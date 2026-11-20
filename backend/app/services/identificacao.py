"""Identificacao do colaborador por data de nascimento + 5 primeiros digitos do CPF.

LGPD: o CPF e a data de nascimento nunca sao gravados nem registrados em log.
A importacao calcula dois codigos HMAC-SHA256 com uma chave secreta:

  * identificacao_hash = HMAC(nascimento | 5 primeiros digitos do CPF)
    -> confere a identidade no primeiro acesso ao portal;
  * cpf_hash = HMAC(CPF completo) -> impede o mesmo CPF em duas matriculas.

Sem a chave os codigos nao revelam nada. Com a chave, os 5 digitos tem poucas
combinacoes: por isso estes dados NAO sao autenticacao forte. Servem so para o
primeiro acesso (com limite de tentativas); depois o colaborador usa a senha.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, timedelta
from functools import lru_cache

from ..config import DATA_DIR, settings

ARQUIVO_CHAVE = DATA_DIR / "chave-identificacao.key"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@lru_cache(maxsize=1)
def _chave() -> bytes:
    if settings.chave_identificacao:
        return settings.chave_identificacao.encode("utf-8")
    if not ARQUIVO_CHAVE.exists():
        ARQUIVO_CHAVE.write_text(secrets.token_hex(32), encoding="ascii")
    return ARQUIVO_CHAVE.read_text(encoding="ascii").strip().encode("ascii")


def _hmac(texto: str) -> str:
    return hmac.new(_chave(), texto.encode("utf-8"), hashlib.sha256).hexdigest()


def codigo_valido(valor: str | None) -> bool:
    return bool(valor) and bool(_HEX64.match(valor))


# ------------------------------------------------------------------ CPF
def _digitos_verificadores_ok(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def normalizar_cpf(valor: str | None) -> str | None:
    """11 digitos com digitos verificadores validos, ou None.

    Aceita pontuacao ("123.456.789-09") e CPF que o Excel guardou como numero,
    perdendo os zeros a esquerda ("1234567890" -> "01234567890").
    """
    digitos = re.sub(r"\D", "", str(valor or ""))
    if 8 <= len(digitos) < 11:
        digitos = digitos.zfill(11)
    return digitos if _digitos_verificadores_ok(digitos) else None


def cinco_digitos_validos(valor: str | None) -> str | None:
    texto = (valor or "").strip()
    return texto if re.fullmatch(r"\d{5}", texto) else None


# ------------------------------------------------------------------ nascimento
_EXCEL_ORIGEM = date(1899, 12, 30)


def normalizar_nascimento(valor) -> date | None:  # noqa: ANN001
    """Data de nascimento plausivel, ou None.

    Aceita date/datetime (celula de data do Excel), "dd/mm/aaaa", "aaaa-mm-dd",
    "aaaa-mm-dd hh:mm:ss" e o numero serial do Excel (celula sem formato de data).
    Ano com 2 digitos e recusado (seria ambiguo).
    """
    data: date | None = None
    if isinstance(valor, datetime):
        data = valor.date()
    elif isinstance(valor, date):
        data = valor
    else:
        texto = str(valor or "").strip()
        if not texto:
            return None
        if re.fullmatch(r"\d{4,5}(\.0+)?", texto):
            data = _EXCEL_ORIGEM + timedelta(days=int(float(texto)))
        else:
            for formato in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%d.%m.%Y"):
                try:
                    data = datetime.strptime(texto, formato).date()
                    break
                except ValueError:
                    continue
    if data is None:
        return None
    hoje = date.today()
    if data.year < 1900 or data > hoje:
        return None
    return data


# ------------------------------------------------------------------ codigos
def codigo_identificacao(nascimento: date, cinco_digitos: str) -> str:
    return _hmac(f"identificacao|{nascimento.isoformat()}|{cinco_digitos}")


def codigo_cpf(cpf: str) -> str:
    return _hmac(f"cpf|{cpf}")


def confere(armazenado: str | None, nascimento: date, cinco_digitos: str) -> bool:
    """Compara em tempo constante. Sem codigo armazenado, nunca confere."""
    calculado = codigo_identificacao(nascimento, cinco_digitos)
    return hmac.compare_digest(armazenado or "0" * 64, calculado) and armazenado is not None
