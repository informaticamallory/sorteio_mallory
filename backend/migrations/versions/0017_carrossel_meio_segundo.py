"""Tempo de cada ganhador no carrossel: minimo de 0,5 segundo (antes 1)

  * events.carrossel_segundos: INTEGER -> FLOAT e CHECK ">= 1" -> ">= 0.5".
  * display_states.carrossel_duracao_s: INTEGER -> FLOAT (sem CHECK).

No SQLite cada coluna e copiada, removida (DROP COLUMN nativo) e criada de
novo, sem recriar as tabelas (mesmo metodo da 0007 e da 0016). Os valores de
cada evento e de cada telao sao mantidos.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-26

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _trocar_coluna(tabela: str, coluna: str, tipo: str, extra: str, valor: str) -> None:
    """SQLite: copia, remove e recria a coluna; `valor` e a expressao do valor novo."""
    temporaria = f"{coluna}_migracao"
    op.execute(f"ALTER TABLE {tabela} ADD COLUMN {temporaria} {tipo}")
    op.execute(f"UPDATE {tabela} SET {temporaria} = {coluna}")
    op.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")
    op.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo} NOT NULL DEFAULT 6 {extra}".rstrip())
    op.execute(f"UPDATE {tabela} SET {coluna} = {valor.format(t=temporaria)}")
    op.execute(f"ALTER TABLE {tabela} DROP COLUMN {temporaria}")


def upgrade() -> None:
    if _sqlite():
        _trocar_coluna(
            "events",
            "carrossel_segundos",
            "FLOAT",
            "CONSTRAINT ck_events_carrossel_minimo CHECK (carrossel_segundos >= 0.5)",
            "COALESCE({t}, 6)",
        )
        _trocar_coluna("display_states", "carrossel_duracao_s", "FLOAT", "", "COALESCE({t}, 6)")
    else:
        op.drop_constraint("ck_events_carrossel_minimo", "events", type_="check")
        op.alter_column("events", "carrossel_segundos", type_=sa.Float(), existing_nullable=False)
        op.create_check_constraint("ck_events_carrossel_minimo", "events", "carrossel_segundos >= 0.5")
        op.alter_column("display_states", "carrossel_duracao_s", type_=sa.Float(), existing_nullable=False)


def downgrade() -> None:
    # Volta a inteiro com minimo 1: 0,5 vira 1 e fracoes sobem (1,5 -> 2).
    if _sqlite():
        _trocar_coluna(
            "events",
            "carrossel_segundos",
            "INTEGER",
            "CONSTRAINT ck_events_carrossel_minimo CHECK (carrossel_segundos >= 1)",
            "MAX(1, CAST(ROUND(COALESCE({t}, 6) + 0.49) AS INTEGER))",
        )
        _trocar_coluna(
            "display_states",
            "carrossel_duracao_s",
            "INTEGER",
            "",
            "MAX(1, CAST(ROUND(COALESCE({t}, 6) + 0.49) AS INTEGER))",
        )
    else:
        op.drop_constraint("ck_events_carrossel_minimo", "events", type_="check")
        op.execute("UPDATE events SET carrossel_segundos = GREATEST(1, CEIL(carrossel_segundos))")
        op.execute("UPDATE display_states SET carrossel_duracao_s = GREATEST(1, CEIL(carrossel_duracao_s))")
        op.alter_column("events", "carrossel_segundos", type_=sa.Integer(), existing_nullable=False)
        op.create_check_constraint("ck_events_carrossel_minimo", "events", "carrossel_segundos >= 1")
        op.alter_column("display_states", "carrossel_duracao_s", type_=sa.Integer(), existing_nullable=False)
