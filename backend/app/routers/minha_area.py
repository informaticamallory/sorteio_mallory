"""Area pessoal do colaborador.

Nao recebe nenhum identificador de participante: tudo vem de
`Participant.usuario_id == usuario logado`. Assim nao existe parametro que
permita consultar os dados de outra pessoa. As notificacoes seguem a mesma
regra, e o canal em tempo real exige o token da propria conta (no cabecalho
Authorization, nunca na URL, para nao ficar em logs).
"""

from __future__ import annotations

import asyncio
import io
import json

import segno
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bus
from ..config import settings
from ..database import get_db, session_scope
from ..deps import bearer, exigir_permissao
from ..models import AuditLog, Event, InscricaoPush, Participant, User
from ..permissoes import Permissao, tem_permissao
from ..schemas import (
    CancelarPushIn,
    InscricaoPushIn,
    MinhaAreaOut,
    MinhaParticipacaoOut,
    NotificacaoOut,
    PremioGanhoOut,
    PushStatusOut,
)
from ..security import ler_token
from ..services import notificacoes as servico
from ..services import push
from ..services.autocadastro import apagar_foto, apagar_foto_se_orfa
from ..services.consultas import premios_ganhos
from ..services.elegibilidade import matricula_da_sorte
from ..services.imagens import ImagemInvalida, salvar_imagem

router = APIRouter(prefix="/api/minha-area", tags=["minha-area"])

PESSOAL = exigir_permissao(Permissao.ACESSAR_AREA_PESSOAL)
HEARTBEAT_SEGUNDOS = 20


@router.get("", response_model=MinhaAreaOut)
def minha_area(db: Session = Depends(get_db), user: User = Depends(PESSOAL)) -> MinhaAreaOut:
    linhas = db.execute(
        select(Participant, Event)
        .join(Event, Participant.event_id == Event.id)
        # Evento de teste nao aparece no portal (aba, premios, cartao).
        .where(Participant.usuario_id == user.id, Event.evento_teste.is_(False))
        .order_by(Event.criado_em.desc())
    ).all()
    ids = [p.id for p, _e in linhas]
    premios = premios_ganhos(db, ids)
    # O premio aparece junto com a revelacao no telao, nunca antes.
    em_revelacao = servico.sorteios_ainda_em_revelacao(db, ids)
    return MinhaAreaOut(
        nome=user.nome,
        usuario=user.usuario,
        notificacoes_nao_lidas=servico.nao_lidas(db, user),
        participacoes=[
            MinhaParticipacaoOut(
                evento_id=evento.id,
                evento_nome=evento.nome,
                empresa_nome=evento.empresa_nome,
                nome=p.nome,
                matricula=p.matricula,
                setor=p.setor,
                foto_url=p.foto_url,
                pulseira=p.pulseira,
                numero_sorteio=p.numero_sorteio,
                matricula_da_sorte=matricula_da_sorte(evento, p),
                presente=p.presente,
                participando=p.participando,
                premios=[
                    PremioGanhoOut(**item)
                    for item in premios.get(p.id, [])
                    if item["sorteio_id"] not in em_revelacao
                ],
            )
            for p, evento in linhas
        ],
    )


# ------------------------------------------------------------------ notificacoes
@router.get("/notificacoes", response_model=list[NotificacaoOut])
def notificacoes(db: Session = Depends(get_db), user: User = Depends(PESSOAL)) -> list[NotificacaoOut]:
    return [NotificacaoOut(**n) for n in servico.listar(db, user)]


@router.post("/notificacoes/lidas")
def marcar_todas_como_lidas(db: Session = Depends(get_db), user: User = Depends(PESSOAL)) -> dict:
    marcadas = servico.marcar_todas(db, user)
    db.commit()
    return {"marcadas": marcadas, "nao_lidas": 0}


@router.post("/notificacoes/{notificacao_id}/lida")
def marcar_como_lida(
    notificacao_id: int, db: Session = Depends(get_db), user: User = Depends(PESSOAL)
) -> dict:
    # Notificacao de outra pessoa responde igual a inexistente.
    if not servico.marcar_lida(db, user, notificacao_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificação não encontrada")
    db.commit()
    return {"nao_lidas": servico.nao_lidas(db, user)}


# ------------------------------------------------------------------ foto (Meu Perfil)
def _minha_participacao(db: Session, user: User, evento_id: int) -> Participant:
    """Cadastro do PROPRIO usuario no evento; de outra pessoa responde igual a inexistente."""
    participante = db.scalar(
        select(Participant).where(Participant.event_id == evento_id, Participant.usuario_id == user.id)
    )
    if participante is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cadastro não encontrado")
    return participante


@router.post("/{evento_id}/foto", response_model=MinhaParticipacaoOut)
def trocar_foto(
    evento_id: int,
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(PESSOAL),
) -> MinhaParticipacaoOut:
    participante = _minha_participacao(db, user, evento_id)
    conteudo = foto.file.read(settings.max_upload_bytes + 1)
    if len(conteudo) > settings.max_upload_bytes:
        limite = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Foto maior que {limite} MB")
    try:
        nova = salvar_imagem(conteudo, foto.filename or "")
    except ImagemInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    anterior = participante.foto_url
    participante.foto_url = nova
    db.add(
        AuditLog(
            event_id=evento_id,
            usuario_id=user.id,
            acao="foto_alterada",
            detalhes={"participante_id": participante.id, "origem": "portal", "operacao": "troca"},
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        apagar_foto(nova)
        raise
    apagar_foto_se_orfa(db, anterior)
    return _participacao(db, user, evento_id)


@router.delete("/{evento_id}/foto", response_model=MinhaParticipacaoOut)
def remover_foto(
    evento_id: int, db: Session = Depends(get_db), user: User = Depends(PESSOAL)
) -> MinhaParticipacaoOut:
    participante = _minha_participacao(db, user, evento_id)
    anterior = participante.foto_url
    if anterior:
        participante.foto_url = None
        db.add(
            AuditLog(
                event_id=evento_id,
                usuario_id=user.id,
                acao="foto_alterada",
                detalhes={"participante_id": participante.id, "origem": "portal", "operacao": "remocao"},
            )
        )
        db.commit()
        apagar_foto_se_orfa(db, anterior)
    return _participacao(db, user, evento_id)


def _participacao(db: Session, user: User, evento_id: int) -> MinhaParticipacaoOut:
    area = minha_area(db, user)
    for item in area.participacoes:
        if item.evento_id == evento_id:
            return item
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Cadastro não encontrado")


@router.get("/{evento_id}/qrcode.png")
def qrcode_cartao(
    evento_id: int, db: Session = Depends(get_db), user: User = Depends(PESSOAL)
) -> Response:
    """QR Code do Cartao da Sorte, lido na Central de Entregas.

    Contem so o evento e o numero da sorte (MALLORY-SORTE:<evento>:<numero>):
    nada de CPF, nascimento ou matricula. Nao prova identidade: o atendente
    sempre confere a pessoa.
    """
    participante = _minha_participacao(db, user, evento_id)
    if participante.numero_sorteio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Seu número da sorte ainda não foi atribuído")
    codigo = segno.make(f"MALLORY-SORTE:{evento_id}:{participante.numero_sorteio}", error="m")
    buffer = io.BytesIO()
    codigo.save(buffer, kind="png", scale=8, border=3, dark="#111111", light="#FFFFFF")
    return Response(content=buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "private, no-store"})


# ------------------------------------------------------------------ push (PWA)
@router.get("/push", response_model=PushStatusOut)
def situacao_push(db: Session = Depends(get_db), user: User = Depends(PESSOAL)) -> PushStatusOut:
    cfg = push.configuracao()
    aparelhos = db.scalar(
        select(func.count(InscricaoPush.id)).where(InscricaoPush.usuario_id == user.id)
    ) or 0
    return PushStatusOut(
        disponivel=cfg.disponivel, chave_publica=cfg.chave_publica, motivo=cfg.motivo, aparelhos=aparelhos
    )


@router.post("/push/inscricao", response_model=PushStatusOut)
def inscrever_push(
    dados: InscricaoPushIn, db: Session = Depends(get_db), user: User = Depends(PESSOAL)
) -> PushStatusOut:
    if not push.configuracao().disponivel:
        raise HTTPException(status.HTTP_409_CONFLICT, "Notificações no celular não estão ativas no servidor")
    push.inscrever(db, user.id, dados.endpoint, dados.p256dh, dados.auth)
    db.add(AuditLog(usuario_id=user.id, acao="push_ativado", detalhes={}))
    db.commit()
    return situacao_push(db, user)


@router.post("/push/cancelar", response_model=PushStatusOut)
def cancelar_push(
    dados: CancelarPushIn, db: Session = Depends(get_db), user: User = Depends(PESSOAL)
) -> PushStatusOut:
    if push.cancelar(db, user.id, dados.endpoint):
        db.add(AuditLog(usuario_id=user.id, acao="push_desativado", detalhes={}))
    db.commit()
    return situacao_push(db, user)


# ------------------------------------------------------------------ canal privado
def verificar_sessao(token: str | None) -> tuple[int, int | None]:
    """(codigo_http, user_id): as mesmas regras de deps.usuario_liberado + permissao."""
    lido = ler_token(token) if token else None
    if lido is None:
        return 401, None
    user_id, versao = lido
    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.ativo or user.sessao_versao != versao:
            return 401, None
        if user.deve_trocar_senha or not tem_permissao(user, Permissao.ACESSAR_AREA_PESSOAL):
            return 403, None
        return 200, user.id


async def eventos_privados(
    fila: asyncio.Queue,
    desconectado: Callable[[], Awaitable[bool]],
    sessao_valida: Callable[[], Awaitable[bool]],
    heartbeat: float = HEARTBEAT_SEGUNDOS,
) -> AsyncIterator[str]:
    """Gerador do SSE privado. A cada intervalo sem mensagem, reconfere a sessao:
    conta desativada ou sessao encerrada derrubam o canal."""
    yield f"data: {json.dumps({'tipo': 'pronto'})}\n\n"
    while True:
        if await desconectado():
            return
        try:
            mensagem = await asyncio.wait_for(fila.get(), timeout=heartbeat)
        except asyncio.TimeoutError:
            if not await sessao_valida():
                yield f"data: {json.dumps({'tipo': 'sessao_encerrada'})}\n\n"
                return
            yield ": ping\n\n"
            continue
        yield f"data: {mensagem}\n\n"


@router.get("/stream")
async def stream(
    request: Request, credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> StreamingResponse:
    token = credenciais.credentials if credenciais else None
    codigo, user_id = await run_in_threadpool(verificar_sessao, token)
    if user_id is None:
        mensagem = (
            "Seu perfil não tem permissão para esta operação"
            if codigo == 403
            else "Sessão inválida ou expirada"
        )
        raise HTTPException(codigo, mensagem)

    chave = bus.canal_usuario(user_id)
    fila = bus.assinar(chave)

    async def ainda_valida() -> bool:
        return (await run_in_threadpool(verificar_sessao, token))[1] == user_id

    async def gerador() -> AsyncIterator[str]:
        try:
            async for parte in eventos_privados(fila, request.is_disconnected, ainda_valida):
                yield parte
        finally:
            bus.cancelar(chave, fila)

    return StreamingResponse(
        gerador(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
