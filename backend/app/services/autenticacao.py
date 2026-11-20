"""Login com protecao contra tentativas repetidas.

Duas camadas:
  * por conta (persistida no banco): N falhas seguidas bloqueiam a conta por
    alguns minutos, mesmo com a senha certa;
  * em memoria, por IP (soma de todas as contas) e por nome de usuario
    inexistente. A segunda faz um usuario inexistente se comportar igual a um
    existente, para que o bloqueio nao revele quais contas existem.

Respostas: 401 com mensagem unica para usuario inexistente, senha errada ou
conta inativa; 429 quando ha bloqueio. O limitador em memoria vale para um
processo (o deploy do evento e um processo so) e zera ao reiniciar; o bloqueio
por conta, no banco, nao zera.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuditLog, Papel, Participant, User, utcnow
from ..security import gastar_tempo_de_verificacao, verificar_senha
from ..texto import normalizar_matricula
from .erros import RegraDeNegocio

MENSAGEM_CREDENCIAIS = "Usuário ou senha inválidos"
MENSAGEM_BLOQUEIO = "Muitas tentativas de login. Aguarde alguns minutos e tente novamente."


class Limitador:
    """Contador de falhas por chave dentro de uma janela de tempo."""

    def __init__(self) -> None:
        self._falhas: dict[str, deque[float]] = defaultdict(deque)
        self._trava = threading.Lock()

    def _janela(self) -> float:
        return settings.login_bloqueio_minutos * 60

    def _contar(self, chave: str, agora: float) -> int:
        fila = self._falhas[chave]
        while fila and agora - fila[0] > self._janela():
            fila.popleft()
        return len(fila)

    def excedeu(self, chave: str, limite: int) -> bool:
        with self._trava:
            return self._contar(chave, time.monotonic()) >= limite

    def registrar(self, *chaves: str) -> None:
        with self._trava:
            agora = time.monotonic()
            for chave in chaves:
                self._contar(chave, agora)
                self._falhas[chave].append(agora)

    def limpar(self) -> None:
        with self._trava:
            self._falhas.clear()


limitador = Limitador()


def _chave_ip(ip: str) -> str:
    return f"ip:{ip}"


def _chave_usuario(usuario: str) -> str:
    return f"usuario:{usuario}"


def autenticar(db: Session, usuario: str, senha: str, ip: str) -> User:
    login = usuario.strip().lower()
    if limitador.excedeu(_chave_ip(ip), settings.login_max_falhas_ip):
        raise RegraDeNegocio(MENSAGEM_BLOQUEIO, 429)

    user = db.scalar(select(User).where(User.usuario == login))
    if user is None:
        user = _colaborador_por_matricula(db, login)
    agora = utcnow()

    if user is None:
        gastar_tempo_de_verificacao(senha)
        if limitador.excedeu(_chave_usuario(login), settings.login_max_falhas_conta):
            raise RegraDeNegocio(MENSAGEM_BLOQUEIO, 429)
        limitador.registrar(_chave_ip(ip), _chave_usuario(login))
        raise RegraDeNegocio(MENSAGEM_CREDENCIAIS, 401)

    if user.bloqueado_ate is not None and user.bloqueado_ate > agora:
        gastar_tempo_de_verificacao(senha)
        limitador.registrar(_chave_ip(ip))
        raise RegraDeNegocio(MENSAGEM_BLOQUEIO, 429)

    if not verificar_senha(senha, user.senha_hash) or not user.ativo:
        registrar_falha(db, user)
        limitador.registrar(_chave_ip(ip))
        db.commit()
        raise RegraDeNegocio(MENSAGEM_CREDENCIAIS, 401)

    user.tentativas_falhas = 0
    user.bloqueado_ate = None
    user.ultimo_acesso_em = agora
    db.add(AuditLog(usuario_id=user.id, acao="login", detalhes={"ip": ip}))
    db.commit()
    return user


def _colaborador_por_matricula(db: Session, login: str) -> User | None:
    """Colaborador digitou a matricula sem os zeros ("26" para "00026").

    So para matricula numerica e so quando ela leva a UMA unica conta de
    colaborador; senao o login segue como inexistente (mesma resposta).
    """
    normalizada = normalizar_matricula(login)
    if not login or not normalizada.isdigit():
        return None
    ids = set(
        db.scalars(
            select(Participant.usuario_id).where(
                Participant.matricula_normalizada == normalizada, Participant.usuario_id.is_not(None)
            )
        ).all()
    )
    if len(ids) != 1:
        return None
    user = db.get(User, ids.pop())
    if user is None or user.papel != Papel.COLABORADOR.value:
        return None
    return user


def registrar_falha(db: Session, user: User) -> None:
    """Conta uma senha errada; na N-esima seguida, bloqueia a conta."""
    user.tentativas_falhas += 1
    if user.tentativas_falhas >= settings.login_max_falhas_conta:
        user.bloqueado_ate = utcnow() + timedelta(minutes=settings.login_bloqueio_minutos)
        user.tentativas_falhas = 0
        db.add(
            AuditLog(
                usuario_id=user.id,
                acao="login_bloqueado",
                detalhes={"minutos": settings.login_bloqueio_minutos},
            )
        )
