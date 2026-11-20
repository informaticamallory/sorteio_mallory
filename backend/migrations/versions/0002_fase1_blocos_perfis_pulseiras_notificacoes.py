"""fase 1: blocos, perfis, pulseiras e notificacoes

Somente acrescimos: nenhuma tabela existente e recriada e nenhum dado e
alterado, exceto o preenchimento de users.papel (todos os usuarios da v1 eram
organizadores com acesso total, logo viram ADMIN).

No SQLite, colunas com FK sao adicionadas com ALTER TABLE ... ADD COLUMN
... REFERENCES (suportado nativamente) em vez do "batch mode" do Alembic, que
copiaria a tabela inteira - inclusive draws, o historico de sorteios.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAPEIS = "'ADMIN', 'SORTEIO', 'RECEPCAO', 'CHECKIN', 'COLABORADOR'"


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _adicionar_coluna_fk(tabela: str, coluna: str, alvo: str, ondelete: str | None = None) -> None:
    """Coluna INTEGER anulavel com FK, sem recriar a tabela."""
    if _sqlite():
        acao = f" ON DELETE {ondelete}" if ondelete else ""
        op.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} INTEGER REFERENCES {alvo}(id){acao}")
    else:
        op.add_column(tabela, sa.Column(coluna, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{tabela}_{coluna}", tabela, alvo, [coluna], ["id"], ondelete=ondelete
        )


def upgrade() -> None:
    # ----------------------------------------------------------- blocos
    op.create_table(
        "blocos_sorteio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("capacidade", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(), nullable=True),
        sa.Column("finalizado_em", sa.DateTime(), nullable=True),
        sa.Column("finalizado_por_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("capacidade >= 1", name="ck_bloco_capacidade_positiva"),
        sa.CheckConstraint(
            "status IN ('PLANEJADO', 'EM_ANDAMENTO', 'PAUSADO', 'FINALIZADO')",
            name="ck_bloco_status_valido",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finalizado_por_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "numero", name="uq_bloco_numero_evento"),
    )
    op.create_index("ix_blocos_sorteio_event_id", "blocos_sorteio", ["event_id"])
    op.create_index("ix_blocos_sorteio_event_ordem", "blocos_sorteio", ["event_id", "ordem"])
    op.create_index("ix_blocos_sorteio_status", "blocos_sorteio", ["status"])

    # ----------------------------------------------------------- notificacoes
    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("draw_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("lida", sa.Boolean(), nullable=False),
        sa.Column("criada_em", sa.DateTime(), nullable=False),
        sa.Column("lida_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["draw_id"], ["draws.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draw_id", "tipo", name="uq_notificacao_sorteio_tipo"),
    )
    op.create_index(
        "ix_notificacoes_usuario_lida_criada", "notificacoes", ["usuario_id", "lida", "criada_em"]
    )
    op.create_index(
        "ix_notificacoes_participante_criada", "notificacoes", ["participant_id", "criada_em"]
    )
    op.create_index("ix_notificacoes_evento_criada", "notificacoes", ["event_id", "criada_em"])

    # ----------------------------------------------------------- users.papel
    if _sqlite():
        op.execute(
            "ALTER TABLE users ADD COLUMN papel VARCHAR(20) NOT NULL DEFAULT 'COLABORADOR' "
            f"CONSTRAINT ck_users_papel_valido CHECK (papel IN ({PAPEIS}))"
        )
    else:
        op.add_column(
            "users",
            sa.Column("papel", sa.String(length=20), nullable=False, server_default="COLABORADOR"),
        )
        op.create_check_constraint("ck_users_papel_valido", "users", f"papel IN ({PAPEIS})")
    # Na v1 todo usuario era organizador com acesso total.
    op.execute("UPDATE users SET papel = 'ADMIN'")

    # ----------------------------------------------------------- participantes
    op.add_column("participants", sa.Column("pulseira", sa.String(length=40), nullable=True))
    _adicionar_coluna_fk("participants", "usuario_id", "users", "SET NULL")
    op.create_index("ix_participants_usuario_id", "participants", ["usuario_id"])
    op.create_index(
        "uq_participante_pulseira_evento", "participants", ["event_id", "pulseira"], unique=True
    )
    op.create_index(
        "uq_participante_usuario_evento", "participants", ["event_id", "usuario_id"], unique=True
    )

    # ----------------------------------------------------------- vinculos com blocos
    _adicionar_coluna_fk("prize_units", "bloco_id", "blocos_sorteio", "SET NULL")
    op.create_index("ix_prize_units_bloco_id", "prize_units", ["bloco_id"])

    _adicionar_coluna_fk("draws", "bloco_id", "blocos_sorteio")
    op.create_index("ix_draws_bloco_id", "draws", ["bloco_id"])


def downgrade() -> None:
    # O downgrade usa batch mode (recria as tabelas). O env.py desliga as FKs
    # durante a migracao, o que impede cascatas, e confere a integridade antes
    # do commit. Faca backup antes de rodar um downgrade.
    op.drop_index("ix_draws_bloco_id", table_name="draws")
    with op.batch_alter_table("draws") as batch_op:
        batch_op.drop_column("bloco_id")
    # O batch recria a tabela a partir da reflexao; o indice parcial nao e
    # reproduzido com fidelidade, entao e recriado explicitamente.
    op.execute("DROP INDEX IF EXISTS uq_draw_unidade_valida")
    op.create_index(
        "uq_draw_unidade_valida",
        "draws",
        ["prize_unit_id"],
        unique=True,
        sqlite_where=sa.text("status = 'valido'"),
        postgresql_where=sa.text("status = 'valido'"),
    )

    op.drop_index("ix_prize_units_bloco_id", table_name="prize_units")
    with op.batch_alter_table("prize_units") as batch_op:
        batch_op.drop_column("bloco_id")

    op.drop_index("uq_participante_usuario_evento", table_name="participants")
    op.drop_index("uq_participante_pulseira_evento", table_name="participants")
    op.drop_index("ix_participants_usuario_id", table_name="participants")
    with op.batch_alter_table("participants") as batch_op:
        batch_op.drop_column("usuario_id")
        batch_op.drop_column("pulseira")

    with op.batch_alter_table("users") as batch_op:
        # No SQLite o batch reflete o CHECK nomeado; sem remove-lo, a tabela
        # recriada referenciaria uma coluna inexistente.
        batch_op.drop_constraint("ck_users_papel_valido", type_="check")
        batch_op.drop_column("papel")

    op.drop_index("ix_notificacoes_evento_criada", table_name="notificacoes")
    op.drop_index("ix_notificacoes_participante_criada", table_name="notificacoes")
    op.drop_index("ix_notificacoes_usuario_lida_criada", table_name="notificacoes")
    op.drop_table("notificacoes")

    op.drop_index("ix_blocos_sorteio_status", table_name="blocos_sorteio")
    op.drop_index("ix_blocos_sorteio_event_ordem", table_name="blocos_sorteio")
    op.drop_index("ix_blocos_sorteio_event_id", table_name="blocos_sorteio")
    op.drop_table("blocos_sorteio")
