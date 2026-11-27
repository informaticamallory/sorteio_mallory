"""Ambiente de teste: copia de um evento real para ensaiar os sorteios.

A copia nasce marcada como evento de teste (fora do portal do colaborador,
sem avisos nem push, fora da lista de cadastro) e com a Recepcao e o cadastro
pelo QR Code fechados. O evento real nao e alterado.

  * copia: configuracao, cores, tema do telao, regras e modo do sorteio;
    premios (com imagens e quantidades) e blocos com a mesma distribuicao,
    tudo zerado (unidades disponiveis, blocos planejados);
  * participantes com o mesmo RE/matricula, setor e participacao, mas com o
    nome trocado por "Participante 001..." (LGPD) e presenca confirmada;
  * NAO copia: sorteios, entregas, notificacoes, contas, codigos de CPF e
    nascimento, pulseiras e fotos dos colaboradores.

"Recomecar teste" apaga os sorteios, entregas e notificacoes do evento de
teste e devolve todas as unidades aos blocos, para ensaiar de novo do zero.
So funciona em evento de teste: os resultados de um evento real nunca sao
apagados.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..models import (
    AuditLog,
    BlocoSorteio,
    DisplayState,
    Draw,
    EstadoTelao,
    Event,
    Notificacao,
    Participant,
    Prize,
    PrizeUnit,
    StatusBloco,
    StatusUnidade,
    User,
)
from ..security import novo_token_telao
from . import carrossel
from .erros import RegraDeNegocio

PREFIXO_NOME = "TESTE — "

# Campos de configuracao copiados como estao.
CAMPOS_COPIADOS = (
    "empresa_nome",
    "logo_url",
    "cor_fundo",
    "cor_primaria",
    "cor_texto",
    "cor_destaque",
    "mensagem_boas_vindas",
    "mensagem_encerramento",
    "regras_participacao",
    "som_ativado",
    "reduzir_animacoes",
    "duracao_animacao_ms",
    "fuso_horario",
    "capacidade_bloco_padrao",
    "carrossel_segundos",
    "permite_multiplas_vitorias",
    "exige_presenca",
    "tratamento_ausente",
    "ausente_pode_concorrer_novamente",
    "modo_sorteio",
    "matricula_faixa_inicio",
    "matricula_faixa_fim",
    "regras_confirmadas_em",
    "tema_telao",
    "claro_cor_fundo",
    "claro_cor_painel",
    "claro_cor_destaque",
    "claro_cor_texto",
    "telao_subtitulo",
    "som_sorteio",
)


def _auditar(db: Session, evento_id: int, usuario: User, acao: str, detalhes: dict) -> None:
    db.add(AuditLog(event_id=evento_id, usuario_id=usuario.id, acao=acao, detalhes=detalhes))


def criar_copia(db: Session, origem: Event, usuario: User) -> Event:
    """Cria o evento de teste a partir de `origem`. Nao faz commit."""
    if origem.evento_teste:
        raise RegraDeNegocio("Este já é um evento de teste. Crie o ambiente de teste a partir do evento real.", 409)

    copia = Event(
        nome=(PREFIXO_NOME + origem.nome)[:200],
        telao_token=novo_token_telao(),
        evento_teste=True,
        demo=False,
        autocadastro_ativo=False,
        recepcao_publica_ativa=False,
        **{campo: getattr(origem, campo) for campo in CAMPOS_COPIADOS},
    )
    db.add(copia)
    db.flush()

    # Blocos (os excluidos ficam de fora), zerados: todos planejados.
    blocos = db.scalars(
        select(BlocoSorteio)
        .where(BlocoSorteio.event_id == origem.id, BlocoSorteio.excluido_em.is_(None))
        .order_by(BlocoSorteio.ordem, BlocoSorteio.id)
    ).all()
    mapa_blocos: dict[int, int] = {}
    for bloco in blocos:
        novo = BlocoSorteio(
            event_id=copia.id,
            numero=bloco.numero_exibicao,
            nome=bloco.nome,
            descricao=bloco.descricao,
            capacidade=bloco.capacidade,
            status=StatusBloco.PLANEJADO.value,
            ordem=bloco.ordem,
        )
        db.add(novo)
        db.flush()
        mapa_blocos[bloco.id] = novo.id

    # Premios (os excluidos ficam de fora) com as unidades na mesma distribuicao.
    premios = db.scalars(
        select(Prize).where(Prize.event_id == origem.id, Prize.excluido_em.is_(None)).order_by(Prize.ordem, Prize.id)
    ).all()
    unidades_copiadas = 0
    for premio in premios:
        novo_premio = Prize(
            event_id=copia.id,
            nome=premio.nome,
            descricao=premio.descricao,
            imagem_url=premio.imagem_url,
            quantidade=premio.quantidade,
            ordem=premio.ordem,
        )
        db.add(novo_premio)
        db.flush()
        for unidade in sorted(premio.unidades, key=lambda u: u.numero):
            if unidade.status == StatusUnidade.REMOVIDO.value:
                continue
            bloco_novo = mapa_blocos.get(unidade.bloco_id) if unidade.bloco_id else None
            db.add(
                PrizeUnit(
                    prize_id=novo_premio.id,
                    numero=unidade.numero,
                    status=StatusUnidade.DISPONIVEL.value,
                    bloco_id=bloco_novo,
                    ordem_bloco=unidade.ordem_bloco if bloco_novo else None,
                )
            )
            unidades_copiadas += 1

    # Participantes: mesmo RE e setor, nome trocado (LGPD), presenca confirmada.
    participantes = db.scalars(
        select(Participant).where(Participant.event_id == origem.id).order_by(Participant.id)
    ).all()
    for indice, participante in enumerate(participantes, start=1):
        db.add(
            Participant(
                event_id=copia.id,
                nome=f"Participante {indice:03d}",
                matricula=participante.matricula,
                setor=participante.setor,
                participando=participante.participando,
                motivo_participacao=participante.motivo_participacao,
                presente=True,
            )
        )
    db.flush()

    detalhes = {
        "origem_id": origem.id,
        "origem_nome": origem.nome,
        "copia_id": copia.id,
        "participantes": len(participantes),
        "premios": len(premios),
        "unidades": unidades_copiadas,
        "blocos": len(blocos),
    }
    _auditar(db, copia.id, usuario, "ambiente_teste_criado", detalhes)
    _auditar(db, origem.id, usuario, "ambiente_teste_criado", detalhes)
    return copia


def recomecar(db: Session, evento: Event, usuario: User) -> dict:
    """Zera os sorteios do evento de teste. Nao faz commit."""
    if not evento.evento_teste:
        raise RegraDeNegocio("Só um evento de teste pode ser recomeçado: os resultados reais nunca são apagados.", 409)

    total = db.scalar(select(func.count(Draw.id)).where(Draw.event_id == evento.id)) or 0
    db.execute(delete(Notificacao).where(Notificacao.event_id == evento.id))
    db.execute(update(Draw).where(Draw.event_id == evento.id).values(draw_anterior_id=None))
    db.execute(delete(Draw).where(Draw.event_id == evento.id))

    premios_ids = select(Prize.id).where(Prize.event_id == evento.id)
    db.execute(
        update(PrizeUnit)
        .where(PrizeUnit.prize_id.in_(premios_ids), PrizeUnit.status != StatusUnidade.REMOVIDO.value)
        .values(status=StatusUnidade.DISPONIVEL.value)
    )
    db.execute(
        update(BlocoSorteio)
        .where(BlocoSorteio.event_id == evento.id, BlocoSorteio.excluido_em.is_(None))
        .values(status=StatusBloco.PLANEJADO.value, iniciado_em=None, finalizado_em=None, finalizado_por_id=None)
    )

    ds = db.get(DisplayState, evento.id)
    if ds is not None:
        ds.estado = EstadoTelao.AGUARDANDO.value
        ds.prize_unit_id = None
        ds.draw_id = None
        ds.nomes_animacao = []
        ds.revelar_em = None
        carrossel.limpar(ds)
        ds.versao += 1

    _auditar(db, evento.id, usuario, "ambiente_teste_recomecado", {"sorteios_apagados": total})
    return {"sorteios_apagados": total}
