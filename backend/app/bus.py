from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Hashable
from typing import Any

_loop: asyncio.AbstractEventLoop | None = None
# Chaves: o id (int) do evento para o canal publico do telao, e
# ("usuario", id) para o canal privado de cada colaborador. Tipos diferentes
# garantem que um canal nunca receba mensagens do outro.
_assinantes: dict[Hashable, set[asyncio.Queue]] = defaultdict(set)


def canal_usuario(user_id: int) -> tuple[str, int]:
    return ("usuario", user_id)


def registrar_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Guarda o loop principal para permitir publish a partir do threadpool."""
    global _loop
    _loop = loop


def assinar(chave: Hashable) -> asyncio.Queue:
    fila: asyncio.Queue = asyncio.Queue(maxsize=32)
    _assinantes[chave].add(fila)
    return fila


def cancelar(chave: Hashable, fila: asyncio.Queue) -> None:
    _assinantes[chave].discard(fila)


def _entregar(chave: Hashable, mensagem: str) -> None:
    for fila in list(_assinantes.get(chave, ())):
        try:
            fila.put_nowait(mensagem)
        except asyncio.QueueFull:
            # Cliente lento: descarta a mensagem mais antiga e entrega a nova.
            try:
                fila.get_nowait()
                fila.put_nowait(mensagem)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


def publicar(chave: Hashable, payload: dict[str, Any], atraso_s: float = 0) -> None:
    """Publica para os assinantes SSE. Seguro para chamar de qualquer thread.

    `atraso_s` agenda a entrega (ex.: aviso ao ganhador so quando o telao
    revelar o resultado). O agendamento vive em memoria: se o servidor
    reiniciar antes, o cliente ainda ve a notificacao na proxima leitura,
    porque ela esta persistida no banco.
    """
    mensagem = json.dumps(payload, ensure_ascii=False, default=str)
    if _loop is None or not _loop.is_running():
        _entregar(chave, mensagem)
        return
    if atraso_s > 0:
        _loop.call_soon_threadsafe(_loop.call_later, atraso_s, _entregar, chave, mensagem)
        return
    try:
        corrente = asyncio.get_running_loop()
    except RuntimeError:
        corrente = None
    if corrente is _loop:
        _entregar(chave, mensagem)
    else:
        _loop.call_soon_threadsafe(_entregar, chave, mensagem)


def total_conectados(chave: Hashable) -> int:
    return len(_assinantes.get(chave, ()))
