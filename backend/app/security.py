from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

_ITERACOES = 240_000


def hash_senha(senha: str) -> str:
    """PBKDF2-SHA256 (stdlib) - evita dependencia nativa (bcrypt/argon2) no Windows."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, _ITERACOES)
    return f"pbkdf2_sha256${_ITERACOES}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        algoritmo, iteracoes, salt_b64, dk_b64 = armazenado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(dk_b64)
        calculado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, int(iteracoes))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


# Hash de referencia: login de usuario inexistente gasta o mesmo tempo que um
# login com senha errada, para o tempo de resposta nao revelar quais contas existem.
_HASH_FICTICIO = hash_senha(secrets.token_hex(16))


def gastar_tempo_de_verificacao(senha: str) -> None:
    verificar_senha(senha, _HASH_FICTICIO)


def criar_token(user_id: int, sessao_versao: int = 1) -> str:
    """JWT com a versao da sessao: incrementa-la no usuario derruba tokens antigos."""
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expira_minutos)
    payload = {"sub": str(user_id), "ver": sessao_versao, "exp": expira}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def ler_token(token: str) -> tuple[int, int] | None:
    """(user_id, versao_da_sessao). Tokens anteriores a Fase 4, sem "ver", contam como 1."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        # Outros tipos de token (ex.: passe do cadastro) nunca valem como sessao.
        if "typ" in payload:
            return None
        return int(payload["sub"]), int(payload.get("ver", 1))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def criar_passe_cadastro(evento_id: int, participante_id: int) -> str:
    """Passe curto entre "identificar" e "confirmar cadastro" no Portal.

    Nao e sessao: nao abre a area pessoal nem rota alguma alem da conclusao do
    proprio cadastro, e vence em poucos minutos. Evita reenviar CPF e
    nascimento a cada passo.
    """
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.cadastro_passe_minutos)
    payload = {"sub": str(participante_id), "evt": evento_id, "typ": "cadastro", "exp": expira}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def ler_passe_cadastro(passe: str) -> tuple[int, int] | None:
    """(evento_id, participante_id) de um passe valido, ou None."""
    try:
        payload = jwt.decode(passe, settings.secret_key, algorithms=["HS256"])
        if payload.get("typ") != "cadastro":
            return None
        return int(payload["evt"]), int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


_ALFABETO_SENHA ="abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def gerar_senha_temporaria() -> str:
    """12 caracteres sem ambiguos (0/O, 1/l/I), com letras e numeros garantidos."""
    while True:
        senha = "".join(secrets.choice(_ALFABETO_SENHA) for _ in range(12))
        if any(c.isdigit() for c in senha) and any(c.isalpha() for c in senha):
            return senha


def problema_na_senha(senha: str, usuario: str) -> str | None:
    """Politica minima de senha. Devolve o motivo da recusa, ou None."""
    if len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    if len(senha) > 128:
        return "A senha pode ter no máximo 128 caracteres."
    if not any(c.isalpha() for c in senha) or not any(c.isdigit() for c in senha):
        return "A senha precisa ter letras e números."
    if usuario and usuario.lower() in senha.lower():
        return "A senha não pode conter o nome de usuário."
    return None


def novo_token_telao() -> str:
    return secrets.token_urlsafe(18)
