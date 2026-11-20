"""Nova recepcao (publica, sem login): numero do sorteio, check-in pela
matricula e consulta do numero e dos premios ja revelados."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, Event, Participant, faixa_numeros
from conftest import montar_evento


def _numeros(event_id: int) -> list[int]:
    with session_scope() as db:
        return list(
            db.scalars(
                select(Participant.numero_sorteio)
                .where(Participant.event_id == event_id)
                .order_by(Participant.id)
            )
        )


# ------------------------------------------------------------------ numero do sorteio
def test_faixa_cresce_so_quando_passa_da_metade():
    assert faixa_numeros(1) == (1000, 9999)
    assert faixa_numeros(4500) == (1000, 9999)
    assert faixa_numeros(4501) == (10000, 99999)
    assert faixa_numeros(45001) == (100000, 999999)


def test_todo_participante_recebe_numero_aleatorio_unico(cliente, auth):
    event_id, _, _ = montar_evento(participantes=30)
    # Importacao (varios no mesmo commit) e cadastro manual.
    importados = cliente.post(
        f"/api/events/{event_id}/participantes/importar/confirmar",
        json={"linhas": [{"nome": f"Importado {i}", "matricula": f"9{i:04d}", "setor": "TI"} for i in range(40)]},
        headers=auth,
    )
    assert importados.status_code == 200, importados.text
    manual = cliente.post(
        f"/api/events/{event_id}/participantes",
        json={"nome": "Manual da Silva", "matricula": "77777", "setor": "RH"},
        headers=auth,
    )
    assert manual.status_code == 201 and 1000 <= manual.json()["numero_sorteio"] <= 9999

    numeros = _numeros(event_id)
    assert len(numeros) == 71 and None not in numeros
    assert len(set(numeros)) == 71
    assert all(1000 <= n <= 9999 for n in numeros)
    # Aleatorio, nao sequencial pela ordem de cadastro.
    assert sorted(numeros) != numeros


def test_numero_e_unico_por_evento_mas_pode_repetir_em_outro():
    a, _, _ = montar_evento(participantes=1)
    b, _, _ = montar_evento(participantes=1)
    (numero_a,) = _numeros(a)
    with session_scope() as db:
        p = db.scalar(select(Participant).where(Participant.event_id == b))
        p.numero_sorteio = numero_a  # outro evento: permitido
    with pytest.raises(Exception):
        with session_scope() as db:
            db.add(Participant(event_id=a, nome="Outra Pessoa", matricula="X1", numero_sorteio=numero_a))


def test_evento_criado_junto_com_participantes_tambem_numera():
    with session_scope() as db:
        evento = Event(nome="Novo", telao_token="tok-novo-numera")
        evento.participantes = [Participant(nome=f"P {i}", matricula=str(i)) for i in range(5)]
        db.add(evento)
        db.flush()
        event_id = evento.id
    numeros = _numeros(event_id)
    assert len(set(numeros)) == 5 and None not in numeros


# ------------------------------------------------------------------ check-in
def test_checkin_mostra_nome_e_numero_antes_de_confirmar(cliente):
    event_id, ids, _ = montar_evento(participantes=3, presentes=0)
    rec = {}  # sem login
    base = f"/api/recepcao/{event_id}"

    achado = cliente.post(f"{base}/localizar", json={"matricula": " 00002 "}, headers=rec)
    assert achado.status_code == 200
    dados = achado.json()
    assert dados["nome"] == "Participante 2" and dados["matricula"] == "00002"
    assert dados["numero_sorteio"] == _numeros_por_id(ids[1])
    assert dados["presente"] is False
    # Sem dados alem do necessario.
    assert set(dados) == {
        "id", "matricula", "nome", "numero_sorteio", "matricula_da_sorte", "presente", "participando", "premios",
    }
    assert dados["matricula_da_sorte"] is None  # modo padrao: numero aleatorio
    assert dados["premios"] == []
    with session_scope() as db:
        assert db.get(Participant, ids[1]).presente is False  # localizar nao confirma nada

    assert cliente.post(f"{base}/localizar", json={"matricula": "99999"}, headers=rec).status_code == 404

    confirmado = cliente.post(f"{base}/checkin", json={"participante_id": ids[1]}, headers=rec)
    assert confirmado.status_code == 200
    assert confirmado.json()["presente"] is True and confirmado.json()["ja_estava_presente"] is False
    de_novo = cliente.post(f"{base}/checkin", json={"participante_id": ids[1]}, headers=rec)
    assert de_novo.json()["ja_estava_presente"] is True

    with session_scope() as db:
        registros = db.scalars(select(AuditLog).where(AuditLog.acao == "presenca_alterada")).all()
        assert len(registros) == 1  # repetir o check-in nao duplica a auditoria
        assert registros[0].usuario_id is None
        assert registros[0].detalhes["origem"] == "recepcao" and registros[0].detalhes["ip"]
        assert registros[0].detalhes["participante_id"] == ids[1]


def _numeros_por_id(pid: int) -> int:
    with session_scope() as db:
        return db.get(Participant, pid).numero_sorteio


def test_checkin_nao_alcanca_participante_de_outro_evento(cliente):
    a, _, _ = montar_evento(participantes=1)
    _, ids_b, _ = montar_evento(participantes=1)
    resposta = cliente.post(f"/api/recepcao/{a}/checkin", json={"participante_id": ids_b[0]})
    assert resposta.status_code == 404


# ------------------------------------------------------------------ consulta
def test_consulta_pelo_nome_sem_acento_ou_pela_matricula(cliente):
    event_id, ids, _ = montar_evento(participantes=2)
    with session_scope() as db:
        db.get(Participant, ids[0]).nome = "José da Conceição"
    rec = {}  # sem login
    url = f"/api/recepcao/{event_id}/consulta"

    por_nome = cliente.get(url, params={"q": "jose conceicao"}, headers=rec).json()
    assert [p["id"] for p in por_nome] == [ids[0]]
    assert por_nome[0]["numero_sorteio"] == _numeros_por_id(ids[0])
    por_matricula = cliente.get(url, params={"q": "00002"}, headers=rec).json()
    assert [p["id"] for p in por_matricula] == [ids[1]]
    assert cliente.get(url, params={"q": "x"}, headers=rec).status_code == 422
    assert cliente.get(url, params={"q": "ninguem"}, headers=rec).json() == []


# ------------------------------------------------------------------ publico e premios
def test_recepcao_nao_exige_login_e_lista_eventos(cliente):
    event_id, _, _ = montar_evento(participantes=1)
    eventos = cliente.get("/api/recepcao/eventos").json()
    assert [e["id"] for e in eventos] == [event_id]
    assert set(eventos[0]) == {"id", "nome", "empresa_nome", "logo_url", "demo"}
    assert cliente.post("/api/recepcao/999/localizar", json={"matricula": "1"}).status_code == 404


def test_consulta_mostra_o_premio_so_depois_da_revelacao(cliente, auth):
    from datetime import timedelta

    from sqlalchemy import update

    from app.models import Notificacao, utcnow

    event_id, ids, unidades = montar_evento(participantes=1)
    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "consulta-premio-1"},
        headers=auth,
    )
    url = f"/api/recepcao/{event_id}/consulta"
    # Telao ainda animando: a recepcao nao estraga a surpresa.
    assert cliente.get(url, params={"q": "00001"}).json()[0]["premios"] == []

    with session_scope() as db:
        db.execute(update(Notificacao).values(disponivel_em=utcnow() - timedelta(seconds=1)))
    (pessoa,) = cliente.get(url, params={"q": "00001"}).json()
    assert pessoa["premios"] == [{"premio_nome": "Premio Teste", "bloco_numero": None, "entregue": False}]
    localizado = cliente.post(f"/api/recepcao/{event_id}/localizar", json={"matricula": "00001"}).json()
    assert localizado["premios"][0]["premio_nome"] == "Premio Teste"


# ------------------------------------------------------------------ numero no telao
def test_telao_mostra_o_numero_do_ganhador_sem_matricula_nem_pulseira(cliente, auth):
    from datetime import timedelta

    from app.models import DisplayState, utcnow

    event_id, ids, unidades = montar_evento(participantes=1)
    with session_scope() as db:
        db.get(Participant, ids[0]).pulseira = "P-77"
        token = db.get(Event, event_id).telao_token
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "numero-telao-1"},
        headers=auth,
    )
    assert sorteio.status_code == 200, sorteio.text
    with session_scope() as db:
        db.get(DisplayState, event_id).revelar_em = utcnow() - timedelta(milliseconds=1)

    estado = cliente.get(f"/api/public/{token}/estado").json()
    assert estado["estado"] == "resultado"
    assert estado["ganhador"]["numero_sorteio"] == _numeros_por_id(ids[0])
    texto = str(estado)
    assert "00001" not in texto and "P-77" not in texto  # matricula e pulseira nunca vao ao telao

    # Encerramento (galeria) tambem leva o numero.
    cliente.post(f"/api/events/{event_id}/telao", json={"estado": "encerramento"}, headers=auth)
    galeria = cliente.get(f"/api/public/{token}/estado").json()["galeria"]
    assert galeria[0]["ganhador_numero"] == _numeros_por_id(ids[0])
