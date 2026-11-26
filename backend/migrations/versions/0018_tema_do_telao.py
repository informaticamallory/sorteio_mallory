"""Tema do telao por evento

  * events.tema_telao: "classico" (o visual atual, com as cores do evento) ou
    "mallory_claro" (modelo claro da Mallory). Todos os eventos existentes
    ficam no "classico": nada muda no telao ate alguem escolher o tema novo.

Coluna nova com CHECK, criada com ALTER TABLE ADD COLUMN (sem recriar a tabela
events). Nenhum dado existente e alterado.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-26

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "tema_telao IN ('classico', 'mallory_claro')"


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE events ADD COLUMN tema_telao VARCHAR(20) NOT NULL DEFAULT 'classico' "
            f"CONSTRAINT ck_events_tema_telao CHECK ({CHECK})"
        )
    else:
        op.add_column(
            "events",
            sa.Column("tema_telao", sa.String(length=20), nullable=False, server_default="classico"),
        )
        op.create_check_constraint("ck_events_tema_telao", "events", CHECK)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE events DROP COLUMN tema_telao")
    else:
        op.drop_constraint("ck_events_tema_telao", "events", type_="check")
        op.drop_column("events", "tema_telao")
