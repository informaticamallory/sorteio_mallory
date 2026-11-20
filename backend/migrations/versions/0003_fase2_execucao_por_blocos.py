"""fase 2: execucao por blocos

* events.capacidade_bloco_padrao (25 por padrao) para a distribuicao automatica;
* prize_units.ordem_bloco: sequencia das unidades dentro do bloco;
* indice unico parcial: no maximo um bloco EM_ANDAMENTO por evento.

Somente acrescimos; nenhuma tabela e recriada no upgrade nem no downgrade
(no SQLite usa-se ALTER TABLE ADD/DROP COLUMN nativo).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    if _sqlite():
        op.execute(
            "ALTER TABLE events ADD COLUMN capacidade_bloco_padrao INTEGER NOT NULL DEFAULT 25 "
            "CONSTRAINT ck_events_capacidade_bloco_positiva CHECK (capacidade_bloco_padrao >= 1)"
        )
    else:
        op.add_column(
            "events",
            sa.Column("capacidade_bloco_padrao", sa.Integer(), nullable=False, server_default="25"),
        )
        op.create_check_constraint(
            "ck_events_capacidade_bloco_positiva", "events", "capacidade_bloco_padrao >= 1"
        )

    op.add_column("prize_units", sa.Column("ordem_bloco", sa.Integer(), nullable=True))

    op.create_index(
        "uq_bloco_em_andamento_evento",
        "blocos_sorteio",
        ["event_id"],
        unique=True,
        sqlite_where=sa.text("status = 'EM_ANDAMENTO'"),
        postgresql_where=sa.text("status = 'EM_ANDAMENTO'"),
    )


def downgrade() -> None:
    op.drop_index("uq_bloco_em_andamento_evento", table_name="blocos_sorteio")
    if _sqlite():
        # DROP COLUMN nativo (SQLite >= 3.35): nao recria as tabelas, o que
        # preservaria mal as FKs declaradas na coluna pela revisao 0002.
        op.execute("ALTER TABLE prize_units DROP COLUMN ordem_bloco")
        op.execute("ALTER TABLE events DROP COLUMN capacidade_bloco_padrao")
    else:
        op.drop_column("prize_units", "ordem_bloco")
        op.drop_constraint("ck_events_capacidade_bloco_positiva", "events", type_="check")
        op.drop_column("events", "capacidade_bloco_padrao")
