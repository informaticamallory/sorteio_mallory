"""fase 4: sessao, ultimo acesso e protecao de login

Colunas em users: sessao_versao, ultimo_acesso_em, tentativas_falhas,
bloqueado_ate, deve_trocar_senha, senha_alterada_em.

As contas existentes sao preservadas como estao: mesma senha, mesmo papel,
nenhuma troca de senha obrigatoria. Somente acrescimos.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUNAS = (
    sa.Column("sessao_versao", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("ultimo_acesso_em", sa.DateTime(), nullable=True),
    sa.Column("tentativas_falhas", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("bloqueado_ate", sa.DateTime(), nullable=True),
    sa.Column("deve_trocar_senha", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("senha_alterada_em", sa.DateTime(), nullable=True),
)


def upgrade() -> None:
    for coluna in COLUNAS:
        op.add_column("users", coluna.copy())


def downgrade() -> None:
    for coluna in reversed(COLUNAS):
        if op.get_bind().dialect.name == "sqlite":
            op.execute(f"ALTER TABLE users DROP COLUMN {coluna.name}")
        else:
            op.drop_column("users", coluna.name)
