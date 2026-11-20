"""Aplicacao das migracoes do banco.

Chamado no boot do app e pelo seed. Tambem pode ser usado direto:

    python -m app.migracoes            # aplica as migracoes pendentes
    python -m app.migracoes --status   # mostra a revisao atual e a mais recente

Garantias:
  * backup automatico (SQLite) antes de aplicar qualquer revisao pendente;
  * bancos criados pela v1 (create_all, sem tabela alembic_version) sao
    adotados na revisao baseline dentro da mesma transacao do upgrade;
  * se nada estiver pendente, nada e tocado.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from .config import BASE_DIR, arquivo_sqlite, settings


def _config(url: str) -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    # configparser interpreta "%"; senhas em URL podem conte-lo.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configurar_log"] = False
    cfg.attributes["adotar_legado"] = True
    return cfg


def situacao(url: str | None = None) -> dict:
    url = url or settings.database_url
    head = ScriptDirectory.from_config(_config(url)).get_current_head()
    engine = create_engine(url)
    try:
        with engine.connect() as conexao:
            atual = MigrationContext.configure(conexao).get_current_revision()
            tabelas = set(inspect(conexao).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()
    return {
        "atual": atual,
        "mais_recente": head,
        "pendente": atual != head,
        "legado": atual is None and bool(tabelas),
        "vazio": not tabelas,
    }


def fazer_backup(url: str, rotulo: str, motivo: str = "antes-da-migracao") -> Path | None:
    """Copia consistente do SQLite (API de backup, segura com WAL)."""
    arquivo = arquivo_sqlite(url)
    if arquivo is None or not arquivo.exists() or arquivo.stat().st_size == 0:
        return None
    pasta = arquivo.parent / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = pasta / f"{arquivo.stem}-{carimbo}-{motivo}-{rotulo}.db"
    origem = sqlite3.connect(arquivo)
    copia = sqlite3.connect(destino)
    try:
        origem.backup(copia)
    finally:
        copia.close()
        origem.close()
    return destino


def aplicar_migracoes(url: str | None = None) -> dict:
    url = url or settings.database_url
    antes = situacao(url)
    if not antes["pendente"]:
        return {**antes, "aplicada": False, "backup": None}

    backup = None if antes["vazio"] else fazer_backup(url, antes["mais_recente"])
    command.upgrade(_config(url), "head")
    depois = situacao(url)
    return {
        **depois,
        "aplicada": True,
        "revisao_anterior": antes["atual"] or ("v1 sem controle" if antes["legado"] else None),
        "backup": backup,
    }


def main(argumentos: list[str]) -> int:
    if "--status" in argumentos:
        estado = situacao()
        print(f"revisao atual ....... {estado['atual'] or '(nenhuma)'}")
        print(f"revisao mais recente  {estado['mais_recente']}")
        print(f"pendente ............ {'sim' if estado['pendente'] else 'nao'}")
        if estado["legado"]:
            print("banco da v1 sem controle de migracao: sera adotado ao migrar")
        return 0

    resultado = aplicar_migracoes()
    if not resultado["aplicada"]:
        print(f"Banco ja esta na revisao mais recente ({resultado['atual']}).")
        return 0
    print(f"Migrado: {resultado['revisao_anterior'] or '(vazio)'} -> {resultado['atual']}")
    if resultado["backup"]:
        print(f"Backup salvo em: {resultado['backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
