"""Credenciamento (check-in): acompanhar cadastros, presenca e pulseiras.

Marcar presenca usa POST /api/events/{id}/participantes/{pid}/presenca, que
aceita GERENCIAR_PARTICIPANTES ou AUXILIAR_CREDENCIAMENTO.
"""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer
from ..models import AuditLog, Event, Participant, User
from ..permissoes import Permissao
from ..schemas import (
    CredenciadoOut,
    CredenciamentoResumoOut,
    LiberarCadastroIn,
    PaginaCredenciadosOut,
    PulseiraCredenciamentoIn,
)
from ..services import autocadastro as servico
from ..services.consultas import condicao_busca_participante
from ..services.erros import RegraDeNegocio

router = APIRouter(prefix="/api/events/{event_id}/credenciamento", tags=["credenciamento"])

ACOMPANHAR = requer(Permissao.ACOMPANHAR_CREDENCIAMENTO)
# Presenca (AUXILIAR_CREDENCIAMENTO) fica na rota de participantes.
# Pulseira e liberar novo cadastro: so o admin (a equipe so confirma presenca).
ADMINISTRAR = exigir_permissao(Permissao.ADMINISTRAR_CREDENCIAMENTO)


def _saida(p: Participant) -> CredenciadoOut:
    return CredenciadoOut(
        id=p.id,
        nome=p.nome,
        matricula=p.matricula,
        setor=p.setor,
        foto_url=p.foto_url,
        pulseira=p.pulseira,
        numero_sorteio=p.numero_sorteio,
        presente=p.presente,
        participando=p.participando,
        tem_conta=p.usuario_id is not None,
    )


@router.get("/resumo", response_model=CredenciamentoResumoOut, dependencies=ACOMPANHAR)
def resumo(
    evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> CredenciamentoResumoOut:
    def contar(*condicoes) -> int:  # noqa: ANN002
        return db.scalar(
            select(func.count(Participant.id)).where(Participant.event_id == evento.id, *condicoes)
        ) or 0

    total = contar()
    presentes = contar(Participant.presente.is_(True))
    com_pulseira = contar(Participant.pulseira.is_not(None))
    return CredenciamentoResumoOut(
        participantes=total,
        participando=contar(Participant.participando.is_(True)),
        presentes=presentes,
        ausentes=total - presentes,
        com_pulseira=com_pulseira,
        sem_pulseira=total - com_pulseira,
        com_conta=contar(Participant.usuario_id.is_not(None)),
    )


@router.get("/participantes", response_model=PaginaCredenciadosOut, dependencies=ACOMPANHAR)
def listar(
    q: str = Query("", max_length=120),
    situacao: str = Query("todos", pattern="^(todos|presentes|ausentes|sem_pulseira)$"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(30, ge=1, le=100),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> PaginaCredenciadosOut:
    condicoes = [Participant.event_id == evento.id, *condicao_busca_participante(q.strip())]
    if situacao == "presentes":
        condicoes.append(Participant.presente.is_(True))
    elif situacao == "ausentes":
        condicoes.append(Participant.presente.is_(False))
    elif situacao == "sem_pulseira":
        condicoes.append(Participant.pulseira.is_(None))

    total = db.scalar(select(func.count(Participant.id)).where(*condicoes)) or 0
    linhas = db.scalars(
        select(Participant)
        .where(*condicoes)
        .order_by(Participant.nome_busca, Participant.id)
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return PaginaCredenciadosOut(
        itens=[_saida(p) for p in linhas],
        total=total,
        pagina=pagina,
        paginas=max(1, math.ceil(total / por_pagina)),
    )


@router.post("/participantes/{participant_id}/pulseira", response_model=CredenciadoOut)
def atribuir_pulseira(
    participant_id: int,
    dados: PulseiraCredenciamentoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(ADMINISTRAR),
) -> CredenciadoOut:
    """Entrega ou troca a pulseira. A troca exige motivo e fica na auditoria."""
    participante = db.get(Participant, participant_id)
    if participante is None or participante.event_id != evento.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Participante não encontrado")
    if participante.pulseira == dados.pulseira:
        return _saida(participante)

    troca = participante.pulseira is not None
    motivo = (dados.motivo or "").strip()
    if troca and len(motivo) < 5:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Para trocar uma pulseira já entregue, informe o motivo (mínimo 5 caracteres).",
        )
    ocupada = db.scalar(
        select(Participant).where(
            Participant.event_id == evento.id,
            Participant.pulseira == dados.pulseira,
            Participant.id != participante.id,
        )
    )
    if ocupada is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A pulseira {dados.pulseira} já está atribuída a outro participante neste evento",
        )

    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="pulseira_trocada" if troca else "pulseira_atribuida",
            detalhes={
                "participante_id": participante.id,
                "anterior": participante.pulseira,
                "nova": dados.pulseira,
                "motivo": motivo or None,
                "origem": "credenciamento",
            },
        )
    )
    participante.pulseira = dados.pulseira
    db.commit()
    db.refresh(participante)
    return _saida(participante)


@router.post("/participantes/{participant_id}/liberar-cadastro", response_model=CredenciadoOut)
def liberar_cadastro(
    participant_id: int,
    dados: LiberarCadastroIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(ADMINISTRAR),
) -> CredenciadoOut:
    """Permite refazer o autocadastro (cadastro indevido ou senha esquecida).

    So vale o primeiro autocadastro; para refazer, a equipe confere o cracha e
    libera aqui, com motivo registrado na auditoria.
    """
    participante = db.get(Participant, participant_id)
    if participante is None or participante.event_id != evento.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Participante não encontrado")
    try:
        servico.liberar_novo_cadastro(db, evento, participante, dados.motivo.strip(), user)
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    db.refresh(participante)
    return _saida(participante)

