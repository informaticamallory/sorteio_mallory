"""Subtitulo do telao (tema "Mallory claro")

  * events.telao_subtitulo: texto ao lado da logo no telao claro, por evento
    (ex.: "Sorteio de aniversario de 52 anos"). Vazio em todos os eventos
    existentes, que continuam mostrando "Sorteios internos".

So acrescimo (ALTER TABLE ADD COLUMN). Nenhum dado existente e alterado.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-26

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("telao_subtitulo", sa.String(length=80), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE events DROP COLUMN telao_subtitulo")
    else:
        op.drop_column("events", "telao_subtitulo")
