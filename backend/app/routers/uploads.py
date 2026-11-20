from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from ..config import settings
from ..deps import requer
from ..permissoes import Permissao
from ..services.imagens import ImagemInvalida, salvar_imagem

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


# Endpoint sincrono de proposito: a validacao/reencode da imagem pelo Pillow e
# trabalho de CPU e, em `async def`, travaria o event loop (e com ele o telao).
# Usado por quem cadastra premios, fotos de participantes ou o logo do evento.
@router.post(
    "/imagem",
    dependencies=requer(
        Permissao.CADASTRAR_PREMIOS,
        Permissao.GERENCIAR_PARTICIPANTES,
        Permissao.GERENCIAR_EVENTOS,
        alguma=True,
    ),
)
def enviar_imagem(arquivo: UploadFile = File(...)) -> dict:
    conteudo = arquivo.file.read()
    if len(conteudo) > settings.max_upload_bytes:
        limite = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Imagem maior que {limite} MB"
        )
    try:
        url = salvar_imagem(conteudo, arquivo.filename or "")
    except ImagemInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"url": url}
