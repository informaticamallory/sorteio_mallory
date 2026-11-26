"""Evento de teste (oculto no portal do colaborador)

  * events.evento_teste: desligado em todos os eventos existentes (nada muda
    ate o admin marcar). Marcado, o evento some do portal do colaborador
    (aba, premios e notificacoes), nao manda aviso nem push ao celular e sai
    da lista de cadastro pelo QR Code. Nenhum dado e apagado.

So acrescimo (ALTER TABLE ADD COLUMN).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-27

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("evento_teste", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE events DROP COLUMN evento_teste")
    else:
        op.drop_column("events", "evento_teste")
