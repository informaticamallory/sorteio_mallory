"""Portal do Colaborador: identificacao, matricula normalizada e push

  * participants.matricula_normalizada: "00026", "026" e "26" viram "26",
    para pesquisar e validar sem depender dos zeros a esquerda. Preenchida
    aqui para os participantes existentes; a matricula original nao muda.
  * participants.identificacao_hash / cpf_hash: codigos HMAC (nunca o CPF ou
    a data de nascimento). Ficam vazios ate a proxima importacao com CPF e
    nascimento.
  * events.autocadastro_inicio / autocadastro_fim: periodo opcional do
    cadastro pelo QR Code.
  * notificacoes.push_enviado_em: garante um push por notificacao.
  * push_inscricoes: aparelhos que aceitaram notificacoes push.

Nenhum dado existente e alterado ou apagado.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalizar_matricula(texto: str | None) -> str:
    # Mesma regra de app.texto.normalizar_matricula (copiada: migracoes nao importam o app).
    compacta = "".join((texto or "").split()).upper()
    if compacta and all(c in "0123456789" for c in compacta):
        return compacta.lstrip("0") or "0"
    return compacta


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("matricula_normalizada", sa.String(length=60), nullable=False, server_default=""),
    )
    op.add_column("participants", sa.Column("identificacao_hash", sa.String(length=64), nullable=True))
    op.add_column("participants", sa.Column("cpf_hash", sa.String(length=64), nullable=True))

    conexao = op.get_bind()
    linhas = conexao.execute(sa.text("SELECT id, matricula FROM participants")).all()
    if linhas:
        conexao.execute(
            sa.text("UPDATE participants SET matricula_normalizada = :n WHERE id = :i"),
            [{"n": _normalizar_matricula(m), "i": i} for i, m in linhas],
        )
    op.create_index(
        "ix_participante_matricula_normalizada",
        "participants",
        ["event_id", "matricula_normalizada"],
    )
    op.create_index("uq_participante_cpf_evento", "participants", ["event_id", "cpf_hash"], unique=True)

    op.add_column("events", sa.Column("autocadastro_inicio", sa.DateTime(), nullable=True))
    op.add_column("events", sa.Column("autocadastro_fim", sa.DateTime(), nullable=True))

    op.add_column("notificacoes", sa.Column("push_enviado_em", sa.DateTime(), nullable=True))

    op.create_table(
        "push_inscricoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("ultimo_envio_em", sa.DateTime(), nullable=True),
        sa.Column("falhas", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index("ix_push_inscricoes_usuario", "push_inscricoes", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_push_inscricoes_usuario", table_name="push_inscricoes")
    op.drop_table("push_inscricoes")
    op.drop_index("uq_participante_cpf_evento", table_name="participants")
    op.drop_index("ix_participante_matricula_normalizada", table_name="participants")
    # SQLite 3.35+ remove colunas sem recriar a tabela (como em 0007).
    for tabela, coluna in (
        ("notificacoes", "push_enviado_em"),
        ("events", "autocadastro_fim"),
        ("events", "autocadastro_inicio"),
        ("participants", "cpf_hash"),
        ("participants", "identificacao_hash"),
        ("participants", "matricula_normalizada"),
    ):
        if _sqlite():
            op.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")
        else:
            op.drop_column(tabela, coluna)
