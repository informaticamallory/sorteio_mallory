from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from . import bus
from .config import BASE_DIR, arquivo_sqlite, avisos_de_ambiente, exigir_volume_de_dados, settings
from .database import session_scope
from .migracoes import aplicar_migracoes
from .models import Papel, User
from .routers import (
    auth,
    autocadastro,
    blocos,
    credenciamento,
    eventos,
    historico,
    minha_area,
    participantes,
    portal,
    premios,
    publico,
    recepcao,
    recepcao_publica,
    relatorios,
    sorteios,
    uploads,
    usuarios,
)
from .security import hash_senha
from .services import push

FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
PUSH_INTERVALO_SEGUNDOS = 2


def garantir_organizador() -> None:
    with session_scope() as db:
        usuario = settings.admin_usuario.strip().lower()
        existente = db.scalar(select(User).where(User.usuario == usuario))
        if existente is None:
            db.add(
                User(
                    usuario=usuario,
                    nome=settings.admin_nome,
                    senha_hash=hash_senha(settings.admin_senha),
                    papel=Papel.ADMIN.value,
                )
            )


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    exigir_volume_de_dados()
    migracao = aplicar_migracoes()
    garantir_organizador()
    bus.registrar_loop(asyncio.get_running_loop())
    print(f"[sorteio] banco: {arquivo_sqlite() or 'servidor externo'} (revisao {migracao['atual']})")
    if migracao["aplicada"]:
        print(
            f"[sorteio] migracao aplicada: {migracao['revisao_anterior'] or '(banco novo)'} "
            f"-> {migracao['atual']}"
        )
        if migracao["backup"]:
            print(f"[sorteio] backup anterior a migracao: {migracao['backup']}")
    print(f"[sorteio] imagens em: {settings.upload_dir}")
    for aviso in avisos_de_ambiente():
        print(f"[sorteio] ATENCAO: {aviso}")
    situacao_push = push.configuracao()
    print(f"[sorteio] push no celular: {'ativo' if situacao_push.disponivel else 'inativo - ' + (situacao_push.motivo or '')}")
    tarefa_push = asyncio.create_task(_laco_push())
    yield
    tarefa_push.cancel()


async def _laco_push() -> None:
    """Envia os pushes de premio assim que o telao revela o ganhador."""
    while True:
        await asyncio.sleep(PUSH_INTERVALO_SEGUNDOS)
        try:
            await run_in_threadpool(push.enviar_pendentes)
        except Exception as exc:  # noqa: BLE001 - o laco nunca pode parar o servidor
            print(f"[sorteio] falha no envio de push: {exc}")


app = FastAPI(
    title="Sorteio da Confraternizacao",
    description="Painel do organizador e telao do evento, sincronizados por SSE.",
    version="1.0.0",
    lifespan=lifespan,
)

origens = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(auth.router)
app.include_router(eventos.router)
app.include_router(participantes.router)
app.include_router(participantes.modelos)
app.include_router(premios.router)
app.include_router(premios.modelos)
app.include_router(blocos.router)
app.include_router(sorteios.router)
app.include_router(historico.router)
app.include_router(usuarios.router)
app.include_router(recepcao.router)
app.include_router(credenciamento.router)
app.include_router(recepcao_publica.router)
app.include_router(minha_area.router)
app.include_router(autocadastro.router)
app.include_router(portal.router)
app.include_router(relatorios.router)
app.include_router(publico.router)
app.include_router(uploads.router)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.exception_handler(OperationalError)
def erro_de_banco(request: Request, exc: OperationalError) -> JSONResponse:
    """Transforma contencao de lock em uma resposta clara e repetivel.

    Nenhum sorteio e perdido: a requisicao nao chegou a gravar nada, e repetir
    com a mesma chave de idempotencia e seguro.
    """
    if "database is locked" in str(exc.orig).lower():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "O banco esta ocupado neste instante. Tente novamente em alguns segundos."
            },
        )
    raise exc


@app.get("/api/saude")
def saude() -> dict:
    return {"ok": True}


# Em producao o build do frontend e servido pelo mesmo processo (uma unica
# porta na rede local). Em desenvolvimento o Vite serve o frontend.
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str) -> FileResponse:
        arquivo = FRONTEND_DIST / caminho
        if caminho and arquivo.is_file():
            return FileResponse(arquivo)
        return FileResponse(FRONTEND_DIST / "index.html")
