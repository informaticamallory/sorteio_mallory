"""Exclusao de bloco que ja teve sorteio, sem perder o historico

  * blocos_sorteio.excluido_em: preenchido quando o admin exclui um bloco que
    tem resultados. O bloco some da gestao de blocos, mas os sorteios continuam
    apontando para ele (historico e relatorio seguem mostrando o bloco).
    Blocos sem nenhum sorteio continuam sendo apagados de verdade.

Nenhum dado existente e alterado.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-23

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("blocos_sorteio", sa.Column("excluido_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE blocos_sorteio DROP COLUMN excluido_em")
    else:
        op.drop_column("blocos_sorteio", "excluido_em")
