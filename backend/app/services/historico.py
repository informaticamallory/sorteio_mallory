"""Pesquisa no historico de sorteios.

Tudo e resolvido no banco: filtros, contagem, ordenacao e paginacao. O
navegador recebe apenas a pagina pedida.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..config import settings
from ..models import (
    AuditLog,
    BlocoSorteio,
    Draw,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    StatusSorteio,
    User,
)
from ..texto import contem, normalizar_busca
from .sorteio import montar_sorteio

ORDENACOES = {"data", "rodada", "ganhador", "premio"}
SITUACOES_ENTREGA = {"entregue", "pendente", "estornado"}


@dataclass
class FiltrosHistorico:
    q: str = ""
    event_id: int | None = None
    bloco_id: int | None = None
    sem_bloco: bool = False
    data_inicio: date | None = None
    data_fim: date | None = None
    status: str | None = None
    entrega: str | None = None
    operador_id: int | None = None
    ordenar: str = "data"
    direcao: str = "desc"

    def para_auditoria(self) -> dict:
        return {
            chave: (valor.isoformat() if isinstance(valor, date) else valor)
            for chave, valor in asdict(self).items()
            if valor not in (None, "", False)
        }


def _limites_utc(filtros: FiltrosHistorico, fuso: str) -> tuple[datetime | None, datetime | None]:
    """Converte as datas (dias locais do evento) para o intervalo UTC gravado."""
    try:
        zona = ZoneInfo(fuso)
    except (ZoneInfoNotFoundError, ValueError):
        zona = ZoneInfo("UTC")

    def para_utc(dia: date) -> datetime:
        local = datetime.combine(dia, time.min, tzinfo=zona)
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    inicio = para_utc(filtros.data_inicio) if filtros.data_inicio else None
    # Fim inclusivo: ate o inicio do dia seguinte (exclusivo).
    fim = para_utc(filtros.data_fim + timedelta(days=1)) if filtros.data_fim else None
    return inicio, fim


def _fuso_dos_filtros(db: Session, filtros: FiltrosHistorico) -> str:
    if filtros.event_id is not None:
        evento = db.get(Event, filtros.event_id)
        if evento is not None:
            return evento.fuso_horario
    return settings.event_timezone


def _condicoes(db: Session, filtros: FiltrosHistorico) -> list:
    condicoes = []
    if filtros.event_id is not None:
        condicoes.append(Draw.event_id == filtros.event_id)
    if filtros.sem_bloco:
        condicoes.append(Draw.bloco_id.is_(None))
    elif filtros.bloco_id is not None:
        condicoes.append(Draw.bloco_id == filtros.bloco_id)
    if filtros.status:
        condicoes.append(Draw.status == filtros.status)
    if filtros.entrega == "entregue":
        condicoes.append(Draw.entregue.is_(True))
    elif filtros.entrega == "pendente":
        condicoes += [Draw.status == StatusSorteio.VALIDO.value, Draw.entregue.is_(False)]
    elif filtros.entrega == "estornado":
        condicoes.append(Draw.estorno_entrega.is_(True))
    if filtros.operador_id is not None:
        condicoes.append(Draw.criado_por_id == filtros.operador_id)

    inicio, fim = _limites_utc(filtros, _fuso_dos_filtros(db, filtros))
    if inicio is not None:
        condicoes.append(Draw.criado_em >= inicio)
    if fim is not None:
        condicoes.append(Draw.criado_em < fim)

    # Cada palavra precisa aparecer em algum campo: "maria souza" encontra
    # "Maria de Souza". Nome e premio sao comparados sem acento e sem caixa;
    # matricula e comparada como texto (zeros a esquerda contam); pulseira em
    # maiusculas, como e gravada.
    for termo in filtros.q.split():
        normalizado = normalizar_busca(termo)
        condicoes.append(
            or_(
                contem(Participant.nome_busca, normalizado),
                contem(Participant.matricula, termo),
                contem(Participant.pulseira, termo.upper()),
                contem(Prize.nome_busca, normalizado),
            )
        )
    return condicoes


def _base(db: Session, filtros: FiltrosHistorico, *colunas) -> Select:  # noqa: ANN002
    consulta = (
        select(*colunas)
        .select_from(Draw)
        .join(PrizeUnit, Draw.prize_unit_id == PrizeUnit.id)
        .join(Prize, PrizeUnit.prize_id == Prize.id)
        .join(Participant, Draw.participant_id == Participant.id)
    )
    condicoes = _condicoes(db, filtros)
    return consulta.where(*condicoes) if condicoes else consulta


def _ordem(filtros: FiltrosHistorico) -> list:
    coluna = {
        "data": Draw.criado_em,
        "rodada": Draw.rodada,
        "ganhador": Participant.nome_busca,
        "premio": Prize.nome_busca,
    }[filtros.ordenar]
    principal = coluna.asc() if filtros.direcao == "asc" else coluna.desc()
    # Desempate estavel: a paginacao nunca repete nem pula linhas.
    desempate = Draw.id.asc() if filtros.direcao == "asc" else Draw.id.desc()
    return [principal, desempate]


def contar(db: Session, filtros: FiltrosHistorico) -> int:
    return db.scalar(_base(db, filtros, func.count(Draw.id))) or 0


def buscar(
    db: Session,
    filtros: FiltrosHistorico,
    pagina: int | None = None,
    por_pagina: int | None = None,
) -> list[dict]:
    """Resultados ja no formato de serializar_sorteio, numa unica consulta."""
    criador = aliased(User)
    entregador = aliased(User)
    anulador = aliased(User)
    consulta = (
        _base(
            db,
            filtros,
            Draw,
            PrizeUnit,
            Prize,
            Participant,
            Event,
            BlocoSorteio,
            criador,
            entregador,
            anulador,
        )
        .join(Event, Draw.event_id == Event.id)
        .outerjoin(BlocoSorteio, Draw.bloco_id == BlocoSorteio.id)
        .join(criador, Draw.criado_por_id == criador.id)
        .outerjoin(entregador, Draw.entregue_por_id == entregador.id)
        .outerjoin(anulador, Draw.anulado_por_id == anulador.id)
        .order_by(*_ordem(filtros))
    )
    if pagina is not None and por_pagina is not None:
        consulta = consulta.limit(por_pagina).offset((pagina - 1) * por_pagina)

    return [
        montar_sorteio(
            sorteio,
            unidade=unidade,
            premio=premio,
            ganhador=ganhador,
            evento=evento,
            bloco=bloco,
            criado_por=criado_por,
            entregue_por=entregue_por,
            anulado_por=anulado_por,
        )
        for (
            sorteio,
            unidade,
            premio,
            ganhador,
            evento,
            bloco,
            criado_por,
            entregue_por,
            anulado_por,
        ) in db.execute(consulta).all()
    ]


def operadores(db: Session, event_id: int | None) -> list[User]:
    """Quem ja realizou sorteios (para o filtro de operador)."""
    consulta = select(User).join(Draw, Draw.criado_por_id == User.id).distinct().order_by(User.nome)
    if event_id is not None:
        consulta = consulta.where(Draw.event_id == event_id)
    return list(db.scalars(consulta).all())


def auditoria_do_sorteio(db: Session, sorteio: Draw) -> list[AuditLog]:
    """Registros ligados ao resultado: o sorteio em si, entrega e anulacao."""
    return list(
        db.scalars(
            select(AuditLog)
            .where(
                AuditLog.event_id == sorteio.event_id,
                or_(
                    AuditLog.detalhes["sorteio_id"].as_integer() == sorteio.id,
                    and_(
                        AuditLog.acao == "sorteio_realizado",
                        AuditLog.detalhes["rodada"].as_integer() == sorteio.rodada,
                    ),
                ),
            )
            .order_by(AuditLog.criado_em, AuditLog.id)
        ).all()
    )
