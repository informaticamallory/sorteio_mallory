"""Reabrir um bloco finalizado que ainda tem premios sem sorteio."""
from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, BlocoSorteio, Draw
from test_blocos import _acao, _blocos, _distribuir, _evento, _liberar_telao, _sortear_proxima


def _finalizado_com_pendentes(cliente, auth) -> tuple[int, int]:
    event_id = _evento([4])
    (bloco,) = _distribuir(cliente, auth, event_id, 4).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    _sortear_proxima(cliente, auth, event_id, bloco["id"], "reabrir-0000001")
    # Encerra a apresentacao automatica para nao interferir nos sorteios seguintes.
    finalizado = _acao(cliente, auth, event_id, bloco["id"], "finalizar", {"confirmar_pendentes": True})
    assert finalizado.status_code == 200, finalizado.text
    cliente.post(f"/api/events/{event_id}/telao/carrossel", json={"acao": "encerrar"}, headers=auth)
    return event_id, bloco["id"]


def test_reabre_finalizado_com_pendentes_e_continua_sorteando(cliente, auth):
    event_id, bloco_id = _finalizado_com_pendentes(cliente, auth)

    resposta = _acao(cliente, auth, event_id, bloco_id, "reabrir")
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["status"] == "PAUSADO"
    assert corpo["finalizado_em"] is None and corpo["restantes"] == 3 and corpo["sorteadas"] == 1

    # Os remanescentes deixam de contar: os premios voltaram para o bloco.
    assert _blocos(cliente, auth, event_id)["unidades_remanescentes"] == 0

    assert _acao(cliente, auth, event_id, bloco_id, "iniciar").status_code == 200
    _liberar_telao(event_id)
    _sortear_proxima(cliente, auth, event_id, bloco_id, "reabrir-0000002")

    with session_scope() as db:
        assert len(db.scalars(select(Draw).where(Draw.event_id == event_id)).all()) == 2
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "bloco_reaberto"))
        assert registro.detalhes["bloco_id"] == bloco_id
        assert registro.detalhes["restantes"] == 3
        assert registro.detalhes["finalizado_em"] is not None
        assert registro.detalhes["finalizado_por_id"] is not None


def test_nao_reabre_bloco_que_nao_esta_finalizado(cliente, auth):
    event_id = _evento([2])
    (bloco,) = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    assert _acao(cliente, auth, event_id, bloco["id"], "reabrir").status_code == 409
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    assert _acao(cliente, auth, event_id, bloco["id"], "reabrir").status_code == 409


def test_nao_reabre_quando_os_pendentes_foram_para_remanescentes(cliente, auth):
    event_id, bloco_id = _finalizado_com_pendentes(cliente, auth)
    criado = cliente.post(f"/api/events/{event_id}/blocos/remanescentes", json={"capacidade": 10}, headers=auth)
    assert criado.status_code == 201, criado.text

    resposta = _acao(cliente, auth, event_id, bloco_id, "reabrir")
    assert resposta.status_code == 409
    assert "Não há o que reabrir" in resposta.json()["detail"]
    with session_scope() as db:
        assert db.get(BlocoSorteio, bloco_id).status == "FINALIZADO"
