from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import bus
from ..database import get_db, session_scope
from ..models import Event
from ..services.telao import obter_estado

router = APIRouter(prefix="/api/public", tags=["telao"])

HEARTBEAT_SEGUNDOS = 20


def _evento_por_token(db: Session, token: str) -> Event:
    evento = db.scalar(select(Event).where(Event.telao_token == token))
    if evento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telão não encontrado")
    return evento


@router.get("/{token}/estado")
def estado(token: str, db: Session = Depends(get_db)) -> dict:
    """Estado atual do telao. Seguro para chamar em F5/reconexao: nunca sorteia."""
    return obter_estado(db, _evento_por_token(db, token))


def _estado_inicial(token: str) -> tuple[int, dict]:
    with session_scope() as db:
        evento = _evento_por_token(db, token)
        return evento.id, obter_estado(db, evento)


@router.get("/{token}/stream")
async def stream(token: str, request: Request) -> StreamingResponse:
    # O acesso ao banco e sincrono e pode esperar por lock: roda no threadpool
    # para nao travar o event loop (o que congelaria todas as outras conexoes).
    event_id, inicial = await run_in_threadpool(_estado_inicial, token)

    fila = bus.assinar(event_id)

    async def gerador():
        try:
            yield f"data: {json.dumps({'tipo': 'estado', **inicial}, ensure_ascii=False, default=str)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    mensagem = await asyncio.wait_for(fila.get(), timeout=HEARTBEAT_SEGUNDOS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {mensagem}\n\n"
        finally:
            bus.cancelar(event_id, fila)

    return StreamingResponse(
        gerador(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
