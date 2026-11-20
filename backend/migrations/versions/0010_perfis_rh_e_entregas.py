"""Perfis: Organizador - RH, Equipe de Entregas, setor e autorizacao para sortear

  * users.papel ganha ENTREGAS. As contas ORGANIZADOR existentes (perfil de
    entregas desde a 0007) viram ENTREGAS: ninguem ganha permissao sem o admin
    decidir. O ORGANIZADOR passa a ser o "Organizador - RH". As contas
    afetadas tem a sessao encerrada (sessao_versao + 1). Como na 0007, o CHECK
    do papel e trocado copiando a coluna, sem recriar a tabela users.
  * users.setor (texto informativo) e users.pode_sortear (falso).

Nenhuma conta, senha, historico ou auditoria e apagado. O downgrade devolve
ENTREGAS para ORGANIZADOR.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAPEIS_NOVOS = "'ADMIN', 'SORTEIO', 'ORGANIZADOR', 'RECEPCAO', 'ENTREGAS', 'COLABORADOR'"
PAPEIS_ANTIGOS = "'ADMIN', 'SORTEIO', 'ORGANIZADOR', 'RECEPCAO', 'COLABORADOR'"


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _trocar_check(papeis_validos: str, de: str | None, para: str | None) -> None:
    if de and para:
        op.execute(f"UPDATE users SET sessao_versao = sessao_versao + 1 WHERE papel = '{de}'")
    caso = f"CASE papel WHEN '{de}' THEN '{para}' ELSE papel END" if de and para else "papel"
    if _sqlite():
        op.execute("ALTER TABLE users ADD COLUMN papel_migracao VARCHAR(20)")
        op.execute(f"UPDATE users SET papel_migracao = {caso}")
        op.execute("ALTER TABLE users DROP COLUMN papel")
        op.execute(
            "ALTER TABLE users ADD COLUMN papel VARCHAR(20) NOT NULL DEFAULT 'COLABORADOR' "
            f"CONSTRAINT ck_users_papel_valido CHECK (papel IN ({papeis_validos}))"
        )
        op.execute("UPDATE users SET papel = papel_migracao")
        op.execute("ALTER TABLE users DROP COLUMN papel_migracao")
    else:
        op.drop_constraint("ck_users_papel_valido", "users", type_="check")
        op.execute(f"UPDATE users SET papel = {caso}")
        op.create_check_constraint("ck_users_papel_valido", "users", f"papel IN ({papeis_validos})")


def upgrade() -> None:
    _trocar_check(PAPEIS_NOVOS, "ORGANIZADOR", "ENTREGAS")
    op.add_column("users", sa.Column("setor", sa.String(length=80), nullable=False, server_default=""))
    op.add_column("users", sa.Column("pode_sortear", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    for coluna in ("pode_sortear", "setor"):
        if _sqlite():
            op.execute(f"ALTER TABLE users DROP COLUMN {coluna}")
        else:
            op.drop_column("users", coluna)
    # ORGANIZADOR (RH) e ENTREGAS voltam a ser um perfil so (o de entregas).
    _trocar_check(PAPEIS_ANTIGOS, "ENTREGAS", "ORGANIZADOR")
