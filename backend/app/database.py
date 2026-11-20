from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

is_sqlite = settings.database_url.startswith("sqlite")

# Quanto tempo aguardar a liberacao do lock de escrita antes de devolver
# "database is locked". As transacoes aqui sao curtas (milissegundos), entao
# 15s e folgado para o cenario de evento ao vivo.
BUSY_TIMEOUT_MS = 15_000


def criar_engine(url: str) -> Engine:
    """Engine com as garantias do sistema. Usada pelo app e pelas migracoes."""
    sqlite = url.startswith("sqlite")
    connect_args = (
        {"timeout": BUSY_TIMEOUT_MS / 1000, "check_same_thread": False} if sqlite else {}
    )
    novo = create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)
    if not sqlite:
        return novo

    @event.listens_for(novo, "connect")
    def _sqlite_on_connect(dbapi_connection, connection_record):  # noqa: ANN001
        # Desliga o controle implicito de transacao do pysqlite para que o
        # SQLAlchemy possa emitir BEGIN IMMEDIATE (ver listener abaixo).
        dbapi_connection.isolation_level = None
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        # Reforca o tempo de espera pelo lock. O parametro `timeout` do connect
        # ja define isso, mas deixamos explicito para nao depender do driver.
        cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cur.close()

    @event.listens_for(novo, "begin")
    def _sqlite_begin_immediate(conn):  # noqa: ANN001
        # BEGIN IMMEDIATE adquire o lock de escrita no inicio da transacao.
        # Isso serializa sorteios concorrentes: a segunda requisicao espera
        # (ate o timeout) em vez de ler um estado desatualizado.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return novo


engine = criar_engine(settings.database_url)


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def criar_tabelas() -> None:
    """Cria o schema direto dos modelos. Uso restrito aos testes.

    O app e o seed usam `app.migracoes.aplicar_migracoes()`, que preserva os
    dados existentes. Um teste garante que modelos e migracoes nao divergem.
    """
    from . import models  # noqa: F401  (registra os modelos no metadata)

    Base.metadata.create_all(bind=engine)
