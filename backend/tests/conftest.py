from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Precisa estar definido ANTES de importar app.config (pydantic-settings le no import).
_tmp = Path(tempfile.mkdtemp(prefix="sorteio-testes-"))
TMP_TESTES = _tmp
os.environ["DATA_DIR"] = str(_tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'teste.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["SECRET_KEY"] = "chave-de-teste"
os.environ["ADMIN_USUARIO"] = "organizador"
os.environ["ADMIN_SENHA"] = "teste123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import MetaData  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app, garantir_organizador  # noqa: E402
from app.migracoes import aplicar_migracoes  # noqa: E402
from app.models import (  # noqa: E402
    DisplayState,
    Event,
    Participant,
    Prize,
    PrizeUnit,
)
from app.security import novo_token_telao  # noqa: E402


def zerar_banco() -> None:
    """Apaga todas as tabelas, inclusive alembic_version."""
    engine.dispose()
    existentes = MetaData()
    existentes.reflect(bind=engine)
    existentes.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def banco_limpo():
    # O schema dos testes e montado pelas migracoes, nao por create_all:
    # todo teste roda exatamente sobre o banco que o app usa em producao.
    from app.services.autenticacao import limitador

    zerar_banco()
    aplicar_migracoes()
    garantir_organizador()
    limitador.limpar()
    yield
    zerar_banco()


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token(cliente) -> str:
    resposta = cliente.post(
        "/api/auth/login", json={"usuario": "organizador", "senha": "teste123"}
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["access_token"]


@pytest.fixture
def auth(token) -> dict:
    return {"Authorization": f"Bearer {token}"}


def montar_evento(
    *,
    participantes: int = 5,
    presentes: int | None = None,
    quantidade_premio: int = 1,
    permite_multiplas_vitorias: bool = False,
    exige_presenca: bool = True,
    # Em producao a Recepcao sem login nasce fechada; nos testes ela vem aberta
    # para exercitar o check-in. test_recepcao_aberta.py cobre a chave desligada.
    recepcao_publica: bool = True,
) -> tuple[int, list[int], list[int]]:
    """Cria um evento completo direto no banco. Devolve (event_id, ids_participantes, ids_unidades)."""
    from app.database import session_scope

    presentes = participantes if presentes is None else presentes
    with session_scope() as db:
        evento = Event(
            nome="Evento de Teste",
            empresa_nome="Empresa Teste",
            telao_token=novo_token_telao(),
            permite_multiplas_vitorias=permite_multiplas_vitorias,
            exige_presenca=exige_presenca,
            recepcao_publica_ativa=recepcao_publica,
            duracao_animacao_ms=1000,
        )
        db.add(evento)
        db.flush()
        db.add(DisplayState(event_id=evento.id, versao=1))

        ids_participantes = []
        for i in range(participantes):
            p = Participant(
                event_id=evento.id,
                nome=f"Participante {i + 1}",
                matricula=f"{i + 1:05d}",
                setor="Geral",
                presente=i < presentes,
            )
            db.add(p)
            db.flush()
            ids_participantes.append(p.id)

        premio = Prize(
            event_id=evento.id, nome="Premio Teste", quantidade=quantidade_premio, ordem=1
        )
        db.add(premio)
        db.flush()
        ids_unidades = []
        for numero in range(1, quantidade_premio + 1):
            u = PrizeUnit(prize_id=premio.id, numero=numero)
            db.add(u)
            db.flush()
            ids_unidades.append(u.id)

        return evento.id, ids_participantes, ids_unidades
