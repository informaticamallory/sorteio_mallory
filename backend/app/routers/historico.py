from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import exigir_permissao
from ..permissoes import Permissao, tem_permissao
from ..models import AuditLog, Draw, Event, User
from ..schemas import (
    OperadorOut,
    PaginaSorteiosOut,
    RegistroAuditoriaOut,
    SorteioDetalheOut,
    SorteioOut,
)
from ..services import historico as servico
from ..services.exportacao import resultados_csv, resultados_xlsx
from ..services.sorteio import serializar_sorteio

router = APIRouter(prefix="/api/sorteios", tags=["historico"])

CONSULTAR = exigir_permissao(Permissao.CONSULTAR_RESULTADOS)
EXPORTAR = exigir_permissao(Permissao.EXPORTAR_RESULTADOS)


def filtros_da_consulta(
    q: str = Query("", max_length=120, description="Nome, matricula, pulseira ou premio"),
    event_id: int | None = Query(None),
    bloco_id: int | None = Query(None),
    sem_bloco: bool = Query(False, description="Apenas sorteios feitos fora de blocos"),
    data_inicio: date | None = Query(None, description="AAAA-MM-DD, no fuso do evento"),
    data_fim: date | None = Query(None, description="AAAA-MM-DD, inclusivo"),
    situacao: str | None = Query(None, alias="status", pattern="^(valido|anulado)$"),
    entrega: str | None = Query(None, pattern="^(entregue|pendente|estornado)$"),
    operador_id: int | None = Query(None),
    ordenar: str = Query("data", pattern="^(data|rodada|ganhador|premio)$"),
    direcao: str = Query("desc", pattern="^(asc|desc)$"),
) -> servico.FiltrosHistorico:
    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A data inicial e posterior a data final"
        )
    return servico.FiltrosHistorico(
        q=q.strip(),
        event_id=event_id,
        bloco_id=bloco_id,
        sem_bloco=sem_bloco,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status=situacao,
        entrega=entrega,
        operador_id=operador_id,
        ordenar=ordenar,
        direcao=direcao,
    )


@router.get("", response_model=PaginaSorteiosOut)
def pesquisar(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
    filtros: servico.FiltrosHistorico = Depends(filtros_da_consulta),
    db: Session = Depends(get_db),
    _: User = Depends(CONSULTAR),
) -> PaginaSorteiosOut:
    total = servico.contar(db, filtros)
    itens = servico.buscar(db, filtros, pagina, por_pagina)
    return PaginaSorteiosOut(
        itens=[SorteioOut(**item) for item in itens],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        paginas=max(1, math.ceil(total / por_pagina)),
    )


@router.get("/operadores", response_model=list[OperadorOut])
def listar_operadores(
    event_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(CONSULTAR),
) -> list[OperadorOut]:
    return [OperadorOut(id=u.id, nome=u.nome) for u in servico.operadores(db, event_id)]


def _exportar(
    db: Session, filtros: servico.FiltrosHistorico, user: User, formato: str
) -> Response:
    itens = servico.buscar(db, filtros)
    evento = db.get(Event, filtros.event_id) if filtros.event_id else None
    fuso = evento.fuso_horario if evento else settings.event_timezone
    if formato == "csv":
        conteudo = resultados_csv(itens, fuso)
        tipo = "text/csv; charset=utf-8"
    else:
        conteudo = resultados_xlsx(itens, fuso, evento.nome if evento else "Todos os eventos")
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    db.add(
        AuditLog(
            event_id=evento.id if evento else None,
            usuario_id=user.id,
            acao="historico_exportado",
            detalhes={"formato": formato, "linhas": len(itens), "filtros": filtros.para_auditoria()},
        )
    )
    db.commit()

    base = re.sub(r"[^a-zA-Z0-9]+", "-", evento.nome).strip("-").lower() if evento else "todos"
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    nome = f"sorteios-{base or 'evento'}-{carimbo}.{formato}"
    return Response(
        content=conteudo,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/export.csv")
def exportar_csv(
    filtros: servico.FiltrosHistorico = Depends(filtros_da_consulta),
    db: Session = Depends(get_db),
    user: User = Depends(EXPORTAR),
) -> Response:
    return _exportar(db, filtros, user, "csv")


@router.get("/export.xlsx")
def exportar_xlsx(
    filtros: servico.FiltrosHistorico = Depends(filtros_da_consulta),
    db: Session = Depends(get_db),
    user: User = Depends(EXPORTAR),
) -> Response:
    return _exportar(db, filtros, user, "xlsx")


@router.get("/{draw_id}", response_model=SorteioDetalheOut)
def detalhe(
    draw_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(CONSULTAR),
) -> SorteioDetalheOut:
    sorteio = db.get(Draw, draw_id)
    if sorteio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resultado não encontrado")
    mesma_unidade = db.scalars(
        select(Draw).where(Draw.prize_unit_id == sorteio.prize_unit_id).order_by(Draw.rodada, Draw.id)
    ).all()
    return SorteioDetalheOut(
        sorteio=SorteioOut(**serializar_sorteio(db, sorteio)),
        indice_sorteado=sorteio.indice_sorteado,
        historico_da_unidade=[SorteioOut(**serializar_sorteio(db, d)) for d in mesma_unidade],
        auditoria=[
            RegistroAuditoriaOut(
                id=linha.id,
                acao=linha.acao,
                detalhes=linha.detalhes,
                usuario=linha.usuario.nome if linha.usuario else "",
                criado_em=linha.criado_em,
            )
            # A auditoria so aparece para quem pode ve-la (admin).
            for linha in (
                servico.auditoria_do_sorteio(db, sorteio)
                if tem_permissao(user, Permissao.VISUALIZAR_AUDITORIA)
                else []
            )
        ],
    )
