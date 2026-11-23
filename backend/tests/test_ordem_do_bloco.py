"""Modo blocos: os premios saem na sequencia do bloco.

Pular para outro premio do bloco so com a permissao PULAR_ORDEM_DO_BLOCO
(administrador) e um motivo, que fica na auditoria do sorteio.
"""
from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, Papel, User
from app.security import criar_token, hash_senha
from test_blocos import _acao, _disponiveis, _distribuir, _evento, _liberar_telao, _sortear


def _bloco_iniciado(cliente, auth) -> tuple[int, int, list[int]]:
    event_id = _evento([2, 2])
    (bloco,) = _distribuir(cliente, auth, event_id, 4).json()["blocos"]
    assert _acao(cliente, auth, event_id, bloco["id"], "iniciar").status_code == 200
    return event_id, bloco["id"], _disponiveis(cliente, auth, event_id, bloco["id"])


def _operador() -> dict:
    with session_scope() as db:
        user = User(
            usuario="operador.sorteio",
            nome="Operador",
            senha_hash=hash_senha("senha-forte1"),
            papel=Papel.SORTEIO.value,
        )
        db.add(user)
        db.flush()
        return {"Authorization": f"Bearer {criar_token(user.id, user.sessao_versao)}"}


def _elegiveis(cliente, headers, event_id, unidade_id) -> dict:
    resposta = cliente.get(
        f"/api/events/{event_id}/sorteio/elegiveis", params={"prize_unit_id": unidade_id}, headers=headers
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_operador_so_sorteia_o_proximo_da_sequencia(cliente, auth):
    event_id, _bloco, (u1, u2, *_resto) = _bloco_iniciado(cliente, auth)
    operador = _operador()

    fora = _sortear(cliente, operador, event_id, u2, "operador-fora-0001", "quero pular")
    assert fora.status_code == 409
    assert "sequência do bloco" in fora.json()["detail"]

    conferencia = _elegiveis(cliente, operador, event_id, u2)
    assert conferencia["fora_da_ordem"] is True
    assert conferencia["proxima_unidade_id"] == u1
    assert conferencia["pode_sortear"] is False

    assert _elegiveis(cliente, operador, event_id, u1)["fora_da_ordem"] is False
    assert _sortear(cliente, operador, event_id, u1, "operador-certo-0001").status_code == 200


def test_admin_pula_a_ordem_so_com_motivo_e_fica_na_auditoria(cliente, auth):
    event_id, _bloco, (u1, u2, *_resto) = _bloco_iniciado(cliente, auth)

    conferencia = _elegiveis(cliente, auth, event_id, u2)
    assert conferencia["fora_da_ordem"] is True and conferencia["pode_sortear"] is True

    sem_motivo = _sortear(cliente, auth, event_id, u2, "admin-sem-motivo-01")
    assert sem_motivo.status_code == 422
    assert _sortear(cliente, auth, event_id, u2, "admin-motivo-curto", "ok").status_code == 422

    com_motivo = _sortear(cliente, auth, event_id, u2, "admin-com-motivo-01", "Patrocinador pediu")
    assert com_motivo.status_code == 200, com_motivo.text

    with session_scope() as db:
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "sorteio_realizado"))
        assert registro.detalhes["unidade_id"] == u2
        assert registro.detalhes["fora_da_ordem"]["motivo"] == "Patrocinador pediu"
        assert registro.detalhes["fora_da_ordem"]["proxima_unidade_id"] == u1


def test_sorteio_na_ordem_nao_marca_fora_da_ordem(cliente, auth):
    event_id, _bloco, (u1, *_resto) = _bloco_iniciado(cliente, auth)
    assert _sortear(cliente, auth, event_id, u1, "na-ordem-000001").status_code == 200
    with session_scope() as db:
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "sorteio_realizado"))
        assert "fora_da_ordem" not in registro.detalhes


def test_premio_anulado_volta_a_ser_o_proximo(cliente, auth):
    event_id, _bloco, (u1, u2, *_resto) = _bloco_iniciado(cliente, auth)
    operador = _operador()

    primeiro = _sortear(cliente, operador, event_id, u1, "anulado-0000001")
    assert primeiro.status_code == 200
    _liberar_telao(event_id)
    anulado = cliente.post(
        f"/api/events/{event_id}/sorteios/{primeiro.json()['id']}/anular",
        json={"motivo": "Ganhador ausente", "tipo": "ausencia"},
        headers=auth,
    )
    assert anulado.status_code == 200, anulado.text

    # A unidade 1 voltou a ficar disponivel e e de novo a proxima da sequencia.
    assert _sortear(cliente, operador, event_id, u2, "anulado-0000002").status_code == 409
    assert _sortear(cliente, operador, event_id, u1, "anulado-0000003").status_code == 200
