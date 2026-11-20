from __future__ import annotations

import unicodedata


def normalizar_busca(texto: str | None) -> str:
    """Forma usada na pesquisa: sem acentos, minusculas e espacos simples.

    "José  da Conceição" -> "jose da conceicao". Gravada em colunas `nome_busca`
    para que a busca sem acento funcione igual no SQLite e no PostgreSQL.
    """
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def normalizar_matricula(texto: str | None) -> str:
    """Forma de comparacao da matricula: "00026", "026" e "26" sao a mesma.

    Maiusculas e sem espacos. Matricula so de digitos perde os zeros a
    esquerda ("000" vira "0"). Com letras ("A-0042") so muda a caixa. A
    matricula original continua gravada em `matricula`; esta forma fica em
    `matricula_normalizada`, usada em pesquisas e validacoes.
    """
    compacta = "".join((texto or "").split()).upper()
    if compacta and all(c in "0123456789" for c in compacta):
        return compacta.lstrip("0") or "0"
    return compacta


def escapar_like(texto: str) -> str:
    """Busca literal: % e _ digitados nao viram curingas do LIKE."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contem(coluna, termo: str):  # noqa: ANN001, ANN201
    """Condicao SQL "coluna contem termo", com curingas escapados."""
    return coluna.like(f"%{escapar_like(termo)}%", escape="\\")
