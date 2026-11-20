from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Path, status
from fastapi.params import Depends as DependsParam
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Event, Papel, User
from .permissoes import PAPEIS_INTERNOS, Permissao, tem_alguma_permissao, tem_permissao
from .security import ler_token

bearer = HTTPBearer(auto_error=False)

TROCA_DE_SENHA_OBRIGATORIA = "Troque a senha temporária antes de continuar."


def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Autenticacao: token valido, conta ativa e sessao ainda nao encerrada.

    O papel e lido do banco a cada requisicao (nao do token): uma mudanca de
    perfil vale na hora. Desativar, trocar perfil ou redefinir a senha
    incrementa `sessao_versao`, o que invalida os tokens emitidos antes.
    """
    if credenciais is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticação necessária")
    lido = ler_token(credenciais.credentials)
    if lido is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada")
    user_id, versao = lido
    user = db.get(User, user_id)
    if user is None or not user.ativo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada")
    if versao != user.sessao_versao:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão encerrada. Entre novamente.")
    return user


def usuario_liberado(user: User = Depends(usuario_atual)) -> User:
    """Autenticado e sem senha temporaria pendente de troca."""
    if user.deve_trocar_senha:
        raise HTTPException(status.HTTP_403_FORBIDDEN, TROCA_DE_SENHA_OBRIGATORIA)
    return user


def _negar() -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN, "Seu perfil não tem permissão para esta operação"
    )


def exigir_permissao(*necessarias: Permissao) -> Callable[..., User]:
    """Dependencia que exige TODAS as permissoes informadas (ver app/permissoes.py)."""

    def dependencia(user: User = Depends(usuario_liberado)) -> User:
        if not tem_permissao(user, *necessarias):
            raise _negar()
        return user

    return dependencia


def exigir_alguma_permissao(*opcoes: Permissao) -> Callable[..., User]:
    """Dependencia que exige AO MENOS UMA das permissoes informadas."""

    def dependencia(user: User = Depends(usuario_liberado)) -> User:
        if not tem_alguma_permissao(user, *opcoes):
            raise _negar()
        return user

    return dependencia


def requer(*permissoes: Permissao, alguma: bool = False) -> list[DependsParam]:
    """Atalho para `dependencies=` de rotas que nao usam o usuario no corpo."""
    if alguma:
        return [Depends(exigir_alguma_permissao(*permissoes))]
    return [Depends(exigir_permissao(*permissoes))]


def exigir_papel(*papeis: Papel) -> Callable[..., User]:
    aceitos = {p.value for p in papeis}

    def dependencia(user: User = Depends(usuario_liberado)) -> User:
        if user.papel not in aceitos:
            raise _negar()
        return user

    return dependencia


# Equipe do evento (todos menos COLABORADOR). Toda rota de evento passa por
# aqui alem da permissao especifica: defesa em profundidade, caso uma rota
# nova seja criada sem declarar permissao.
usuario_interno = exigir_papel(*PAPEIS_INTERNOS)


def evento_atual(
    event_id: int = Path(..., description="ID do evento"),
    db: Session = Depends(get_db),
    _: User = Depends(usuario_interno),
) -> Event:
    evento = db.get(Event, event_id)
    if evento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento não encontrado")
    return evento
