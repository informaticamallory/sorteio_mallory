"""Cores proprias do tema "Mallory claro"

  * events.claro_cor_fundo / claro_cor_painel / claro_cor_destaque /
    claro_cor_texto: as quatro cores do telao claro, separadas das cores do
    classico. Todos os eventos comecam na paleta Mallory (#eeeeee, #dddddd,
    #ff5d1d, #606060), que e o que o tema ja mostrava.

So acrescimos (ALTER TABLE ADD COLUMN). Nenhum dado existente e alterado.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-26

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORES = (
    ("claro_cor_fundo", "#eeeeee"),
    ("claro_cor_painel", "#dddddd"),
    ("claro_cor_destaque", "#ff5d1d"),
    ("claro_cor_texto", "#606060"),
)


def upgrade() -> None:
    for coluna, padrao in CORES:
        op.add_column("events", sa.Column(coluna, sa.String(length=20), nullable=False, server_default=padrao))


def downgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    for coluna, _padrao in reversed(CORES):
        if sqlite:
            op.execute(f"ALTER TABLE events DROP COLUMN {coluna}")
        else:
            op.drop_column("events", coluna)
