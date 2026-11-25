"""Tempo de cada ganhador no carrossel: minimo de 1 segundo (antes 5)

  * events.carrossel_segundos: o CHECK passa de ">= 5" para ">= 1". No SQLite
    a coluna e copiada, removida (DROP COLUMN nativo) e criada de novo com o
    CHECK novo, sem recriar a tabela events (mesmo metodo da 0007). O valor de
    cada evento e mantido.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-25

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _trocar_minimo(minimo: int) -> None:
    if _sqlite():
        op.execute("ALTER TABLE events ADD COLUMN carrossel_segundos_migracao INTEGER")
        op.execute("UPDATE events SET carrossel_segundos_migracao = carrossel_segundos")
        op.execute("ALTER TABLE events DROP COLUMN carrossel_segundos")
        op.execute(
            "ALTER TABLE events ADD COLUMN carrossel_segundos INTEGER NOT NULL DEFAULT 6 "
            f"CONSTRAINT ck_events_carrossel_minimo CHECK (carrossel_segundos >= {minimo})"
        )
        # Ao voltar para 5, quem estava abaixo sobe para 5 (o CHECK antigo exige).
        op.execute(
            f"UPDATE events SET carrossel_segundos = MAX({minimo}, COALESCE(carrossel_segundos_migracao, 6))"
        )
        op.execute("ALTER TABLE events DROP COLUMN carrossel_segundos_migracao")
    else:
        op.drop_constraint("ck_events_carrossel_minimo", "events", type_="check")
        op.execute(f"UPDATE events SET carrossel_segundos = GREATEST({minimo}, carrossel_segundos)")
        op.create_check_constraint("ck_events_carrossel_minimo", "events", f"carrossel_segundos >= {minimo}")


def upgrade() -> None:
    _trocar_minimo(1)


def downgrade() -> None:
    _trocar_minimo(5)
