"""Modo faixa de matriculas: a matricula e o numero da sorte exibido.

Modo padrao (numero da sorte): nada muda, o telao continua sem matricula.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.database import session_scope
from app.models import DisplayState, Event, Participant, User, utcnow
from app.routers.autocadastro import cartao
from conftest import montar_evento


def _preparar(cliente, auth, *, faixa: bool):
    event_id, ids, unidades = montar_evento(participantes=1)
    if faixa:
        r = cliente.patch(
            f"/api/events/{event_id}/regras",
            json={"modo_sorteio": "faixa_matricula", "matricula_faixa_inicio": 1, "matricula_faixa_fim": 10},
            headers=auth,
        )
        assert r.status_code == 200, r.text
    with session_scope() as db:
        # A conta logada (admin) tambem e participante: ve o proprio cartao.
        db.get(Participant, ids[0]).usuario_id = db.scalars(select(User)).first().id
        token = db.get(Event, event_id).telao_token
    r = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": f"mds-{faixa:d}-000"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    with session_scope() as db:
        db.get(DisplayState, event_id).revelar_em = utcnow() - timedelta(milliseconds=1)
    return event_id, ids[0], token


def _telas(cliente, auth, event_id, pid, token):
    with session_scope() as db:
        cartao_cadastro = cartao(db.get(Event, event_id), db.get(Participant, pid))
    area = cliente.get("/api/minha-area", headers=auth).json()["participacoes"][0]
    consulta = cliente.get(f"/api/recepcao/{event_id}/consulta", params={"q": "00001"}).json()[0]
    telao = cliente.get(f"/api/public/{token}/estado").json()
    cliente.post(f"/api/events/{event_id}/telao", json={"estado": "encerramento"}, headers=auth)
    galeria = cliente.get(f"/api/public/{token}/estado").json()["galeria"][0]
    return cartao_cadastro, area, consulta, telao, galeria


def test_modo_padrao_mostra_o_numero_aleatorio_e_telao_sem_matricula(cliente, auth):
    event_id, pid, token = _preparar(cliente, auth, faixa=False)
    cartao_cadastro, area, consulta, telao, galeria = _telas(cliente, auth, event_id, pid, token)

    assert cartao_cadastro.matricula_da_sorte is None
    assert area["matricula_da_sorte"] is None and area["numero_sorteio"] is not None
    assert consulta["matricula_da_sorte"] is None
    assert telao["estado"] == "resultado"
    assert "matricula" not in str(telao) and "00001" not in str(telao)
    assert "matricula" not in str(galeria) and "00001" not in str(galeria)


def test_modo_faixa_mostra_a_matricula_no_cartao_na_consulta_e_no_telao(cliente, auth):
    event_id, pid, token = _preparar(cliente, auth, faixa=True)
    cartao_cadastro, area, consulta, telao, galeria = _telas(cliente, auth, event_id, pid, token)

    assert cartao_cadastro.matricula_da_sorte == "00001"
    assert area["matricula_da_sorte"] == "00001"
    assert consulta["matricula_da_sorte"] == "00001"
    assert telao["ganhador"]["matricula_da_sorte"] == "00001"
    assert galeria["ganhador_matricula_da_sorte"] == "00001"
    # O numero aleatorio continua existindo (QR Code e busca da Central de Entregas).
    assert telao["ganhador"]["numero_sorteio"] == area["numero_sorteio"] is not None


def test_voltar_ao_modo_padrao_volta_ao_numero_aleatorio(cliente, auth):
    event_id, pid, token = _preparar(cliente, auth, faixa=True)
    cliente.patch(f"/api/events/{event_id}/regras", json={"modo_sorteio": "numero_sorte"}, headers=auth)
    area = cliente.get("/api/minha-area", headers=auth).json()["participacoes"][0]
    assert area["matricula_da_sorte"] is None
    assert "matricula" not in str(cliente.get(f"/api/public/{token}/estado").json())
