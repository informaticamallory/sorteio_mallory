"""Admin exclui premio que ja teve sorteio, sem perder o historico."""
from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, DisplayState, Draw, Papel, Prize, PrizeUnit, User
from app.security import criar_token, hash_senha
from test_blocos import _distribuir, _evento, _liberar_telao, _sortear


def _premio_e_unidades(event_id: int) -> tuple[int, list[int]]:
    with session_scope() as db:
        premio = db.scalar(select(Prize).where(Prize.event_id == event_id))
        return premio.id, [u.id for u in premio.unidades]


def _url(event_id: int, prize_id: int) -> str:
    return f"/api/events/{event_id}/premios/{prize_id}"


def _anular(cliente, auth, event_id, sorteio_id):
    resposta = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio_id}/anular",
        json={"motivo": "teste de anulacao", "tipo": "erro_operacional", "confirmar_estorno": True},
        headers=auth,
    )
    assert resposta.status_code == 200, resposta.text


def _organizador() -> dict:
    with session_scope() as db:
        user = User(
            usuario="rh.premios",
            nome="RH",
            senha_hash=hash_senha("senha-forte1"),
            papel=Papel.ORGANIZADOR.value,
        )
        db.add(user)
        db.flush()
        return {"Authorization": f"Bearer {criar_token(user.id, user.sessao_versao)}"}


def test_premio_sem_sorteio_continua_sendo_apagado(cliente, auth):
    event_id = _evento([3])
    prize_id, _ = _premio_e_unidades(event_id)
    # Quem cadastra premios (organizador) exclui premio sem sorteio, como antes.
    assert cliente.delete(_url(event_id, prize_id), headers=_organizador()).status_code == 204
    with session_scope() as db:
        assert db.get(Prize, prize_id) is None


def test_admin_exclui_premio_so_com_sorteio_anulado(cliente, auth):
    # O caso do print: todas as unidades "Disponivel", mas houve sorteio anulado.
    event_id = _evento([3])
    prize_id, unidades = _premio_e_unidades(event_id)
    sorteio = _sortear(cliente, auth, event_id, unidades[0], "premio-anulado-01")
    assert sorteio.status_code == 200, sorteio.text
    _liberar_telao(event_id)
    _anular(cliente, auth, event_id, sorteio.json()["id"])

    assert cliente.delete(_url(event_id, prize_id), headers=_organizador()).status_code == 403
    assert cliente.delete(_url(event_id, prize_id), headers=auth).status_code == 204

    assert cliente.get(f"/api/events/{event_id}/premios", headers=auth).json() == []
    assert cliente.patch(_url(event_id, prize_id), json={"nome": "x"}, headers=auth).status_code == 404
    with session_scope() as db:
        premio = db.get(Prize, prize_id)
        assert premio is not None and premio.excluido_em is not None
        # A unidade com sorteio anulado fica so pelo historico; as outras foram apagadas.
        assert db.get(PrizeUnit, unidades[0]).status == "removido"
        assert db.get(PrizeUnit, unidades[1]) is None and db.get(PrizeUnit, unidades[2]) is None
        assert db.get(Draw, sorteio.json()["id"]).status == "anulado"
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "premio_removido"))
        assert registro.detalhes["sorteios_no_historico"] == 1
        assert registro.detalhes["unidades_retiradas"] == 1 and registro.detalhes["unidades_apagadas"] == 2

    # A unidade retirada nao pode mais ser sorteada.
    assert _sortear(cliente, auth, event_id, unidades[0], "premio-anulado-02").status_code in (404, 409, 422)
    resumo = cliente.get(f"/api/events/{event_id}/resumo", headers=auth).json()
    assert resumo["premios_total"] == 0 and resumo["unidades_total"] == 0


def test_excluir_premio_com_ganhador_mantem_resultado_e_entrega(cliente, auth):
    event_id = _evento([2])
    prize_id, unidades = _premio_e_unidades(event_id)
    sorteio = _sortear(cliente, auth, event_id, unidades[0], "premio-valido-01")
    assert sorteio.status_code == 200, sorteio.text
    _liberar_telao(event_id)

    assert cliente.delete(_url(event_id, prize_id), headers=auth).status_code == 204

    with session_scope() as db:
        assert db.get(Draw, sorteio.json()["id"]).status == "valido"
        assert db.get(PrizeUnit, unidades[0]).status == "sorteado"
        assert db.get(PrizeUnit, unidades[1]) is None  # sobra sem sorteio
    # O ganhador continua no historico e pode retirar o premio.
    historico = cliente.get("/api/sorteios", params={"event_id": event_id}, headers=auth).json()["itens"]
    assert [i["id"] for i in historico] == [sorteio.json()["id"]]
    entrega = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio.json()['id']}/entrega", json={"entregue": True}, headers=auth
    )
    assert entrega.status_code == 200, entrega.text
    resumo = cliente.get(f"/api/events/{event_id}/resumo", headers=auth).json()
    assert resumo["premios_total"] == 0 and resumo["unidades_total"] == 1 and resumo["unidades_entregues"] == 1

    # Anular depois da exclusao nao devolve a unidade ao sorteio.
    _anular(cliente, auth, event_id, sorteio.json()["id"])
    with session_scope() as db:
        assert db.get(PrizeUnit, unidades[0]).status == "removido"


def test_excluir_premio_tira_as_sobras_dos_blocos(cliente, auth):
    event_id = _evento([2, 2])
    _distribuir(cliente, auth, event_id, 4)
    with session_scope() as db:
        premio = db.scalars(select(Prize).where(Prize.event_id == event_id).order_by(Prize.ordem)).first()
        prize_id, unidades = premio.id, [u.id for u in premio.unidades]
        bloco_id = db.get(PrizeUnit, unidades[0]).bloco_id
    cliente.post(f"/api/events/{event_id}/blocos/{bloco_id}/iniciar", json={}, headers=auth)
    assert _sortear(cliente, auth, event_id, unidades[0], "premio-bloco-01").status_code == 200
    _liberar_telao(event_id)

    assert cliente.delete(_url(event_id, prize_id), headers=auth).status_code == 204
    (bloco,) = cliente.get(f"/api/events/{event_id}/blocos", headers=auth).json()["blocos"]
    assert bloco["id"] == bloco_id
    # Fica a unidade sorteada (resultado valido) e as 2 do outro premio.
    assert bloco["total"] == 3 and bloco["sorteadas"] == 1 and bloco["restantes"] == 2


def test_nao_exclui_durante_a_revelacao(cliente, auth):
    from datetime import timedelta

    from app.models import utcnow

    event_id = _evento([2])
    prize_id, unidades = _premio_e_unidades(event_id)
    assert _sortear(cliente, auth, event_id, unidades[0], "premio-revelando").status_code == 200
    with session_scope() as db:
        ds = db.get(DisplayState, event_id)
        ds.estado = "sorteando"
        ds.revelar_em = utcnow() + timedelta(seconds=30)
    assert cliente.delete(_url(event_id, prize_id), headers=auth).status_code == 409
