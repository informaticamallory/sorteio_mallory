"""perfis Organizador/Recepcao e numero do sorteio

  * users.papel: RECEPCAO (entrega de premios) vira ORGANIZADOR e CHECKIN vira
    a nova RECEPCAO (check-in e consulta). As contas afetadas tem a sessao
    encerrada (sessao_versao + 1) para recarregar menus e permissoes.
    No SQLite o CHECK do papel pertence a propria coluna (ver 0002); para
    troca-lo sem recriar a tabela users, a coluna e copiada, removida com
    DROP COLUMN nativo e criada de novo com o CHECK novo.
  * participants.numero_sorteio: numero aleatorio e unico por evento; os
    participantes ja existentes recebem o seu aqui.

Nenhum outro dado e alterado.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14

"""
from __future__ import annotations

import random
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAPEIS_NOVOS = "'ADMIN', 'SORTEIO', 'ORGANIZADOR', 'RECEPCAO', 'COLABORADOR'"
PAPEIS_ANTIGOS = "'ADMIN', 'SORTEIO', 'RECEPCAO', 'CHECKIN', 'COLABORADOR'"

# (papel antigo, papel novo) na ordem em que precisam ser aplicados.
SUBIDA = [("RECEPCAO", "ORGANIZADOR"), ("CHECKIN", "RECEPCAO")]
DESCIDA = [("RECEPCAO", "CHECKIN"), ("ORGANIZADOR", "RECEPCAO")]


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _trocar_papeis(mapa: list[tuple[str, str]], papeis_validos: str) -> None:
    """Renomeia papeis e troca o CHECK, sem recriar a tabela users."""
    casos = " ".join(f"WHEN '{antigo}' THEN '{novo}'" for antigo, novo in mapa)
    afetados = ", ".join(f"'{antigo}'" for antigo, _ in mapa)
    op.execute(
        f"UPDATE users SET sessao_versao = sessao_versao + 1 WHERE papel IN ({afetados})"
    )
    if _sqlite():
        op.execute("ALTER TABLE users ADD COLUMN papel_migracao VARCHAR(20)")
        op.execute(f"UPDATE users SET papel_migracao = CASE papel {casos} ELSE papel END")
        op.execute("ALTER TABLE users DROP COLUMN papel")
        op.execute(
            "ALTER TABLE users ADD COLUMN papel VARCHAR(20) NOT NULL DEFAULT 'COLABORADOR' "
            f"CONSTRAINT ck_users_papel_valido CHECK (papel IN ({papeis_validos}))"
        )
        op.execute("UPDATE users SET papel = papel_migracao")
        op.execute("ALTER TABLE users DROP COLUMN papel_migracao")
    else:
        op.drop_constraint("ck_users_papel_valido", "users", type_="check")
        op.execute(f"UPDATE users SET papel = CASE papel {casos} ELSE papel END")
        op.create_check_constraint("ck_users_papel_valido", "users", f"papel IN ({papeis_validos})")


def _faixa(total: int) -> tuple[int, int]:
    # Mesma regra de app.models.faixa_numeros (copiada: migracoes nao importam o app).
    digitos = 4
    while total > 9 * 10 ** (digitos - 1) // 2:
        digitos += 1
    return 10 ** (digitos - 1), 10**digitos - 1


def upgrade() -> None:
    # ----------------------------------------------------------- perfis
    _trocar_papeis(SUBIDA, PAPEIS_NOVOS)

    # ----------------------------------------------------------- numero do sorteio
    op.add_column("participants", sa.Column("numero_sorteio", sa.Integer(), nullable=True))
    conexao = op.get_bind()
    sorteador = random.SystemRandom()  # os.urandom: imprevisivel, como o modulo secrets
    eventos = [linha[0] for linha in conexao.execute(sa.text("SELECT id FROM events"))]
    for event_id in eventos:
        ids = [
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT id FROM participants WHERE event_id = :e ORDER BY id"), {"e": event_id}
            )
        ]
        if not ids:
            continue
        menor, maior = _faixa(len(ids))
        numeros = sorteador.sample(range(menor, maior + 1), len(ids))
        conexao.execute(
            sa.text("UPDATE participants SET numero_sorteio = :n WHERE id = :i"),
            [{"n": n, "i": i} for i, n in zip(ids, numeros)],
        )
    op.create_index(
        "uq_participante_numero_evento",
        "participants",
        ["event_id", "numero_sorteio"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_participante_numero_evento", table_name="participants")
    if _sqlite():
        op.execute("ALTER TABLE participants DROP COLUMN numero_sorteio")
    else:
        op.drop_column("participants", "numero_sorteio")

    _trocar_papeis(DESCIDA, PAPEIS_ANTIGOS)
