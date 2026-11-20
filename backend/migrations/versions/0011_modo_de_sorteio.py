"""Modo de sorteio por evento: numero da sorte (padrao) ou faixa de matriculas

  * events.modo_sorteio ("numero_sorte" nos eventos existentes: nada muda);
  * events.matricula_faixa_inicio / matricula_faixa_fim (vazias).

Nenhum dado existente e alterado.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUNAS = ("matricula_faixa_fim", "matricula_faixa_inicio", "modo_sorteio")


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("modo_sorteio", sa.String(length=20), nullable=False, server_default="numero_sorte"),
    )
    op.add_column("events", sa.Column("matricula_faixa_inicio", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("matricula_faixa_fim", sa.Integer(), nullable=True))


def downgrade() -> None:
    for coluna in COLUNAS:
        if op.get_bind().dialect.name == "sqlite":
            op.execute(f"ALTER TABLE events DROP COLUMN {coluna}")
        else:
            op.drop_column("events", coluna)
