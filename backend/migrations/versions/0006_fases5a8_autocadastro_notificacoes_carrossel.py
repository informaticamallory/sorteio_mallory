"""fases 5 a 8: autocadastro, notificacoes e carrossel dos ganhadores

Somente acrescimos; nenhuma tabela existente e recriada e nenhum dado e
alterado:
  * events: autocadastro_ativo (desligado), autocadastro_confirma_presenca,
    carrossel_segundos (>= 5);
  * notificacoes: prize_id e disponivel_em;
  * display_states: estado oficial do carrossel.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _adicionar_coluna_fk(tabela: str, coluna: str, alvo: str, ondelete: str | None = None) -> None:
    """Coluna INTEGER anulavel com FK, sem recriar a tabela (ver 0002)."""
    if _sqlite():
        acao = f" ON DELETE {ondelete}" if ondelete else ""
        op.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} INTEGER REFERENCES {alvo}(id){acao}")
    else:
        op.add_column(tabela, sa.Column(coluna, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{tabela}_{coluna}", tabela, alvo, [coluna], ["id"], ondelete=ondelete
        )


def _remover_coluna(tabela: str, coluna: str) -> None:
    if _sqlite():
        op.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")
    else:
        op.drop_column(tabela, coluna)


def upgrade() -> None:
    # ----------------------------------------------------------- eventos
    op.add_column(
        "events",
        sa.Column("autocadastro_ativo", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "events",
        sa.Column(
            "autocadastro_confirma_presenca", sa.Boolean(), nullable=False, server_default="1"
        ),
    )
    if _sqlite():
        op.execute(
            "ALTER TABLE events ADD COLUMN carrossel_segundos INTEGER NOT NULL DEFAULT 6 "
            "CONSTRAINT ck_events_carrossel_minimo CHECK (carrossel_segundos >= 5)"
        )
    else:
        op.add_column(
            "events",
            sa.Column("carrossel_segundos", sa.Integer(), nullable=False, server_default="6"),
        )
        op.create_check_constraint(
            "ck_events_carrossel_minimo", "events", "carrossel_segundos >= 5"
        )

    # ----------------------------------------------------------- notificacoes
    _adicionar_coluna_fk("notificacoes", "prize_id", "prizes", "SET NULL")
    op.add_column("notificacoes", sa.Column("disponivel_em", sa.DateTime(), nullable=True))

    # ----------------------------------------------------------- telao: carrossel
    _adicionar_coluna_fk("display_states", "carrossel_bloco_id", "blocos_sorteio", "SET NULL")
    op.add_column(
        "display_states",
        sa.Column("carrossel_indice", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("display_states", sa.Column("carrossel_desde", sa.DateTime(), nullable=True))
    op.add_column(
        "display_states",
        sa.Column("carrossel_duracao_s", sa.Integer(), nullable=False, server_default="6"),
    )


def downgrade() -> None:
    # Um telao parado no carrossel volta para a tela de espera.
    op.execute("UPDATE display_states SET estado = 'aguardando' WHERE estado = 'carrossel_ganhadores'")
    for coluna in ("carrossel_duracao_s", "carrossel_desde", "carrossel_indice", "carrossel_bloco_id"):
        _remover_coluna("display_states", coluna)
    _remover_coluna("notificacoes", "disponivel_em")
    _remover_coluna("notificacoes", "prize_id")

    if _sqlite():
        # DROP COLUMN nativo (como na 0003): o CHECK pertence a propria coluna.
        op.execute("ALTER TABLE events DROP COLUMN carrossel_segundos")
    else:
        op.drop_constraint("ck_events_carrossel_minimo", "events", type_="check")
        op.drop_column("events", "carrossel_segundos")
    _remover_coluna("events", "autocadastro_confirma_presenca")
    _remover_coluna("events", "autocadastro_ativo")
