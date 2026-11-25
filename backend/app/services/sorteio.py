from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    AuditLog,
    BlocoSorteio,
    Draw,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    StatusSorteio,
    StatusUnidade,
    User,
    utcnow,
)
from ..permissoes import Permissao, tem_permissao
from .blocos import bloqueio_do_bloco, proxima_do_bloco
from .elegibilidade import modo_faixa_matricula, participantes_elegiveis
from .erros import RegraDeNegocio
from .notificacoes import notificar_anulacao, notificar_premio

__all__ = ["RegraDeNegocio"]


def _auditar(db: Session, evento_id: int, usuario: User, acao: str, detalhes: dict) -> None:
    db.add(AuditLog(event_id=evento_id, usuario_id=usuario.id, acao=acao, detalhes=detalhes))


def escolher_indice(total: int) -> int:
    """Indice uniformemente distribuido em [0, total) usando CSPRNG do SO.

    secrets.randbelow usa rejeicao de amostragem, portanto nao sofre do vies
    de modulo que `random.randint`/`% n` introduziriam.
    """
    if total <= 0:
        raise ValueError("total deve ser positivo")
    return secrets.randbelow(total)


def realizar_sorteio(
    db: Session,
    evento: Event,
    prize_unit_id: int,
    idempotency_key: str,
    usuario: User,
    motivo_fora_da_ordem: str | None = None,
) -> tuple[Draw, bool]:
    """Sorteia uma unidade de premio. Retorna (sorteio, reaproveitado).

    `reaproveitado=True` significa que a chave de idempotencia ja havia sido
    usada e o resultado anterior foi devolvido sem novo sorteio.

    Toda a funcao roda dentro de uma unica transacao. Em SQLite ela e aberta
    com BEGIN IMMEDIATE (ver database.py), o que serializa sorteios concorrentes.
    """
    existente = db.scalar(select(Draw).where(Draw.idempotency_key == idempotency_key))
    if existente is not None:
        if existente.event_id != evento.id:
            raise RegraDeNegocio("Chave de idempotência pertence a outro evento", 409)
        return existente, True

    unidade = db.get(PrizeUnit, prize_unit_id)
    if unidade is None:
        raise RegraDeNegocio("Unidade de prêmio não encontrada", 404)

    premio = db.get(Prize, unidade.prize_id)
    if premio is None or premio.event_id != evento.id:
        raise RegraDeNegocio("Unidade de prêmio não pertence a este evento", 400)

    if unidade.status != StatusUnidade.DISPONIVEL.value:
        raise RegraDeNegocio("Esta unidade do prêmio já foi sorteada", 409)

    # Modo blocos: so o bloco em andamento sorteia, e nunca durante a revelacao
    # de outro sorteio no telao. Checado dentro da transacao exclusiva.
    motivo = bloqueio_do_bloco(db, evento, unidade)
    if motivo:
        raise RegraDeNegocio(motivo, 409)

    # Modo blocos: segue a sequencia do bloco. Pular so com permissao e motivo.
    fora_da_ordem = None
    proxima = proxima_do_bloco(db, unidade.bloco_id) if unidade.bloco_id is not None else None
    if proxima is not None and proxima[0].id != unidade.id:
        proxima_unidade, proximo_premio = proxima
        texto = (motivo_fora_da_ordem or "").strip()
        if not tem_permissao(usuario, Permissao.PULAR_ORDEM_DO_BLOCO):
            raise RegraDeNegocio(
                f"Siga a sequência do bloco: o próximo prêmio é {proximo_premio.nome} "
                f"(unidade {proxima_unidade.numero}). Só um administrador pode sortear fora da ordem.",
                409,
            )
        if len(texto) < 5:
            raise RegraDeNegocio(
                "Informe o motivo para sortear fora da sequência do bloco (mínimo 5 caracteres).", 422
            )
        fora_da_ordem = {
            "motivo": texto,
            "proxima_unidade_id": proxima_unidade.id,
            "proximo_premio": proximo_premio.nome,
            "proxima_unidade": proxima_unidade.numero,
        }

    faixa = modo_faixa_matricula(evento)
    if faixa and (evento.matricula_faixa_inicio is None or evento.matricula_faixa_fim is None):
        raise RegraDeNegocio("Defina a faixa de matrículas nas Regras antes de sortear", 409)

    elegiveis = participantes_elegiveis(db, evento)
    if not elegiveis:
        if faixa:
            raise RegraDeNegocio(
                "Nenhum participante elegível com matrícula entre "
                f"{evento.matricula_faixa_inicio} e {evento.matricula_faixa_fim}",
                409,
            )
        raise RegraDeNegocio(
            "Não há participantes elegíveis para esta rodada conforme as regras configuradas", 409
        )

    indice = escolher_indice(len(elegiveis))
    ganhador: Participant = elegiveis[indice]

    ultima_rodada = (
        db.scalar(select(func.max(Draw.rodada)).where(Draw.event_id == evento.id)) or 0
    )

    anterior = db.scalar(
        select(Draw)
        .where(Draw.prize_unit_id == unidade.id)
        .order_by(Draw.id.desc())
        .limit(1)
    )

    sorteio = Draw(
        event_id=evento.id,
        prize_unit_id=unidade.id,
        participant_id=ganhador.id,
        rodada=ultima_rodada + 1,
        status=StatusSorteio.VALIDO.value,
        idempotency_key=idempotency_key,
        elegiveis_ids=[p.id for p in elegiveis],
        elegiveis_total=len(elegiveis),
        indice_sorteado=indice,
        criado_por_id=usuario.id,
        draw_anterior_id=anterior.id if anterior is not None else None,
        # Fotografia do bloco no momento do sorteio (ver Draw.bloco_id).
        bloco_id=unidade.bloco_id,
    )
    unidade.status = StatusUnidade.SORTEADO.value
    db.add(sorteio)

    _auditar(
        db,
        evento.id,
        usuario,
        "sorteio_realizado",
        {
            "unidade_id": unidade.id,
            "premio": premio.nome,
            "ganhador_id": ganhador.id,
            "elegiveis_total": len(elegiveis),
            "rodada": ultima_rodada + 1,
            "modo_sorteio": evento.modo_sorteio,
            **(
                {"faixa_matricula": [evento.matricula_faixa_inicio, evento.matricula_faixa_fim]}
                if faixa
                else {}
            ),
            **({"fora_da_ordem": fora_da_ordem} if fora_da_ordem else {}),
        },
    )

    try:
        db.flush()
    except IntegrityError as exc:  # pragma: no cover - backstop do indice unico
        db.rollback()
        raise RegraDeNegocio("Já existe um resultado válido para esta unidade", 409) from exc

    # Aviso ao ganhador na mesma transacao do resultado. Fica visivel quando
    # o telao termina a animacao (revelar_em = agora + duracao da animacao).
    notificar_premio(
        db, sorteio, evento, utcnow() + timedelta(milliseconds=evento.duracao_animacao_ms)
    )
    db.flush()

    return sorteio, False


def registrar_entrega(
    db: Session,
    sorteio: Draw,
    entregue: bool,
    usuario: User,
    pulseira_conferida: str | None = None,
    motivo: str | None = None,
    foto_url: str | None = None,
) -> Draw:
    """Confirma ou desfaz a entrega de UMA unidade (cada uma tem o proprio registro).

    `foto_url`: foto opcional tirada no balcao (fica no registro da entrega).

    Roda dentro da transacao exclusiva da requisicao: dois atendentes
    confirmando a mesma unidade ao mesmo tempo -> o segundo recebe 409.
    Desfazer exige justificativa; a permissao e conferida pelo chamador.
    """
    if sorteio.status != StatusSorteio.VALIDO.value:
        raise RegraDeNegocio("Não é possível alterar a entrega de um resultado anulado", 409)
    if entregue and sorteio.entregue:
        quem = db.get(User, sorteio.entregue_por_id) if sorteio.entregue_por_id else None
        raise RegraDeNegocio(
            "Este prêmio já foi entregue"
            + (f" por {quem.nome}" if quem else "")
            + ". Nenhuma entrega duplicada foi registrada.",
            409,
        )
    if not entregue:
        if not sorteio.entregue:
            raise RegraDeNegocio("Este prêmio ainda não foi entregue; não há entrega para desfazer.", 409)
        if not motivo or len(motivo.strip()) < 5:
            raise RegraDeNegocio("Informe a justificativa para desfazer a entrega (mínimo 5 caracteres).", 422)
    entrega_original = (
        {
            "entregue_em": sorteio.entregue_em.isoformat() if sorteio.entregue_em else None,
            "entregue_por_id": sorteio.entregue_por_id,
        }
        if not entregue
        else None
    )

    ganhador = db.get(Participant, sorteio.participant_id)
    # Conferencia no balcao: a pulseira apresentada precisa ser a do ganhador.
    if entregue and pulseira_conferida is not None and ganhador is not None:
        if ganhador.pulseira and pulseira_conferida != ganhador.pulseira:
            raise RegraDeNegocio(
                "A pulseira apresentada não confere com a do ganhador. Entrega não registrada.",
                409,
            )

    unidade = db.get(PrizeUnit, sorteio.prize_unit_id)
    premio = db.get(Prize, unidade.prize_id) if unidade else None
    if entregue:
        sorteio.entregue = True
        sorteio.entregue_em = utcnow()
        sorteio.entregue_por_id = usuario.id
        if unidade is not None:
            unidade.status = StatusUnidade.ENTREGUE.value
    else:
        sorteio.entregue = False
        sorteio.entregue_em = None
        sorteio.entregue_por_id = None
        if unidade is not None:
            unidade.status = StatusUnidade.SORTEADO.value

    _auditar(
        db,
        sorteio.event_id,
        usuario,
        "entrega_registrada" if entregue else "entrega_revertida",
        {
            "sorteio_id": sorteio.id,
            "participante_id": sorteio.participant_id,
            "participante": ganhador.nome if ganhador else None,
            "matricula": ganhador.matricula if ganhador else None,
            "premio_id": premio.id if premio else None,
            "premio": premio.nome if premio else None,
            "unidade": unidade.numero if unidade else None,
            "bloco_id": sorteio.bloco_id,
            "pulseira_conferida": pulseira_conferida,
            "estado": {
                "antes": "pendente" if entregue else "entregue",
                "depois": "entregue" if entregue else "pendente",
            },
            **({"motivo": motivo.strip(), "entrega_original": entrega_original} if not entregue else {}),
            **({"foto_url": foto_url} if entregue and foto_url else {}),
        },
    )
    db.flush()
    return sorteio


def anular_sorteio(
    db: Session,
    sorteio: Draw,
    motivo: str,
    tipo: str,
    confirmar_estorno: bool,
    usuario: User,
) -> Draw:
    """Anula um resultado preservando o registro e liberando a unidade."""
    if sorteio.status == StatusSorteio.ANULADO.value:
        raise RegraDeNegocio("Este resultado já está anulado", 409)

    if sorteio.entregue and not confirmar_estorno:
        raise RegraDeNegocio(
            "Este prêmio já foi entregue. A anulação exige confirmação explícita de estorno.", 409
        )

    sorteio.status = StatusSorteio.ANULADO.value
    sorteio.anulado_em = utcnow()
    sorteio.anulado_por_id = usuario.id
    sorteio.motivo_anulacao = motivo
    sorteio.tipo_anulacao = tipo
    if sorteio.entregue:
        sorteio.estorno_entrega = True
        sorteio.entregue = False  # entregue_em/por sao preservados como historico

    unidade = db.get(PrizeUnit, sorteio.prize_unit_id)
    if unidade is not None:
        premio = db.get(Prize, unidade.prize_id)
        if premio is not None and premio.excluido_em is not None:
            # Premio excluido pelo admin: a unidade nao volta para o sorteio.
            unidade.status = StatusUnidade.REMOVIDO.value
            unidade.bloco_id = None
            unidade.ordem_bloco = None
        else:
            unidade.status = StatusUnidade.DISPONIVEL.value

    _auditar(
        db,
        sorteio.event_id,
        usuario,
        "sorteio_anulado",
        {
            "sorteio_id": sorteio.id,
            "motivo": motivo,
            "tipo": tipo,
            "estorno": sorteio.estorno_entrega,
        },
    )
    notificar_anulacao(db, sorteio)
    db.flush()
    return sorteio


def serializar_sorteio(db: Session, sorteio: Draw) -> dict:
    unidade = db.get(PrizeUnit, sorteio.prize_unit_id)
    return montar_sorteio(
        sorteio,
        unidade=unidade,
        premio=db.get(Prize, unidade.prize_id) if unidade else None,
        ganhador=db.get(Participant, sorteio.participant_id),
        evento=db.get(Event, sorteio.event_id),
        bloco=db.get(BlocoSorteio, sorteio.bloco_id) if sorteio.bloco_id else None,
        criado_por=db.get(User, sorteio.criado_por_id),
        entregue_por=db.get(User, sorteio.entregue_por_id) if sorteio.entregue_por_id else None,
        anulado_por=db.get(User, sorteio.anulado_por_id) if sorteio.anulado_por_id else None,
    )


def montar_sorteio(
    sorteio: Draw,
    *,
    unidade: PrizeUnit | None,
    premio: Prize | None,
    ganhador: Participant | None,
    evento: Event | None,
    bloco: BlocoSorteio | None,
    criado_por: User | None,
    entregue_por: User | None,
    anulado_por: User | None,
) -> dict:
    """Formato unico de um resultado, a partir de objetos ja carregados.

    Usado tanto por serializar_sorteio (um registro) quanto pela busca
    paginada do historico, que carrega tudo numa consulta so.
    """
    return {
        "id": sorteio.id,
        "rodada": sorteio.rodada,
        "status": sorteio.status,
        "premio_id": premio.id if premio else 0,
        "premio_nome": premio.nome if premio else "",
        "premio_imagem_url": premio.imagem_url if premio else None,
        "unidade_id": sorteio.prize_unit_id,
        "unidade_numero": unidade.numero if unidade else 0,
        "ganhador_id": ganhador.id if ganhador else 0,
        "ganhador_nome": ganhador.nome if ganhador else "",
        "ganhador_matricula": ganhador.matricula if ganhador else "",
        "ganhador_setor": ganhador.setor if ganhador else "",
        "ganhador_foto_url": ganhador.foto_url if ganhador else None,
        "ganhador_pulseira": ganhador.pulseira if ganhador else None,
        "evento_id": sorteio.event_id,
        "evento_nome": evento.nome if evento else "",
        "evento_fuso": evento.fuso_horario if evento else None,
        "elegiveis_total": sorteio.elegiveis_total,
        "criado_em": sorteio.criado_em,
        "criado_por": criado_por.nome if criado_por else "",
        "entregue": sorteio.entregue,
        "entregue_em": sorteio.entregue_em,
        "entregue_por": entregue_por.nome if entregue_por else None,
        "anulado_em": sorteio.anulado_em,
        "anulado_por": anulado_por.nome if anulado_por else None,
        "motivo_anulacao": sorteio.motivo_anulacao,
        "tipo_anulacao": sorteio.tipo_anulacao,
        "estorno_entrega": sorteio.estorno_entrega,
        "draw_anterior_id": sorteio.draw_anterior_id,
        "bloco_id": sorteio.bloco_id,
        "bloco_numero": bloco.numero_exibicao if bloco else None,
        "bloco_nome": bloco.nome_exibicao if bloco else None,
        "reaproveitado": False,
    }
