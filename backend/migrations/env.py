"""Ambiente de migracao.

Garantias adicionadas ao env.py padrao do Alembic:

* usa o mesmo engine do app (WAL, BEGIN IMMEDIATE, busy_timeout), entao a
  migracao inteira roda numa unica transacao com lock de escrita;
* no SQLite, desliga as FKs durante a migracao. Isso e obrigatorio: o "batch
  mode" recria tabelas, e DROP TABLE com FKs ligadas dispara as cascatas -
  apagaria, por exemplo, todos os sorteios ao recriar prize_units. Antes do
  commit, PRAGMA foreign_key_check confirma que nenhuma referencia quebrou;
* adota bancos criados antes das migracoes (create_all), marcando-os na
  revisao baseline dentro da mesma transacao do upgrade.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import inspect

from app import models  # noqa: F401  (registra os modelos no metadata)
from app.config import settings
from app.database import Base, criar_engine

config = context.config

# Ao rodar dentro do app, nao reconfigura o logging (apagaria os logs do uvicorn).
if config.config_file_name and config.attributes.get("configurar_log", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Revisao que corresponde ao schema criado por create_all na versao 1.
REVISAO_BASELINE = "0001"
TABELAS_V1 = {
    "users",
    "events",
    "participants",
    "prizes",
    "prize_units",
    "draws",
    "rule_changes",
    "audit_logs",
    "display_states",
}


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or settings.database_url


def _adotar_banco_legado(connection, migration_context) -> None:  # noqa: ANN001
    if migration_context.get_current_revision() is not None:
        return
    tabelas = set(inspect(connection).get_table_names()) - {"alembic_version"}
    if not tabelas:
        return  # banco vazio: as migracoes criam tudo do zero
    # So adota se o schema for exatamente o da v1. Tabelas a mais indicam um
    # banco criado por outra via (ex.: create_all de modelos novos); marca-lo
    # como baseline faria as revisoes seguintes colidirem ou pularem passos.
    faltando = TABELAS_V1 - tabelas
    sobrando = tabelas - TABELAS_V1
    if faltando or sobrando:
        raise RuntimeError(
            "Banco sem controle de migracao cujo schema nao e o da v1 "
            f"(faltam: {sorted(faltando) or '-'}; inesperadas: {sorted(sobrando) or '-'}). "
            "Nada foi alterado."
        )
    migration_context.stamp(context.script, REVISAO_BASELINE)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=_url().startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _url()
    sqlite = url.startswith("sqlite")
    engine = criar_engine(url)
    try:
        with engine.connect() as connection:
            # PRAGMA foreign_keys so tem efeito fora de transacao: usamos a
            # conexao do driver diretamente (autocommit), antes do BEGIN.
            bruta = connection.connection.driver_connection if sqlite else None
            if bruta is not None:
                bruta.execute("PRAGMA foreign_keys=OFF")
            try:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    render_as_batch=sqlite,
                    compare_type=True,
                )
                with context.begin_transaction():
                    if config.attributes.get("adotar_legado"):
                        _adotar_banco_legado(connection, context.get_context())
                    context.run_migrations()
                    if sqlite:
                        violacoes = connection.exec_driver_sql(
                            "PRAGMA foreign_key_check"
                        ).fetchall()
                        if violacoes:
                            raise RuntimeError(
                                "Migracao abortada: referencias quebradas "
                                f"{violacoes[:5]}. Nenhuma alteracao foi gravada."
                            )
            finally:
                if bruta is not None:
                    bruta.execute("PRAGMA foreign_keys=ON")
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
