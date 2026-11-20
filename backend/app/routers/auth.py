from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from ..database import get_db
from ..deps import usuario_atual
from ..models import AuditLog, Participant, User, utcnow
from ..permissoes import permissoes_do_usuario
from ..schemas import LoginIn, LoginOut, TrocarSenhaIn, UsuarioOut
from ..security import criar_token, hash_senha, problema_na_senha, verificar_senha
from ..services.autenticacao import MENSAGEM_CREDENCIAIS, autenticar, limitador, registrar_falha
from ..services.erros import RegraDeNegocio

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def usuario_out(user: User) -> UsuarioOut:
    saida = UsuarioOut.model_validate(user)
    saida.permissoes = sorted(p.value for p in permissoes_do_usuario(user))
    sessao = object_session(user)
    if sessao is not None:
        saida.tem_cartao = (
            sessao.scalar(select(Participant.id).where(Participant.usuario_id == user.id).limit(1)) is not None
        )
    return saida


@router.post("/login", response_model=LoginOut)
def login(dados: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    try:
        user = autenticar(db, dados.usuario, dados.senha, _ip(request))
    except RegraDeNegocio as exc:
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    return LoginOut(
        access_token=criar_token(user.id, user.sessao_versao), usuario=usuario_out(user)
    )


@router.get("/me", response_model=UsuarioOut)
def me(user: User = Depends(usuario_atual)) -> UsuarioOut:
    return usuario_out(user)


@router.post("/trocar-senha", response_model=LoginOut)
def trocar_senha(
    dados: TrocarSenhaIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(usuario_atual),
) -> LoginOut:
    """Troca a propria senha (obrigatoria apos senha temporaria).

    Encerra as sessoes dos outros aparelhos e devolve um token novo para este.
    Senha atual errada conta como tentativa de login (mesmo bloqueio).
    """
    if not verificar_senha(dados.senha_atual, user.senha_hash):
        registrar_falha(db, user)
        limitador.registrar(f"ip:{_ip(request)}")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MENSAGEM_CREDENCIAIS)
    problema = problema_na_senha(dados.senha_nova, user.usuario)
    if problema:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problema)
    if verificar_senha(dados.senha_nova, user.senha_hash):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A nova senha precisa ser diferente da atual."
        )

    user.senha_hash = hash_senha(dados.senha_nova)
    user.deve_trocar_senha = False
    user.senha_alterada_em = utcnow()
    user.sessao_versao += 1
    db.add(AuditLog(usuario_id=user.id, acao="senha_alterada", detalhes={"usuario_alvo_id": user.id}))
    db.commit()
    db.refresh(user)
    return LoginOut(
        access_token=criar_token(user.id, user.sessao_versao), usuario=usuario_out(user)
    )


@router.post("/encerrar-sessoes", response_model=LoginOut)
def encerrar_minhas_sessoes(
    db: Session = Depends(get_db), user: User = Depends(usuario_atual)
) -> LoginOut:
    """Sai de todos os outros aparelhos; este recebe um token novo."""
    user.sessao_versao += 1
    db.add(AuditLog(usuario_id=user.id, acao="sessoes_encerradas", detalhes={"usuario_alvo_id": user.id}))
    db.commit()
    db.refresh(user)
    return LoginOut(
        access_token=criar_token(user.id, user.sessao_versao), usuario=usuario_out(user)
    )
