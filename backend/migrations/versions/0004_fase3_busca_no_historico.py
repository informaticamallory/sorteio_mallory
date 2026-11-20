"""fase 3: busca no historico

participants.nome_busca e prizes.nome_busca: o nome sem acentos, em
minusculas, para a pesquisa funcionar igual no SQLite e no PostgreSQL (o
SQLite nao tem funcao para remover acentos). Os registros existentes sao
preenchidos aqui; os novos, pelo ORM (models._manter_nome_busca).

Somente acrescimos; nenhum dado existente e alterado.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13

"""
from __future__ import annotations

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABELAS = ("participants", "prizes")


def _normalizar(texto: str | None) -> str:
    # Copia congelada de app.texto.normalizar_busca: a migracao nao pode
    # mudar de comportamento se o codigo do app mudar depois.
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def upgrade() -> None:
    conexao = op.get_bind()
    for tabela in TABELAS:
        op.add_column(
            tabela,
            sa.Column("nome_busca", sa.String(length=200), nullable=False, server_default=""),
        )
        linhas = conexao.execute(sa.text(f"SELECT id, nome FROM {tabela}")).fetchall()
        for linha_id, nome in linhas:
            conexao.execute(
                sa.text(f"UPDATE {tabela} SET nome_busca = :valor WHERE id = :id"),
                {"valor": _normalizar(nome), "id": linha_id},
            )


def downgrade() -> None:
    for tabela in TABELAS:
        if op.get_bind().dialect.name == "sqlite":
            op.execute(f"ALTER TABLE {tabela} DROP COLUMN nome_busca")
        else:
            op.drop_column(tabela, "nome_busca")
