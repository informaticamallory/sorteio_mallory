"""Gerenciador de blocos: descricao opcional do bloco

  * blocos_sorteio.descricao (texto opcional, vazio nos blocos existentes).

Nenhum dado existente e alterado.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("blocos_sorteio", sa.Column("descricao", sa.Text(), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE blocos_sorteio DROP COLUMN descricao")
    else:
        op.drop_column("blocos_sorteio", "descricao")
