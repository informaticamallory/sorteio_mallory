"""Som do sorteio por evento

  * events.som_sorteio: "tambores" (o rufar atual) ou "caca_niquel" (tec-tec
    dos rolos, um clac a cada rolo que para, campainha e moedas). Todos os
    eventos existentes ficam com "tambores": nada muda ate alguem escolher.

Coluna nova com CHECK, criada com ALTER TABLE ADD COLUMN (sem recriar a tabela
events, como na 0018). Nenhum dado existente e alterado.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-27

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "som_sorteio IN ('tambores', 'caca_niquel')"


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE events ADD COLUMN som_sorteio VARCHAR(20) NOT NULL DEFAULT 'tambores' "
            f"CONSTRAINT ck_events_som_sorteio CHECK ({CHECK})"
        )
    else:
        op.add_column(
            "events",
            sa.Column("som_sorteio", sa.String(length=20), nullable=False, server_default="tambores"),
        )
        op.create_check_constraint("ck_events_som_sorteio", "events", CHECK)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE events DROP COLUMN som_sorteio")
    else:
        op.drop_constraint("ck_events_som_sorteio", "events", type_="check")
        op.drop_column("events", "som_sorteio")
