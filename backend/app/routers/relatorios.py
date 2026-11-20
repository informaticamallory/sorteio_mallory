from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer
from ..permissoes import Permissao
from ..models import AuditLog, Draw, Event, StatusSorteio, User
from ..schemas import SorteioOut
from ..services.exportacao import resultados_csv, resultados_xlsx
from ..services.sorteio import serializar_sorteio

router = APIRouter(prefix="/api/events/{event_id}/relatorio", tags=["relatorio"])

EXPORTAR = exigir_permissao(Permissao.EXPORTAR_RESULTADOS)


def _itens(db: Session, evento: Event, filtro: str) -> list[dict]:
    condicoes = [Draw.event_id == evento.id]
    if filtro == "entregues":
        condicoes += [Draw.status == StatusSorteio.VALIDO.value, Draw.entregue.is_(True)]
    elif filtro == "pendentes":
        condicoes += [Draw.status == StatusSorteio.VALIDO.value, Draw.entregue.is_(False)]
    elif filtro == "validos":
        condicoes.append(Draw.status == StatusSorteio.VALIDO.value)
    elif filtro == "anulados":
        condicoes.append(Draw.status == StatusSorteio.ANULADO.value)

    linhas = db.scalars(select(Draw).where(*condicoes).order_by(Draw.rodada)).all()
    return [serializar_sorteio(db, linha) for linha in linhas]


def _nome_arquivo(evento: Event, extensao: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", evento.nome).strip("-").lower() or "evento"
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"sorteio-{base}-{carimbo}.{extensao}"


@router.get(
    "", response_model=list[SorteioOut], dependencies=requer(Permissao.CONSULTAR_RELATORIOS)
)
def listar(
    filtro: str = Query("todos", pattern="^(todos|validos|anulados|entregues|pendentes)$"),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> list[SorteioOut]:
    return [SorteioOut(**item) for item in _itens(db, evento, filtro)]


@router.get("/export.csv")
def exportar_csv(
    filtro: str = Query("todos", pattern="^(todos|validos|anulados|entregues|pendentes)$"),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(EXPORTAR),
) -> Response:
    conteudo = resultados_csv(_itens(db, evento, filtro), evento.fuso_horario)
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="relatorio_exportado",
            detalhes={"formato": "csv", "filtro": filtro},
        )
    )
    db.commit()
    return Response(
        content=conteudo,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{_nome_arquivo(evento, "csv")}"'
        },
    )


@router.get("/export.xlsx")
def exportar_xlsx(
    filtro: str = Query("todos", pattern="^(todos|validos|anulados|entregues|pendentes)$"),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(EXPORTAR),
) -> Response:
    conteudo = resultados_xlsx(_itens(db, evento, filtro), evento.fuso_horario, evento.nome)
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="relatorio_exportado",
            detalhes={"formato": "xlsx", "filtro": filtro},
        )
    )
    db.commit()
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{_nome_arquivo(evento, "xlsx")}"'
        },
    )


@router.get("/auditoria", dependencies=requer(Permissao.VISUALIZAR_AUDITORIA))
def auditoria(
    evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> list[dict]:
    linhas = db.scalars(
        select(AuditLog)
        .where(AuditLog.event_id == evento.id)
        .order_by(AuditLog.criado_em.desc())
        .limit(300)
    ).all()
    return [
        {
            "id": linha.id,
            "acao": linha.acao,
            "detalhes": linha.detalhes,
            "usuario": linha.usuario.nome if linha.usuario else "",
            "criado_em": linha.criado_em,
        }
        for linha in linhas
    ]
