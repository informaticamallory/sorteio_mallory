"""Recepcao sem login (check-in e consulta) passa a depender de uma chave por evento

  * events.recepcao_publica_ativa: desligada (inclusive nos eventos existentes).
    O admin ou o organizador liga em Configuracao quando a recepcao comecar.

Nenhum dado existente e alterado.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("recepcao_publica_ativa", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE events DROP COLUMN recepcao_publica_ativa")
    else:
        op.drop_column("events", "recepcao_publica_ativa")
