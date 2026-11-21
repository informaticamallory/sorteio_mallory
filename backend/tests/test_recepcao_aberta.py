"""Recepcao sem login so funciona com a chave do evento ligada."""
from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, Event, Participant
from conftest import montar_evento


def _rotas(event_id: int, participante_id: int):
    base = f"/api/recepcao/{event_id}"
    return [
        ("post", f"{base}/localizar", {"json": {"matricula": "00001"}}),
        ("post", f"{base}/checkin", {"json": {"participante_id": participante_id}}),
        ("get", f"{base}/consulta", {"params": {"q": "00001"}}),
    ]


def test_evento_novo_nasce_com_a_recepcao_fechada(cliente, auth):
    r = cliente.post("/api/events", json={"nome": "Festa", "empresa_nome": "Mallory"}, headers=auth)
    assert r.status_code in (200, 201), r.text
    assert r.json()["recepcao_publica_ativa"] is False


def test_recepcao_fechada_bloqueia_checkin_e_consulta(cliente):
    event_id, ids, _ = montar_evento(participantes=2, presentes=0, recepcao_publica=False)

    assert cliente.get("/api/recepcao/eventos").json() == []
    for metodo, url, extra in _rotas(event_id, ids[0]):
        r = getattr(cliente, metodo)(url, **extra)
        assert r.status_code == 403, (url, r.text)
        assert "não foi aberta" in r.json()["detail"]

    with session_scope() as db:
        assert db.get(Participant, ids[0]).presente is False  # check-in nao passou


def test_admin_abre_a_recepcao_pela_configuracao(cliente, auth):
    event_id, ids, _ = montar_evento(participantes=2, presentes=0, recepcao_publica=False)

    r = cliente.patch(f"/api/events/{event_id}", json={"recepcao_publica_ativa": True}, headers=auth)
    assert r.status_code == 200 and r.json()["recepcao_publica_ativa"] is True

    assert [e["id"] for e in cliente.get("/api/recepcao/eventos").json()] == [event_id]
    feito = cliente.post(f"/api/recepcao/{event_id}/checkin", json={"participante_id": ids[0]})
    assert feito.status_code == 200 and feito.json()["presente"] is True

    with session_scope() as db:
        log = db.scalars(select(AuditLog).where(AuditLog.acao == "evento_configurado")).one()
        assert "recepcao_publica_ativa" in log.detalhes["campos"]

    # Fechar de novo bloqueia na hora.
    cliente.patch(f"/api/events/{event_id}", json={"recepcao_publica_ativa": False}, headers=auth)
    assert cliente.post(f"/api/recepcao/{event_id}/localizar", json={"matricula": "00002"}).status_code == 403


def test_so_aparecem_eventos_com_a_recepcao_aberta(cliente):
    aberto, _, _ = montar_evento(participantes=1, recepcao_publica=True)
    montar_evento(participantes=1, recepcao_publica=False)
    with session_scope() as db:
        assert db.scalar(select(Event.id).where(Event.id == aberto)) is not None
    assert [e["id"] for e in cliente.get("/api/recepcao/eventos").json()] == [aberto]
