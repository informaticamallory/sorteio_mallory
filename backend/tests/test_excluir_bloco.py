"""Admin exclui bloco em qualquer situacao, sem perder historico de sorteios."""
from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, BlocoSorteio, Draw, Papel, PrizeUnit, User
from app.security import criar_token, hash_senha
from test_blocos import _acao, _blocos, _distribuir, _evento, _liberar_telao, _sortear_proxima, _url


def _bloco_com_um_sorteio(cliente, auth, finalizar: bool) -> tuple[int, int, int]:
    event_id = _evento([3, 2])
    (bloco,) = _distribuir(cliente, auth, event_id, 5).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    sorteio = _sortear_proxima(cliente, auth, event_id, bloco["id"], "excluir-bloco-01")
    if finalizar:
        _acao(cliente, auth, event_id, bloco["id"], "finalizar", {"confirmar_pendentes": True})
        cliente.post(f"/api/events/{event_id}/telao/carrossel", json={"acao": "encerrar"}, headers=auth)
    return event_id, bloco["id"], sorteio["id"]


def test_excluir_bloco_finalizado_com_sorteio_mantem_o_historico(cliente, auth):
    event_id, bloco_id, sorteio_id = _bloco_com_um_sorteio(cliente, auth, finalizar=True)

    assert cliente.delete(_url(event_id, f"/{bloco_id}"), headers=auth).status_code == 204

    resumo = _blocos(cliente, auth, event_id)
    assert resumo["blocos"] == []
    assert resumo["unidades_sem_bloco"] == 4  # os que faltavam sortear
    assert resumo["sorteadas_sem_bloco"] == 1
    assert cliente.get(_url(event_id, f"/{bloco_id}"), headers=auth).status_code == 404

    with session_scope() as db:
        bloco = db.get(BlocoSorteio, bloco_id)
        assert bloco is not None and bloco.excluido_em is not None
        sorteio = db.get(Draw, sorteio_id)
        assert sorteio.bloco_id == bloco_id and sorteio.status == "valido"
        assert db.get(PrizeUnit, sorteio.prize_unit_id).status == "sorteado"
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "bloco_removido"))
        assert registro.detalhes["sorteios_no_historico"] == 1
        assert registro.detalhes["unidades_liberadas"] == 4

    # O historico continua mostrando o bloco do sorteio, marcado como excluido.
    historico = cliente.get("/api/sorteios", params={"event_id": event_id}, headers=auth)
    assert historico.status_code == 200, historico.text
    (item,) = historico.json()["itens"]
    assert item["id"] == sorteio_id and item["bloco_nome"] == "Bloco 01 (excluído)"
    assert item["bloco_numero"] == 1

    # Os que faltavam podem ser distribuidos de novo e a numeracao recomeca do 01.
    (novo,) = _distribuir(cliente, auth, event_id, 10).json()["blocos"]
    assert novo["numero"] == 1 and novo["nome"] == "Bloco 01" and novo["total"] == 4
    with session_scope() as db:
        assert db.get(BlocoSorteio, bloco_id).numero_original == 1


def test_excluir_bloco_encerra_a_apresentacao_dele_no_telao(cliente, auth):
    from app.models import DisplayState

    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    _sortear_proxima(cliente, auth, event_id, bloco["id"], "excluir-bloco-03")
    # Finalizar inicia a apresentacao dos ganhadores no telao automaticamente.
    _acao(cliente, auth, event_id, bloco["id"], "finalizar", {"confirmar_pendentes": True})
    with session_scope() as db:
        assert db.get(DisplayState, event_id).carrossel_bloco_id == bloco["id"]

    assert cliente.delete(_url(event_id, f"/{bloco['id']}"), headers=auth).status_code == 204
    with session_scope() as db:
        ds = db.get(DisplayState, event_id)
        assert ds.carrossel_bloco_id is None and ds.estado == "aguardando"


def test_excluir_bloco_em_andamento_com_sorteio_libera_outro_bloco(cliente, auth):
    event_id, bloco_id, _sorteio = _bloco_com_um_sorteio(cliente, auth, finalizar=False)
    _liberar_telao(event_id)

    assert cliente.delete(_url(event_id, f"/{bloco_id}"), headers=auth).status_code == 204
    (novo,) = _distribuir(cliente, auth, event_id, 10).json()["blocos"]
    assert _acao(cliente, auth, event_id, novo["id"], "iniciar").status_code == 200
    _sortear_proxima(cliente, auth, event_id, novo["id"], "excluir-bloco-02")


def test_nao_exclui_durante_a_revelacao_no_telao(cliente, auth):
    event_id, bloco_id, _sorteio = _bloco_com_um_sorteio(cliente, auth, finalizar=False)
    # _sortear_proxima ja liberou o telao; simula outro sorteio ainda revelando.
    with session_scope() as db:
        from app.models import DisplayState, utcnow
        from datetime import timedelta

        ds = db.get(DisplayState, event_id)
        ds.estado = "sorteando"
        ds.revelar_em = utcnow() + timedelta(seconds=30)
    assert cliente.delete(_url(event_id, f"/{bloco_id}"), headers=auth).status_code == 409


def test_so_o_admin_exclui(cliente, auth):
    event_id = _evento([2])
    (bloco,) = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    with session_scope() as db:
        user = User(
            usuario="rh.organizador",
            nome="RH",
            senha_hash=hash_senha("senha-forte1"),
            papel=Papel.ORGANIZADOR.value,
        )
        db.add(user)
        db.flush()
        organizador = {"Authorization": f"Bearer {criar_token(user.id, user.sessao_versao)}"}
    assert cliente.delete(_url(event_id, f"/{bloco['id']}"), headers=organizador).status_code == 403
    assert cliente.delete(_url(event_id, f"/{bloco['id']}"), headers=auth).status_code == 204
