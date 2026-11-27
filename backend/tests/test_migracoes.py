"""Migracoes: banco novo, adocao de banco v1, ida e volta e recusas seguras."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.database import Base
from app.migracoes import _config, aplicar_migracoes, situacao

TABELAS_V1 = [
    "users", "events", "participants", "prizes", "prize_units",
    "draws", "rule_changes", "audit_logs", "display_states",
]


def _url(caminho: Path) -> str:
    return f"sqlite:///{caminho.as_posix()}"


def _fk_ondelete_pragma(caminho: Path, tabela: str, coluna: str) -> str:
    con = sqlite3.connect(caminho)
    try:
        for linha in con.execute(f"pragma foreign_key_list({tabela})"):
            if linha[3] == coluna:
                return linha[6]
    finally:
        con.close()
    raise AssertionError(f"FK {tabela}.{coluna} nao encontrada")


def _divergencias(caminho: Path) -> list:
    """compare_metadata, descontando um falso positivo conhecido.

    FKs adicionadas com ALTER TABLE ADD COLUMN ficam declaradas na propria
    coluna; a reflexao do SQLAlchemy nao le o ON DELETE nesse formato. Para
    esses pares remove_fk/add_fk, a regra e conferida no PRAGMA do SQLite,
    que e a fonte de verdade do banco.
    """
    engine = create_engine(_url(caminho))
    try:
        with engine.connect() as conexao:
            diff = compare_metadata(
                MigrationContext.configure(conexao, opts={"compare_type": True}), Base.metadata
            )
    finally:
        engine.dispose()

    restantes = []
    for item in diff:
        if item[0] in {"remove_fk", "add_fk"}:
            fk = item[1]
            tabela = fk.parent.name
            coluna = next(iter(fk.columns)).name
            esperado = (fk.ondelete or "NO ACTION").upper()
            if item[0] == "add_fk" and _fk_ondelete_pragma(caminho, tabela, coluna) == esperado:
                continue
            if item[0] == "remove_fk":
                continue  # o par add_fk correspondente e conferido acima
        restantes.append(item)
    return restantes


def _criar_banco_v1(caminho: Path) -> None:
    """Banco identico ao da v1: schema da baseline, sem alembic_version."""
    command.upgrade(_config(_url(caminho)), "0001")
    con = sqlite3.connect(caminho)
    con.execute("DROP TABLE alembic_version")
    con.commit()
    con.close()


def _popular_v1(caminho: Path) -> None:
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA foreign_keys=ON")
    agora = "2026-11-13 12:00:00.000000"
    con.execute(
        "INSERT INTO users VALUES (1, 'organizador', 'Organizador', 'hash', 1, ?)", (agora,)
    )
    con.execute(
        "INSERT INTO users VALUES (2, 'segundo', 'Segundo Organizador', 'hash', 1, ?)", (agora,)
    )
    con.execute(
        """INSERT INTO events VALUES (1, 'Evento Real', 'Mallory', NULL, '#0B1F3A', '#D4AF37',
        '#F8FAFC', '#1D4ED8', 'Ola', 'Tchau', 'Regras', 1, 0, 6000, 'America/Sao_Paulo',
        'tok-v1', 0, 1, 'resortear', 0, ?, 0, ?, ?)""",
        (agora, agora, agora),
    )
    for i in range(1, 5):
        con.execute(
            "INSERT INTO participants VALUES (?, 1, ?, ?, 'TI', NULL, 1, 1, NULL, ?, ?)",
            (i, f"Pessoa {i}", f"{i:05d}", agora, agora),
        )
    con.execute("INSERT INTO prizes VALUES (1, 1, 'TV', NULL, NULL, 2, 1, ?)", (agora,))
    con.execute("INSERT INTO prize_units VALUES (1, 1, 1, 'sorteado')")
    con.execute("INSERT INTO prize_units VALUES (2, 1, 2, 'entregue')")
    colunas_draw = (
        "id, event_id, prize_unit_id, participant_id, rodada, status, idempotency_key, "
        "elegiveis_ids, elegiveis_total, indice_sorteado, criado_em, criado_por_id, entregue, "
        "entregue_em, entregue_por_id, anulado_em, anulado_por_id, motivo_anulacao, "
        "tipo_anulacao, estorno_entrega, draw_anterior_id"
    )
    linhas = [
        (1, 1, 1, 1, 1, "anulado", "k1", "[1,2,3,4]", 4, 0, agora, 1, 0, None, None,
         agora, 2, "Ausente no palco", "ausencia", 0, None),
        (2, 1, 1, 2, 2, "valido", "k2", "[2,3,4]", 3, 0, agora, 1, 0, None, None,
         None, None, None, None, 0, 1),
        (3, 1, 2, 3, 3, "valido", "k3", "[3,4]", 2, 0, agora, 2, 1, agora, 1,
         None, None, None, None, 0, None),
    ]
    for linha in linhas:
        con.execute(f"INSERT INTO draws ({colunas_draw}) VALUES ({','.join('?' * 21)})", linha)
    con.execute(
        "INSERT INTO display_states VALUES (1, 'resultado', 2, 3, NULL, '[]', 7, ?)", (agora,)
    )
    con.execute(
        "INSERT INTO audit_logs VALUES (1, 1, 1, 'sorteio_realizado', '{}', ?)", (agora,)
    )
    con.execute(
        "INSERT INTO rule_changes VALUES (1, 1, 'exige_presenca', 'False', 'True', 1, 1, ?)",
        (agora,),
    )
    con.commit()
    con.close()


def _foto_v1(caminho: Path) -> dict:
    """Todos os dados das tabelas v1, apenas nas colunas que existiam na v1."""
    con = sqlite3.connect(caminho)
    colunas_posteriores_a_v1 = {
        "users": {
            "papel", "sessao_versao", "ultimo_acesso_em", "tentativas_falhas",
            "bloqueado_ate", "deve_trocar_senha", "senha_alterada_em",
            "setor", "pode_sortear",
        },
        "events": {
            "capacidade_bloco_padrao", "autocadastro_ativo",
            "autocadastro_confirma_presenca", "carrossel_segundos",
            "autocadastro_inicio", "autocadastro_fim",
            "modo_sorteio", "matricula_faixa_inicio", "matricula_faixa_fim",
            "recepcao_publica_ativa", "tema_telao",
            "claro_cor_fundo", "claro_cor_painel", "claro_cor_destaque", "claro_cor_texto",
            "telao_subtitulo", "evento_teste", "som_sorteio",
        },
        "display_states": {
            "carrossel_bloco_id", "carrossel_indice", "carrossel_desde", "carrossel_duracao_s",
        },
        "participants": {
            "pulseira", "usuario_id", "nome_busca", "numero_sorteio",
            "matricula_normalizada", "identificacao_hash", "cpf_hash",
        },
        "prizes": {"nome_busca", "excluido_em"},
        "prize_units": {"bloco_id", "ordem_bloco"},
        "draws": {"bloco_id"},
    }
    foto = {}
    for tabela in TABELAS_V1:
        ignorar = colunas_posteriores_a_v1.get(tabela, set())
        colunas = [r[1] for r in con.execute(f"pragma table_info({tabela})") if r[1] not in ignorar]
        foto[tabela] = con.execute(
            f"SELECT {', '.join(colunas)} FROM {tabela} ORDER BY rowid"
        ).fetchall()
    con.close()
    return foto


def _sql_indice(caminho: Path, nome: str) -> str | None:
    con = sqlite3.connect(caminho)
    try:
        linha = con.execute("SELECT sql FROM sqlite_master WHERE name = ?", (nome,)).fetchone()
        return linha[0] if linha else None
    finally:
        con.close()


# ------------------------------------------------------------------ testes
def test_banco_novo_chega_na_revisao_mais_recente_igual_aos_modelos(tmp_path):
    banco = tmp_path / "novo.db"
    resultado = aplicar_migracoes(_url(banco))

    assert resultado["aplicada"] is True
    assert resultado["atual"] == resultado["mais_recente"]
    assert resultado["backup"] is None  # banco vazio nao precisa de backup
    assert _divergencias(banco) == []


def test_fks_adicionadas_por_alter_table_tem_a_regra_de_exclusao_correta(tmp_path):
    banco = tmp_path / "fks.db"
    aplicar_migracoes(_url(banco))
    assert _fk_ondelete_pragma(banco, "participants", "usuario_id") == "SET NULL"
    assert _fk_ondelete_pragma(banco, "prize_units", "bloco_id") == "SET NULL"
    # Bloco com resultado registrado nao pode ser apagado.
    assert _fk_ondelete_pragma(banco, "draws", "bloco_id") == "NO ACTION"


def test_adocao_de_banco_v1_preserva_todos_os_dados(tmp_path):
    banco = tmp_path / "v1.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    antes = _foto_v1(banco)

    assert situacao(_url(banco))["legado"] is True
    resultado = aplicar_migracoes(_url(banco))

    assert resultado["aplicada"] is True
    assert resultado["revisao_anterior"] == "v1 sem controle"
    assert resultado["atual"] == resultado["mais_recente"]
    assert _foto_v1(banco) == antes, "dados da v1 mudaram na migracao"

    con = sqlite3.connect(banco)
    try:
        assert con.execute("SELECT usuario, papel FROM users ORDER BY id").fetchall() == [
            ("organizador", "ADMIN"),
            ("segundo", "ADMIN"),
        ]
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # Resultados antigos nao ganham bloco retroativamente.
        assert con.execute("SELECT count(*) FROM draws WHERE bloco_id IS NULL").fetchone()[0] == 3
    finally:
        con.close()
    assert _divergencias(banco) == []


def test_backup_e_feito_antes_de_migrar_e_contem_os_dados_originais(tmp_path):
    banco = tmp_path / "comdados.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    antes = _foto_v1(banco)

    resultado = aplicar_migracoes(_url(banco))
    backup = Path(resultado["backup"])

    assert backup.exists()
    assert backup.parent == tmp_path / "backups"
    assert _foto_v1(backup) == antes
    con = sqlite3.connect(backup)
    try:
        colunas_users = [r[1] for r in con.execute("pragma table_info(users)")]
    finally:
        con.close()
    assert "papel" not in colunas_users  # o backup e o estado ANTERIOR


def test_segunda_execucao_nao_altera_nada(tmp_path):
    banco = tmp_path / "idempotente.db"
    aplicar_migracoes(_url(banco))
    segunda = aplicar_migracoes(_url(banco))
    assert segunda["aplicada"] is False
    assert segunda["backup"] is None
    assert not (tmp_path / "backups").exists()


def test_ida_e_volta_preserva_dados_e_o_indice_parcial(tmp_path):
    banco = tmp_path / "idaevolta.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    antes = _foto_v1(banco)
    aplicar_migracoes(_url(banco))

    command.downgrade(_config(_url(banco)), "0001")
    assert _foto_v1(banco) == antes
    indice = _sql_indice(banco, "uq_draw_unidade_valida")
    assert indice is not None and "WHERE" in indice.upper(), indice

    command.upgrade(_config(_url(banco)), "head")
    assert _foto_v1(banco) == antes
    assert _divergencias(banco) == []
    con = sqlite3.connect(banco)
    try:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()


def test_0017_carrossel_aceita_meio_segundo_e_mantem_os_valores(tmp_path):
    banco = tmp_path / "carrossel.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    command.upgrade(_config(_url(banco)), "0016")
    con = sqlite3.connect(banco)
    con.execute("UPDATE events SET carrossel_segundos = 3")
    con.commit()
    con.close()

    command.upgrade(_config(_url(banco)), "0017")
    con = sqlite3.connect(banco)
    try:
        assert con.execute("SELECT carrossel_segundos FROM events").fetchall() == [(3.0,)]
        con.execute("UPDATE events SET carrossel_segundos = 0.5")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE events SET carrossel_segundos = 0.4")
        con.commit()
    finally:
        con.close()

    # Na volta, 0,5 vira o minimo antigo (1 s).
    command.downgrade(_config(_url(banco)), "0016")
    con = sqlite3.connect(banco)
    try:
        assert con.execute("SELECT carrossel_segundos FROM events").fetchall() == [(1,)]
    finally:
        con.close()
    command.upgrade(_config(_url(banco)), "head")
    assert _divergencias(banco) == []


def test_fase2_evento_existente_recebe_capacidade_25_e_indice_de_bloco_ativo(tmp_path):
    banco = tmp_path / "fase2.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    aplicar_migracoes(_url(banco))

    con = sqlite3.connect(banco)
    try:
        assert con.execute("SELECT capacidade_bloco_padrao FROM events").fetchall() == [(25,)]
        assert con.execute("SELECT count(*) FROM prize_units WHERE ordem_bloco IS NOT NULL").fetchone()[0] == 0
    finally:
        con.close()
    indice = _sql_indice(banco, "uq_bloco_em_andamento_evento")
    assert indice is not None and "WHERE" in indice.upper(), indice


def test_fase3_nomes_existentes_ganham_forma_de_busca(tmp_path):
    banco = tmp_path / "fase3.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    con = sqlite3.connect(banco)
    con.execute("UPDATE participants SET nome = 'José da Conceição' WHERE id = 1")
    con.execute("UPDATE prizes SET nome = 'Câmera  Fotográfica' WHERE id = 1")
    con.commit()
    con.close()

    aplicar_migracoes(_url(banco))

    con = sqlite3.connect(banco)
    try:
        assert con.execute("SELECT nome_busca FROM participants WHERE id = 1").fetchone() == (
            "jose da conceicao",
        )
        assert con.execute("SELECT nome_busca FROM participants WHERE id = 2").fetchone() == (
            "pessoa 2",
        )
        assert con.execute("SELECT nome_busca FROM prizes").fetchall() == [("camera fotografica",)]
    finally:
        con.close()


def test_fase4_contas_existentes_continuam_entrando_sem_troca_obrigatoria(tmp_path):
    banco = tmp_path / "fase4.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    aplicar_migracoes(_url(banco))
    con = sqlite3.connect(banco)
    try:
        assert con.execute(
            "SELECT usuario, papel, senha_hash, sessao_versao, tentativas_falhas, "
            "deve_trocar_senha, bloqueado_ate FROM users ORDER BY id"
        ).fetchall() == [
            ("organizador", "ADMIN", "hash", 1, 0, 0, None),
            ("segundo", "ADMIN", "hash", 1, 0, 0, None),
        ]
    finally:
        con.close()


def test_0007_perfis_migram_e_participantes_ganham_numero_unico(tmp_path):
    banco = tmp_path / "fase9.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    command.upgrade(_config(_url(banco)), "0006")
    con = sqlite3.connect(banco)
    con.execute("UPDATE users SET papel = 'RECEPCAO' WHERE id = 2")
    con.execute(
        "INSERT INTO users (id, usuario, nome, senha_hash, ativo, criado_em, papel) "
        "VALUES (3, 'checkin', 'Check-in', 'hash', 1, '2026-11-13', 'CHECKIN')"
    )
    con.commit()
    con.close()

    command.upgrade(_config(_url(banco)), "0007")

    con = sqlite3.connect(banco)
    try:
        assert con.execute("SELECT usuario, papel, sessao_versao FROM users ORDER BY id").fetchall() == [
            ("organizador", "ADMIN", 1),
            ("segundo", "ORGANIZADOR", 2),  # antiga recepcao; sessao encerrada
            ("checkin", "RECEPCAO", 2),  # antigo check-in vira a nova recepcao
        ]
        numeros = [n for (n,) in con.execute("SELECT numero_sorteio FROM participants ORDER BY id")]
        assert len(numeros) == 4 and len(set(numeros)) == 4
        assert all(1000 <= n <= 9999 for n in numeros)
        # O CHECK novo recusa os papeis que nao existem mais.
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE users SET papel = 'CHECKIN' WHERE id = 3")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE participants SET numero_sorteio = ? WHERE id = 2", (numeros[0],))
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()

    # E a volta devolve os papeis antigos.
    command.downgrade(_config(_url(banco)), "0006")
    con = sqlite3.connect(banco)
    try:
        assert [p for (p,) in con.execute("SELECT papel FROM users ORDER BY id")] == [
            "ADMIN", "RECEPCAO", "CHECKIN",
        ]
    finally:
        con.close()


def test_0010_organizador_de_entregas_vira_equipe_de_entregas_sem_ganhar_permissao(tmp_path):
    banco = tmp_path / "fase10.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    command.upgrade(_config(_url(banco)), "0009")
    con = sqlite3.connect(banco)
    con.execute("UPDATE users SET papel = 'ORGANIZADOR' WHERE id = 2")
    con.commit()
    con.close()

    aplicar_migracoes(_url(banco))
    con = sqlite3.connect(banco)
    try:
        assert con.execute(
            "SELECT usuario, papel, sessao_versao, setor, pode_sortear, senha_hash FROM users ORDER BY id"
        ).fetchall() == [
            ("organizador", "ADMIN", 1, "", 0, "hash"),  # admin intocado (senha, sessao)
            ("segundo", "ENTREGAS", 2, "", 0, "hash"),  # perfil de entregas preservado; sessao encerrada
        ]
        con.execute("UPDATE users SET papel = 'ENTREGAS' WHERE id = 1")  # o CHECK novo aceita
        con.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE users SET papel = 'SUPERUSUARIO' WHERE id = 1")
    finally:
        con.close()

    command.downgrade(_config(_url(banco)), "0009")
    con = sqlite3.connect(banco)
    try:
        assert [p for (p,) in con.execute("SELECT papel FROM users ORDER BY id")] == ["ADMIN", "ORGANIZADOR"]
    finally:
        con.close()


def test_indice_que_impede_dois_resultados_validos_continua_ativo(tmp_path):
    banco = tmp_path / "unico.db"
    _criar_banco_v1(banco)
    _popular_v1(banco)
    aplicar_migracoes(_url(banco))

    con = sqlite3.connect(banco)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO draws (event_id, prize_unit_id, participant_id, rodada, status, "
                "idempotency_key, elegiveis_ids, elegiveis_total, indice_sorteado, criado_em, "
                "criado_por_id, entregue, estorno_entrega) VALUES "
                "(1, 1, 4, 4, 'valido', 'k4', '[]', 1, 0, '2026-11-13', 1, 0, 0)"
            )
    finally:
        con.close()


def test_banco_sem_controle_com_schema_desconhecido_e_recusado(tmp_path):
    """Nunca carimbar como v1 um banco que nao e o da v1."""
    banco = tmp_path / "estranho.db"
    engine = create_engine(_url(banco))
    Base.metadata.create_all(engine)  # schema novo, sem alembic_version
    engine.dispose()

    with pytest.raises(RuntimeError, match="nao e o da v1"):
        aplicar_migracoes(_url(banco))
    assert situacao(_url(banco))["atual"] is None  # nada foi gravado


def test_banco_v1_incompleto_e_recusado(tmp_path):
    banco = tmp_path / "incompleto.db"
    _criar_banco_v1(banco)
    con = sqlite3.connect(banco)
    con.execute("DROP TABLE rule_changes")
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="faltam"):
        aplicar_migracoes(_url(banco))
    assert situacao(_url(banco))["atual"] is None
