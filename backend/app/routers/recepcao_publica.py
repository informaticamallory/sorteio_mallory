"""Recepcao: check-in pela matricula e consulta do numero, SEM login.

Decisao do evento: o botao Recepcao da tela inicial abre estas telas em
qualquer aparelho, sem senha. Consequencia aceita: quem abrir o endereco do
sistema pode confirmar presencas e consultar nome, matricula e numero.

O que limita o estrago:
  * as respostas trazem so matricula, nome, numero, presenca e premios ja
    revelados no telao (sem foto, setor, pulseira ou dados de conta);
  * o check-in so MARCA presenca (nunca desmarca) e cada um fica na auditoria
    com origem "recepcao" e o IP;
  * um premio so aparece na consulta depois que o telao revelou o ganhador.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, Event, Participant
from ..schemas import (
    AtendidoOut,
    CheckinIn,
    CheckinOut,
    EventoRecepcaoOut,
    LocalizarMatriculaIn,
    PremioConsultaOut,
)
from ..services.autocadastro import _participante_por_matricula
from ..services.consultas import premios_ganhos
from ..services.elegibilidade import matricula_da_sorte
from ..services.notificacoes import sorteios_ainda_em_revelacao
from ..texto import contem, normalizar_busca, normalizar_matricula

router = APIRouter(prefix="/api/recepcao", tags=["recepcao"])

MENSAGEM_NAO_ENCONTRADA = "Matrícula não encontrada neste evento."
MENSAGEM_FECHADA = "A Recepção deste evento ainda não foi aberta pela organização."


def _evento(db: Session, event_id: int) -> Event:
    """Evento com a Recepcao aberta. Fechada: nada de check-in nem consulta.

    A chave fica em Configuracao (admin e organizador). A equipe logada
    continua marcando presenca pelo Credenciamento.
    """
    evento = db.get(Event, event_id)
    if evento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento não encontrado")
    if not evento.recepcao_publica_ativa:
        raise HTTPException(status.HTTP_403_FORBIDDEN, MENSAGEM_FECHADA)
    return evento


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def _atendidos(db: Session, evento: Event, participantes: list[Participant]) -> list[AtendidoOut]:
    ids = [p.id for p in participantes]
    ganhos = premios_ganhos(db, ids)
    escondidos = sorteios_ainda_em_revelacao(db, ids)
    saida = []
    for p in participantes:
        premios = [
            PremioConsultaOut(
                premio_nome=g["premio_nome"],
                bloco_numero=g["bloco_numero"],
                entregue=g["entregue"],
            )
            for g in ganhos.get(p.id, [])
            if g["sorteio_id"] not in escondidos  # telao ainda nao revelou
        ]
        saida.append(
            AtendidoOut(
                id=p.id,
                matricula=p.matricula,
                nome=p.nome,
                numero_sorteio=p.numero_sorteio,
                matricula_da_sorte=matricula_da_sorte(evento, p),
                presente=p.presente,
                participando=p.participando,
                premios=premios,
            )
        )
    return saida


@router.get("/eventos", response_model=list[EventoRecepcaoOut])
def eventos(db: Session = Depends(get_db)) -> list[Event]:
    """Eventos com a Recepcao aberta (reais primeiro, mais recentes antes).

    Lista vazia: a tela inicial esconde o acesso a Recepcao.
    """
    return list(
        db.scalars(
            select(Event)
            .where(Event.recepcao_publica_ativa.is_(True))
            .order_by(Event.demo, Event.criado_em.desc())
        ).all()
    )


@router.post("/{event_id}/localizar", response_model=AtendidoOut)
def localizar(event_id: int, dados: LocalizarMatriculaIn, db: Session = Depends(get_db)) -> AtendidoOut:
    """Check-in, passo 1: a matricula mostra nome e numero antes de confirmar."""
    evento = _evento(db, event_id)
    participante = _participante_por_matricula(db, evento, dados.matricula)
    if participante is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAGEM_NAO_ENCONTRADA)
    return _atendidos(db, evento, [participante])[0]


@router.post("/{event_id}/checkin", response_model=CheckinOut)
def confirmar_checkin(
    event_id: int, dados: CheckinIn, request: Request, db: Session = Depends(get_db)
) -> CheckinOut:
    """Check-in, passo 2: confirma a presenca. Repetir nao muda nada."""
    evento = _evento(db, event_id)
    participante = db.get(Participant, dados.participante_id)
    if participante is None or participante.event_id != evento.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, MENSAGEM_NAO_ENCONTRADA)
    ja_estava = participante.presente
    if not ja_estava:
        participante.presente = True
        db.add(
            AuditLog(
                event_id=evento.id,
                usuario_id=None,
                acao="presenca_alterada",
                detalhes={
                    "participante_id": participante.id,
                    "presente": True,
                    "origem": "recepcao",
                    "ip": _ip(request),
                },
            )
        )
        db.commit()
        db.refresh(participante)
    atendido = _atendidos(db, evento, [participante])[0]
    return CheckinOut(**atendido.model_dump(), ja_estava_presente=ja_estava)


@router.get("/{event_id}/consulta", response_model=list[AtendidoOut])
def consultar(
    event_id: int,
    q: str = Query(..., min_length=2, max_length=120),
    db: Session = Depends(get_db),
) -> list[AtendidoOut]:
    """Numero do sorteio e premios ja revelados, pelo nome (sem acento) ou matricula."""
    evento = _evento(db, event_id)
    termos = q.split()
    if not termos:
        return []
    condicoes = [
        or_(
            contem(Participant.nome_busca, normalizar_busca(t)),
            contem(Participant.matricula, t),
            Participant.matricula_normalizada == normalizar_matricula(t),
        )
        for t in termos
    ]
    linhas = db.scalars(
        select(Participant)
        .where(Participant.event_id == evento.id, *condicoes)
        .order_by(Participant.nome_busca, Participant.id)
        .limit(20)
    ).all()
    return _atendidos(db, evento, list(linhas))
