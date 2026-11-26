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


def test_evento_de_teste_com_sorteios_e_apagado_pelo_admin_com_tudo_dele(cliente, auth):
    from app.models import Draw, Notificacao

    # Evento real ao lado: nao pode ser afetado.
    real_id, _p, unidades_reais = montar_evento(participantes=2)
    real = cliente.post(f"/api/events/{real_id}/sorteio", json={"prize_unit_id": unidades_reais[0], "idempotency_key": "evento-real-01"}, headers=auth)
    assert real.status_code == 200, real.text

    event_id, _participantes, unidades = montar_evento(participantes=3, quantidade_premio=2)
    for i, unidade in enumerate(unidades):
        resposta = cliente.post(
            f"/api/events/{event_id}/sorteio",
            json={"prize_unit_id": unidade, "idempotency_key": f"teste-apaga-{i}"},
            headers=auth,
        )
        assert resposta.status_code == 200, resposta.text
    with session_scope() as db:
        nome = db.get(Event, event_id).nome
        auditoria_do_evento = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.event_id == event_id))
        assert db.scalar(select(func.count(Notificacao.id)).where(Notificacao.event_id == event_id)) == 2

    # Sem a marca de teste: bloqueado, com a orientacao de como fazer.
    resposta = _apagar(cliente, auth, event_id, nome)
    assert resposta.status_code == 409 and "Evento de teste" in resposta.json()["detail"]

    # Marcado como teste, mas sem confirmar os sorteios: bloqueado.
    cliente.patch(f"/api/events/{event_id}", json={"evento_teste": True}, headers=auth)
    resposta = _apagar(cliente, auth, event_id, nome)
    assert resposta.status_code == 409 and "Confirme" in resposta.json()["detail"]

    # Organizador - RH nunca apaga.
    organizador = cabecalho(conta("ORGANIZADOR", login="rh-apaga-teste"))
    resposta = cliente.request(
        "DELETE", f"/api/events/{event_id}", json={"nome_confirmacao": nome, "apagar_sorteios": True}, headers=organizador
    )
    assert resposta.status_code == 403

    resposta = cliente.request(
        "DELETE", f"/api/events/{event_id}", json={"nome_confirmacao": nome, "apagar_sorteios": True}, headers=auth
    )
    assert resposta.status_code == 204, resposta.text
    with session_scope() as db:
        assert db.get(Event, event_id) is None
        assert db.scalar(select(func.count(Draw.id)).where(Draw.event_id == event_id)) == 0
        assert db.scalar(select(func.count(Notificacao.id)).where(Notificacao.event_id == event_id)) == 0
        assert db.scalar(select(func.count(Participant.id)).where(Participant.event_id == event_id)) == 0
        # Auditoria preservada (sem o vinculo) + registro do que foi apagado.
        sem_evento = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.event_id.is_(None)))
        assert sem_evento >= auditoria_do_evento + 1
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "evento_excluido"))
        assert registro.detalhes["sorteios"] == 2 and registro.detalhes["evento_teste"] is True
        # O evento real continua intacto.
        assert db.get(Event, real_id) is not None
        assert db.scalar(select(func.count(Draw.id)).where(Draw.event_id == real_id)) == 1
