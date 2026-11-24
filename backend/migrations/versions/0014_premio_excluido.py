"""Exclusao de premio que ja teve sorteio, sem perder o historico

  * prizes.excluido_em: preenchido quando o admin exclui um premio que tem
    resultados (validos ou anulados). O premio some da tela de Premios, mas os
    sorteios continuam apontando para ele (historico, entregas e relatorio).
    Premios sem nenhum sorteio continuam sendo apagados de verdade.

Nenhum dado existente e alterado.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prizes", sa.Column("excluido_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE prizes DROP COLUMN excluido_em")
    else:
        op.drop_column("prizes", "excluido_em")
