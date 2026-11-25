"""Numeracao dos blocos recomeca do 01 depois de excluir blocos

  * blocos_sorteio.numero_original: numero que um bloco excluido tinha. O
    historico continua mostrando "Bloco 01 (excluido)" a partir dele.
  * Blocos ja excluidos: guardam o numero em numero_original e passam a usar
    um numero negativo unico (-id), que nunca e exibido. Assim o numero fica
    livre para os blocos ativos (a restricao de numero unico no evento
    continua valendo, sem recriar a tabela).
  * Blocos PLANEJADO de cada evento recebem o menor numero livre depois dos
    blocos ja iniciados que vem antes deles. Ex.: excluidos 01 a 03, os
    planejados 04 e 05 viram 01 e 02; um planejado 02 entre o 01 finalizado e
    o 03 em andamento continua 02. Nome padrao ("Bloco 04") acompanha o
    numero; nomes escolhidos pela equipe ficam como estao.

Nenhum premio, unidade, sorteio ou historico e alterado.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-25

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _nome_padrao(numero: int) -> str:
    return f"Bloco {numero:02d}"


def upgrade() -> None:
    op.add_column("blocos_sorteio", sa.Column("numero_original", sa.Integer(), nullable=True))
    con = op.get_bind()

    # 1) Excluidos saem do caminho, guardando o numero para o historico.
    con.execute(
        sa.text(
            "UPDATE blocos_sorteio SET numero_original = numero, numero = -id "
            "WHERE excluido_em IS NOT NULL AND numero_original IS NULL"
        )
    )

    # 2) Planejados renumerados em sequencia, evento a evento.
    eventos = [r[0] for r in con.execute(sa.text("SELECT DISTINCT event_id FROM blocos_sorteio"))]
    for event_id in eventos:
        ativos = con.execute(
            sa.text(
                "SELECT id, numero, nome, status FROM blocos_sorteio "
                "WHERE event_id = :e AND excluido_em IS NULL ORDER BY ordem, numero"
            ),
            {"e": event_id},
        ).all()
        planejados = [r for r in ativos if r.status == "PLANEJADO"]
        # Mesma regra de services.blocos.numeros_dos_planejados: cada planejado
        # recebe o menor numero livre depois dos iniciados que vem antes dele.
        fixos = {r.numero for r in ativos if r.status != "PLANEJADO"}
        novos: dict[int, int] = {}
        ultimo = 0
        maior_fixo_antes = 0
        for r in ativos:
            if r.status != "PLANEJADO":
                maior_fixo_antes = max(maior_fixo_antes, r.numero)
                continue
            candidato = max(maior_fixo_antes, ultimo) + 1
            while candidato in fixos:
                candidato += 1
            novos[r.id] = candidato
            ultimo = candidato
        if all(r.numero == novos[r.id] for r in planejados):
            continue
        # Duas etapas para nao esbarrar no numero unico do evento.
        for r in planejados:
            con.execute(
                sa.text("UPDATE blocos_sorteio SET numero = :n WHERE id = :i"),
                {"n": -(1_000_000 + r.id), "i": r.id},
            )
        usados = {r.nome.lower() for r in ativos}
        for r in planejados:
            nome = r.nome
            novo_nome = _nome_padrao(novos[r.id])
            if nome == _nome_padrao(r.numero) and novo_nome.lower() not in usados:
                usados.discard(nome.lower())
                nome = novo_nome
                usados.add(nome.lower())
            con.execute(
                sa.text("UPDATE blocos_sorteio SET numero = :n, nome = :nome WHERE id = :i"),
                {"n": novos[r.id], "nome": nome, "i": r.id},
            )


def downgrade() -> None:
    con = op.get_bind()
    # Devolve o numero original aos excluidos (os planejados ficam como estao).
    con.execute(
        sa.text(
            "UPDATE blocos_sorteio SET numero = numero_original "
            "WHERE numero_original IS NOT NULL AND NOT EXISTS ("
            " SELECT 1 FROM blocos_sorteio b2 WHERE b2.event_id = blocos_sorteio.event_id"
            " AND b2.numero = blocos_sorteio.numero_original AND b2.id <> blocos_sorteio.id)"
        )
    )
    if con.dialect.name == "sqlite":
        op.execute("ALTER TABLE blocos_sorteio DROP COLUMN numero_original")
    else:
        op.drop_column("blocos_sorteio", "numero_original")
