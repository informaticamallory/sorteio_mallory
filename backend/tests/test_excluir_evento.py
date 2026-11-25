"""Apagar evento: so o admin, so sem sorteio, com o nome digitado."""
from __future__ import annotations

from sqlalchemy import func, select

from app.database import session_scope
from app.models import AuditLog, DisplayState, Event, Participant, Prize, PrizeUnit
from apoio import cabecalho, conta
from conftest import montar_evento


def _apagar(cliente, cab, event_id, nome):
    return cliente.request("DELETE", f"/api/events/{event_id}", json={"nome_confirmacao": nome}, headers=cab)


def test_admin_apaga_evento_sem_sorteio_com_o_nome_digitado(cliente, auth):
    event_id, _participantes, _unidades = montar_evento(participantes=3, quantidade_premio=2)
    with session_scope() as db:
        nome = db.get(Event, event_id).nome

    organizador = cabecalho(conta("ORGANIZADOR", login="rh-apaga"))
    assert _apagar(cliente, organizador, event_id, nome).status_code == 403
    assert _apagar(cliente, auth, event_id, "outro nome").status_code == 422
    assert _apagar(cliente, auth, event_id, f"  {nome.upper()} ").status_code == 204

    assert cliente.get(f"/api/events/{event_id}", headers=auth).status_code == 404
    with session_scope() as db:
        assert db.get(Event, event_id) is None
        for modelo, coluna in ((Participant, Participant.event_id), (Prize, Prize.event_id)):
            assert db.scalar(select(func.count(modelo.id)).where(coluna == event_id)) == 0
        assert db.scalar(select(func.count(PrizeUnit.id))) == 0
        assert db.get(DisplayState, event_id) is None
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "evento_excluido"))
        assert registro.event_id is None and registro.detalhes["nome"] == nome
        assert registro.detalhes["participantes"] == 3


def test_evento_com_sorteio_nao_e_apagado(cliente, auth):
    event_id, _participantes, unidades = montar_evento(participantes=2)
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "apaga-evento-01"},
        headers=auth,
    )
    assert sorteio.status_code == 200, sorteio.text
    with session_scope() as db:
        nome = db.get(Event, event_id).nome
    resposta = _apagar(cliente, auth, event_id, nome)
    assert resposta.status_code == 409 and "sorteio" in resposta.json()["detail"]
    with session_scope() as db:
        assert db.get(Event, event_id) is not None
