"""Distribuir nos blocos ja criados e numeracao que recomeca do 01."""
from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import PrizeUnit
from test_blocos import _acao, _blocos, _distribuir, _evento, _sortear_proxima, _url


def _criar(cliente, auth, event_id, nome, capacidade):
    resposta = cliente.post(_url(event_id), json={"nome": nome, "capacidade": capacidade}, headers=auth)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_preenche_os_blocos_criados_na_ordem_e_deixa_a_sobra_sem_bloco(cliente, auth):
    event_id = _evento([6, 4])  # 10 unidades
    abertura = _criar(cliente, auth, event_id, "Abertura", 4)
    especiais = _criar(cliente, auth, event_id, "Especiais", 3)

    previa = cliente.post(_url(event_id, "/distribuir-nos-blocos/previa"), headers=auth)
    assert previa.status_code == 200, previa.text
    assert previa.json() == {
        "unidades": 10,
        "blocos": [
            {"numero": abertura["numero"], "nome": "Abertura", "unidades": 4, "capacidade": 4},
            {"numero": especiais["numero"], "nome": "Especiais", "unidades": 3, "capacidade": 3},
        ],
        "sobra": 3,
    }
    assert _blocos(cliente, auth, event_id)["unidades_sem_bloco"] == 10  # previa nao grava

    feito = cliente.post(_url(event_id, "/distribuir-nos-blocos"), json={"misturar": True}, headers=auth)
    assert feito.status_code == 200, feito.text
    resumo = feito.json()
    # Os mesmos blocos (ids, nomes e capacidades), agora cheios; a sobra fica sem bloco.
    assert [(b["id"], b["nome"], b["total"], b["capacidade"]) for b in resumo["blocos"]] == [
        (abertura["id"], "Abertura", 4, 4),
        (especiais["id"], "Especiais", 3, 3),
    ]
    assert resumo["unidades_sem_bloco"] == 3
    with session_scope() as db:
        ordem = [
            u.prize_id
            for u in db.scalars(
                select(PrizeUnit).where(PrizeUnit.bloco_id == abertura["id"]).order_by(PrizeUnit.ordem_bloco)
            )
        ]
    assert all(a != b for a, b in zip(ordem, ordem[1:]))  # misturado, sem repetir em seguida


def test_sem_blocos_planejados_pede_para_criar(cliente, auth):
    event_id = _evento([3])
    resposta = cliente.post(_url(event_id, "/distribuir-nos-blocos/previa"), headers=auth)
    assert resposta.status_code == 409 and "Não há blocos planejados" in resposta.json()["detail"]


def test_excluir_planejado_renumera_os_seguintes(cliente, auth):
    event_id = _evento([6])
    _distribuir(cliente, auth, event_id, 2)  # Blocos 01, 02, 03
    b1, b2, b3 = _blocos(cliente, auth, event_id)["blocos"]
    assert cliente.delete(_url(event_id, f"/{b1['id']}"), headers=auth).status_code == 204
    restantes = _blocos(cliente, auth, event_id)["blocos"]
    assert [(b["id"], b["numero"], b["nome"]) for b in restantes] == [
        (b2["id"], 1, "Bloco 01"),
        (b3["id"], 2, "Bloco 02"),
    ]


def test_excluido_com_sorteio_libera_o_numero_e_iniciados_nao_mudam(cliente, auth):
    event_id = _evento([6])
    _distribuir(cliente, auth, event_id, 2)  # 01, 02, 03
    b1, b2, b3 = _blocos(cliente, auth, event_id)["blocos"]
    _acao(cliente, auth, event_id, b1["id"], "iniciar")
    _sortear_proxima(cliente, auth, event_id, b1["id"], "renumera-01")
    _acao(cliente, auth, event_id, b1["id"], "finalizar", {"confirmar_pendentes": True})
    cliente.post(f"/api/events/{event_id}/telao/carrossel", json={"acao": "encerrar"}, headers=auth)
    _acao(cliente, auth, event_id, b2["id"], "iniciar")
    _sortear_proxima(cliente, auth, event_id, b2["id"], "renumera-02")

    # Exclui o 01 (com sorteio): o 02 ja iniciado fica 02; o planejado vira 03.
    assert cliente.delete(_url(event_id, f"/{b1['id']}"), headers=auth).status_code == 204
    numeros = [(b["id"], b["numero"]) for b in _blocos(cliente, auth, event_id)["blocos"]]
    assert numeros == [(b2["id"], 2), (b3["id"], 3)]
    # Um bloco novo ganha o 04 (o 01 do excluido nao volta para tras de um iniciado).
    novo = _criar(cliente, auth, event_id, "", 5)
    assert novo["numero"] == 4
