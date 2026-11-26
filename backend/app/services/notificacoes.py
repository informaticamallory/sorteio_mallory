"""Notificacoes individuais (Fase 6).

  * criadas na MESMA transacao do resultado (sorteio ou anulacao): se o
    resultado foi gravado, o aviso tambem foi;
  * no maximo uma por (sorteio, tipo) - garantido no banco - entao repetir
    um clique ou reconectar nunca duplica;
  * ligadas ao participante (o ganhador pode ainda nao ter conta; o vinculo
    com a conta e feito no autocadastro);
  * o aviso de premio so fica visivel quando o telao revela o ganhador;
  * o empurrao em tempo real vai pelo canal privado do usuario
    (bus.canal_usuario), nunca pelo canal publico do telao.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from .. import bus
from ..models import (
    BlocoSorteio,
    Draw,
    Event,
    Notificacao,
    Participant,
    Prize,
    PrizeUnit,
    StatusSorteio,
    TipoNotificacao,
    User,
    utcnow,
)

ROTULO_ANULACAO = {
    "ausencia": "ausência no momento do sorteio",
    "desistencia": "desistência",
    "erro_operacional": "erro operacional",
    "outro": "decisão da organização",
}


def _existente(db: Session, sorteio_id: int, tipo: TipoNotificacao) -> Notificacao | None:
    return db.scalar(
        select(Notificacao).where(Notificacao.draw_id == sorteio_id, Notificacao.tipo == tipo.value)
    )


def _contexto(db: Session, sorteio: Draw) -> tuple[Participant, Prize | None, PrizeUnit | None, BlocoSorteio | None]:
    unidade = db.get(PrizeUnit, sorteio.prize_unit_id)
    premio = db.get(Prize, unidade.prize_id) if unidade else None
    bloco = db.get(BlocoSorteio, sorteio.bloco_id) if sorteio.bloco_id else None
    return db.get(Participant, sorteio.participant_id), premio, unidade, bloco


def notificar_premio(
    db: Session, sorteio: Draw, evento: Event, disponivel_em: datetime | None
) -> Notificacao:
    existente = _existente(db, sorteio.id, TipoNotificacao.PREMIO_GANHO)
    if existente is not None:
        return existente
    participante, premio, unidade, bloco = _contexto(db, sorteio)
    linhas = [
        f"Seu número da sorte foi contemplado no Sorteio {evento.empresa_nome or 'Mallory'}.",
        f"Prêmio: {premio.nome if premio else 'prêmio'}",
    ]
    if premio is not None and premio.quantidade > 1 and unidade is not None:
        linhas[1] += f" (unidade {unidade.numero} de {premio.quantidade})"
    if bloco is not None:
        linhas.append(f"Bloco: {bloco.numero_exibicao:02d}")
    linhas.append("Retire seu prêmio na recepção apresentando sua pulseira.")
    notificacao = Notificacao(
        event_id=evento.id,
        usuario_id=participante.usuario_id,
        participant_id=participante.id,
        draw_id=sorteio.id,
        prize_id=premio.id if premio else None,
        tipo=TipoNotificacao.PREMIO_GANHO.value,
        titulo="🎉 Parabéns! Você foi sorteado!",
        mensagem="\n".join(linhas),
        lida=False,
        disponivel_em=disponivel_em,
    )
    db.add(notificacao)
    return notificacao


def notificar_anulacao(db: Session, sorteio: Draw) -> Notificacao:
    existente = _existente(db, sorteio.id, TipoNotificacao.SORTEIO_ANULADO)
    if existente is not None:
        return existente
    participante, premio, _unidade, _bloco = _contexto(db, sorteio)
    # Se o aviso do premio ainda nao apareceu (anulacao durante a animacao),
    # o aviso da anulacao nao pode aparecer antes dele.
    ganho = _existente(db, sorteio.id, TipoNotificacao.PREMIO_GANHO)
    agora = utcnow()
    disponivel_em = (
        ganho.disponivel_em if ganho is not None and ganho.disponivel_em and ganho.disponivel_em > agora else None
    )
    motivo = ROTULO_ANULACAO.get(sorteio.tipo_anulacao or "", "decisão da organização")
    notificacao = Notificacao(
        event_id=sorteio.event_id,
        usuario_id=participante.usuario_id,
        participant_id=participante.id,
        draw_id=sorteio.id,
        prize_id=premio.id if premio else None,
        tipo=TipoNotificacao.SORTEIO_ANULADO.value,
        titulo="Resultado de sorteio anulado",
        mensagem=(
            f"O resultado que indicava você como ganhador de {premio.nome if premio else 'um prêmio'} "
            f"foi anulado ({motivo}). Em caso de dúvida, procure a organização do evento."
        ),
        lida=False,
        disponivel_em=disponivel_em,
    )
    db.add(notificacao)
    return notificacao


# ------------------------------------------------------------------ tempo real
def avisar_ganhador(db: Session, sorteio: Draw, tipo: str, quando: datetime | None = None) -> None:
    """Empurra um aviso ao(s) aparelho(s) do ganhador pelo canal privado.

    A mensagem nao carrega dado pessoal: so diz ao aplicativo para reler a
    area pessoal (que exige o token do proprio colaborador).
    """
    participante = db.get(Participant, sorteio.participant_id)
    if participante is None or participante.usuario_id is None:
        return
    evento = db.get(Event, sorteio.event_id)
    if evento is not None and evento.evento_teste:
        return  # evento de teste: nada chega ao celular do colaborador
    atraso = max(0.0, (quando - utcnow()).total_seconds()) if quando else 0.0
    bus.publicar(bus.canal_usuario(participante.usuario_id), {"tipo": tipo}, atraso_s=atraso)


# ------------------------------------------------------------------ leitura
def _do_usuario(user: User):
    """Notificacoes dos cadastros vinculados a conta, ja liberadas."""
    agora = utcnow()
    return (
        Notificacao.participant_id.in_(
            select(Participant.id).where(Participant.usuario_id == user.id)
        ),
        or_(Notificacao.disponivel_em.is_(None), Notificacao.disponivel_em <= agora),
        # Evento de teste: os avisos ficam guardados, mas nao aparecem no portal.
        Notificacao.event_id.in_(select(Event.id).where(Event.evento_teste.is_(False))),
    )


def nao_lidas(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count(Notificacao.id)).where(*_do_usuario(user), Notificacao.lida.is_(False))
    ) or 0


def sorteios_ainda_em_revelacao(db: Session, participantes: list[int]) -> set[int]:
    """Sorteios cujo ganhador o telao ainda nao revelou (nao aparecem na area pessoal)."""
    if not participantes:
        return set()
    return set(
        db.scalars(
            select(Notificacao.draw_id).where(
                Notificacao.participant_id.in_(participantes),
                Notificacao.tipo == TipoNotificacao.PREMIO_GANHO.value,
                Notificacao.disponivel_em > utcnow(),
            )
        ).all()
    )


def _situacao(sorteio: Draw | None) -> str | None:
    if sorteio is None:
        return None
    if sorteio.status == StatusSorteio.ANULADO.value:
        return "anulado"
    return "entregue" if sorteio.entregue else "aguardando_retirada"


def listar(db: Session, user: User, limite: int = 100) -> list[dict]:
    linhas = db.execute(
        select(Notificacao, Event, Draw, Prize, BlocoSorteio)
        .join(Event, Notificacao.event_id == Event.id)
        .outerjoin(Draw, Notificacao.draw_id == Draw.id)
        .outerjoin(Prize, Notificacao.prize_id == Prize.id)
        .outerjoin(BlocoSorteio, Draw.bloco_id == BlocoSorteio.id)
        .where(*_do_usuario(user))
        .order_by(func.coalesce(Notificacao.disponivel_em, Notificacao.criada_em).desc(), Notificacao.id.desc())
        .limit(limite)
    ).all()
    return [
        {
            "id": n.id,
            "tipo": n.tipo,
            "titulo": n.titulo,
            "mensagem": n.mensagem,
            "lida": n.lida,
            "criada_em": n.disponivel_em or n.criada_em,
            "evento_id": evento.id,
            "evento_nome": evento.nome,
            "sorteio_id": n.draw_id,
            "premio_nome": premio.nome if premio else None,
            "premio_imagem_url": premio.imagem_url if premio else None,
            "bloco_numero": bloco.numero_exibicao if bloco else None,
            "situacao": _situacao(sorteio),
        }
        for n, evento, sorteio, premio, bloco in linhas
    ]


def marcar_lida(db: Session, user: User, notificacao_id: int) -> bool:
    """False quando a notificacao nao existe OU nao e do usuario (mesma resposta)."""
    notificacao = db.scalar(
        select(Notificacao).where(Notificacao.id == notificacao_id, *_do_usuario(user))
    )
    if notificacao is None:
        return False
    if not notificacao.lida:
        notificacao.lida = True
        notificacao.lida_em = utcnow()
    return True


def marcar_todas(db: Session, user: User) -> int:
    ids = db.scalars(
        select(Notificacao.id).where(*_do_usuario(user), Notificacao.lida.is_(False))
    ).all()
    if ids:
        db.execute(
            update(Notificacao)
            .where(Notificacao.id.in_(ids))
            .values(lida=True, lida_em=utcnow())
        )
    return len(ids)
