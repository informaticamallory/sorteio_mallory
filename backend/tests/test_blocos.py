"""Fase 2: distribuicao, execucao e encerramento de sorteios por blocos."""

from __future__ import annotations

import threading
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database import engine, session_scope
from app.models import (
    BlocoSorteio,
    DisplayState,
    Draw,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    utcnow,
)
from app.security import novo_token_telao


# ------------------------------------------------------------------ apoio
def _evento(quantidades: list[int], participantes: int = 60) -> int:
    """Evento com um premio por item de `quantidades` (cada um com N unidades)."""
    with session_scope() as db:
        evento = Event(
            nome="Evento Blocos", telao_token=novo_token_telao(), duracao_animacao_ms=1000
        )
        db.add(evento)
        db.flush()
        db.add(DisplayState(event_id=evento.id, versao=1))
        for i in range(participantes):
            db.add(
                Participant(
                    event_id=evento.id, nome=f"Pessoa {i + 1}", matricula=f"{i + 1:05d}", presente=True
                )
            )
        for ordem, quantidade in enumerate(quantidades, start=1):
            premio = Prize(event_id=evento.id, nome=f"Premio {ordem}", quantidade=quantidade, ordem=ordem)
            db.add(premio)
            db.flush()
            for numero in range(1, quantidade + 1):
                db.add(PrizeUnit(prize_id=premio.id, numero=numero))
        db.flush()
        return evento.id


def _url(event_id: int, sufixo: str = "") -> str:
    return f"/api/events/{event_id}/blocos{sufixo}"


def _distribuir(cliente, auth, event_id, capacidade=None):
    corpo = {} if capacidade is None else {"capacidade": capacidade}
    return cliente.post(_url(event_id, "/distribuir"), json=corpo, headers=auth)


def _blocos(cliente, auth, event_id) -> dict:
    resposta = cliente.get(_url(event_id), headers=auth)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _acao(cliente, auth, event_id, bloco_id, acao, corpo=None):
    return cliente.post(_url(event_id, f"/{bloco_id}/{acao}"), json=corpo or {}, headers=auth)


def _detalhe(cliente, auth, event_id, bloco_id) -> dict:
    return cliente.get(_url(event_id, f"/{bloco_id}"), headers=auth).json()


def _sortear(cliente, auth, event_id, unidade_id, chave):
    return cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidade_id, "idempotency_key": chave},
        headers=auth,
    )


def _liberar_telao(event_id: int) -> None:
    """Simula o fim da animacao no telao (equivale a esperar duracao_animacao_ms)."""
    with session_scope() as db:
        ds = db.get(DisplayState, event_id)
        if ds and ds.revelar_em:
            ds.revelar_em = utcnow() - timedelta(seconds=1)


def _disponiveis(cliente, auth, event_id, bloco_id) -> list[int]:
    return [
        u["id"]
        for u in _detalhe(cliente, auth, event_id, bloco_id)["unidades"]
        if u["status"] == "disponivel"
    ]


def _sortear_proxima(cliente, auth, event_id, bloco_id, chave):
    unidade = _disponiveis(cliente, auth, event_id, bloco_id)[0]
    resposta = _sortear(cliente, auth, event_id, unidade, chave)
    assert resposta.status_code == 200, resposta.text
    _liberar_telao(event_id)
    return resposta.json()


# ------------------------------------------------------------------ distribuicao automatica
@pytest.mark.parametrize(
    "quantidades,esperado",
    [
        ([25], [25]),
        ([26], [25, 1]),
        ([100], [25, 25, 25, 25]),
        ([107], [25, 25, 25, 25, 7]),
        # Mesmo total espalhado em tipos de premio diferentes: conta UNIDADES.
        ([1, 3, 50, 53], [25, 25, 25, 25, 7]),
    ],
    ids=["25", "26", "100", "107", "107-em-4-tipos"],
)
def test_distribuicao_automatica_por_unidades(cliente, auth, quantidades, esperado):
    event_id = _evento(quantidades)
    resposta = _distribuir(cliente, auth, event_id, 25)
    assert resposta.status_code == 200, resposta.text

    dados = resposta.json()
    assert [b["total"] for b in dados["blocos"]] == esperado
    assert [b["numero"] for b in dados["blocos"]] == list(range(1, len(esperado) + 1))
    assert [b["nome"] for b in dados["blocos"]][:2] == ["Bloco 01", "Bloco 02"][: len(esperado)]
    assert all(b["status"] == "PLANEJADO" for b in dados["blocos"])
    assert dados["unidades_sem_bloco"] == 0
    assert dados["modo_blocos"] is True


def test_capacidade_padrao_e_25_e_fica_salva(cliente, auth):
    event_id = _evento([30])
    assert [b["total"] for b in _distribuir(cliente, auth, event_id).json()["blocos"]] == [25, 5]
    assert cliente.get(f"/api/events/{event_id}", headers=auth).json()["capacidade_bloco_padrao"] == 25

    _distribuir(cliente, auth, event_id, 10)
    assert _blocos(cliente, auth, event_id)["capacidade_padrao"] == 10


def test_capacidade_personalizada_107_em_blocos_de_10(cliente, auth):
    event_id = _evento([107])
    totais = [b["total"] for b in _distribuir(cliente, auth, event_id, 10).json()["blocos"]]
    assert totais == [10] * 10 + [7]


def test_unidades_seguem_a_ordem_dos_premios_e_podem_dividir_um_premio(cliente, auth):
    event_id = _evento([3, 2])
    blocos = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    sequencia = [
        (u["premio_nome"], u["numero"])
        for b in blocos
        for u in _detalhe(cliente, auth, event_id, b["id"])["unidades"]
    ]
    assert sequencia == [
        ("Premio 1", 1), ("Premio 1", 2),
        ("Premio 1", 3), ("Premio 2", 1),
        ("Premio 2", 2),
    ]


@pytest.mark.parametrize("capacidade", [0, -5])
def test_capacidade_invalida_e_recusada(cliente, auth, capacidade):
    event_id = _evento([10])
    assert _distribuir(cliente, auth, event_id, capacidade).status_code == 422


def test_sem_unidades_para_distribuir(cliente, auth):
    event_id = _evento([])
    assert _distribuir(cliente, auth, event_id, 25).status_code == 409


def test_redistribuir_nao_toca_bloco_iniciado_nem_unidades_sorteadas(cliente, auth):
    event_id = _evento([60])
    blocos = _distribuir(cliente, auth, event_id, 25).json()["blocos"]
    primeiro = blocos[0]["id"]
    _acao(cliente, auth, event_id, primeiro, "iniciar")
    _sortear_proxima(cliente, auth, event_id, primeiro, "redistribui-0001")
    _sortear_proxima(cliente, auth, event_id, primeiro, "redistribui-0002")
    antes = _detalhe(cliente, auth, event_id, primeiro)["unidades"]

    novos = _distribuir(cliente, auth, event_id, 10).json()["blocos"]

    assert _detalhe(cliente, auth, event_id, primeiro)["unidades"] == antes
    assert [b["numero"] for b in novos] == [1, 2, 3, 4, 5]
    assert [b["total"] for b in novos] == [25, 10, 10, 10, 5]
    assert novos[0]["status"] == "EM_ANDAMENTO"
    with session_scope() as db:
        sorteios = db.scalars(select(Draw).where(Draw.event_id == event_id)).all()
        assert len(sorteios) == 2 and all(s.bloco_id == primeiro for s in sorteios)


# ------------------------------------------------------------------ distribuicao manual
def _quadro(cliente, auth, event_id) -> dict:
    return cliente.get(_url(event_id, "/distribuicao"), headers=auth).json()


def _salvar(cliente, auth, event_id, itens):
    return cliente.put(_url(event_id, "/distribuicao"), json={"blocos": itens}, headers=auth)


def _ids(bloco: dict) -> list[int]:
    return [u["id"] for u in bloco["unidades"]]


def test_mover_unidade_entre_blocos_planejados_e_reordenar(cliente, auth):
    event_id = _evento([6])
    _distribuir(cliente, auth, event_id, 4)
    b1, b2 = _quadro(cliente, auth, event_id)["blocos"]
    u1 = _ids(b1)
    u2 = _ids(b2)

    # Move a ultima do bloco 1 para o inicio do bloco 2 e inverte o bloco 1.
    novo_b1 = list(reversed(u1[:-1]))
    novo_b2 = [u1[-1], *u2]
    resposta = _salvar(
        cliente,
        auth,
        event_id,
        [
            {"bloco_id": b1["bloco"]["id"], "unidades": novo_b1},
            {"bloco_id": b2["bloco"]["id"], "unidades": novo_b2},
        ],
    )
    assert resposta.status_code == 200, resposta.text
    depois = resposta.json()["blocos"]
    assert _ids(depois[0]) == novo_b1
    assert _ids(depois[1]) == novo_b2
    assert [u["ordem_bloco"] for u in depois[0]["unidades"]] == [1, 2, 3]


def test_capacidade_e_respeitada_salvo_alteracao_explicita(cliente, auth):
    event_id = _evento([6])
    _distribuir(cliente, auth, event_id, 3)
    b1, b2 = _quadro(cliente, auth, event_id)["blocos"]
    tudo_no_b1 = _ids(b1) + _ids(b2)

    excedeu = _salvar(
        cliente, auth, event_id,
        [{"bloco_id": b1["bloco"]["id"], "unidades": tudo_no_b1}, {"bloco_id": b2["bloco"]["id"], "unidades": []}],
    )
    assert excedeu.status_code == 409
    assert "capacidade" in excedeu.json()["detail"]

    com_capacidade = _salvar(
        cliente, auth, event_id,
        [
            {"bloco_id": b1["bloco"]["id"], "unidades": tudo_no_b1, "capacidade": 6},
            {"bloco_id": b2["bloco"]["id"], "unidades": []},
        ],
    )
    assert com_capacidade.status_code == 200, com_capacidade.text
    assert com_capacidade.json()["blocos"][0]["bloco"]["capacidade"] == 6


def test_unidade_retirada_de_bloco_planejado_fica_sem_bloco(cliente, auth):
    event_id = _evento([4])
    _distribuir(cliente, auth, event_id, 4)
    (b1,) = _quadro(cliente, auth, event_id)["blocos"]
    ids = _ids(b1)

    resposta = _salvar(cliente, auth, event_id, [{"bloco_id": b1["bloco"]["id"], "unidades": ids[:3]}])
    assert resposta.status_code == 200
    assert [u["id"] for u in resposta.json()["sem_bloco"]] == ids[3:]
    assert _blocos(cliente, auth, event_id)["unidades_sem_bloco"] == 1


def test_unidade_sorteada_nao_muda_de_bloco(cliente, auth):
    event_id = _evento([4])
    _distribuir(cliente, auth, event_id, 2)
    b1, b2 = _quadro(cliente, auth, event_id)["blocos"]
    _acao(cliente, auth, event_id, b1["bloco"]["id"], "iniciar")
    sorteada = _sortear_proxima(cliente, auth, event_id, b1["bloco"]["id"], "nao-move-0001")["unidade_id"]
    _acao(cliente, auth, event_id, b1["bloco"]["id"], "finalizar", {"confirmar_pendentes": True})

    resposta = _salvar(
        cliente, auth, event_id,
        [{"bloco_id": b2["bloco"]["id"], "unidades": [*_ids(b2), sorteada], "capacidade": 3}],
    )
    assert resposta.status_code == 409
    assert "já sorteadas" in resposta.json()["detail"]


def test_bloco_iniciado_fica_congelado(cliente, auth):
    event_id = _evento([4])
    _distribuir(cliente, auth, event_id, 2)
    b1, b2 = _quadro(cliente, auth, event_id)["blocos"]
    _acao(cliente, auth, event_id, b1["bloco"]["id"], "iniciar")

    # Nao recebe...
    recebe = _salvar(
        cliente, auth, event_id,
        [
            {"bloco_id": b1["bloco"]["id"], "unidades": [*_ids(b1), _ids(b2)[0]], "capacidade": 3},
            {"bloco_id": b2["bloco"]["id"], "unidades": _ids(b2)[1:]},
        ],
    )
    assert recebe.status_code == 409
    # ...nao perde...
    perde = _salvar(
        cliente, auth, event_id,
        [
            {"bloco_id": b1["bloco"]["id"], "unidades": _ids(b1)[1:]},
            {"bloco_id": b2["bloco"]["id"], "unidades": [*_ids(b2), _ids(b1)[0]], "capacidade": 3},
        ],
    )
    assert perde.status_code == 409
    # ...nem e reordenado.
    reordena = _salvar(
        cliente, auth, event_id, [{"bloco_id": b1["bloco"]["id"], "unidades": list(reversed(_ids(b1)))}]
    )
    assert reordena.status_code == 409


@pytest.mark.parametrize("problema", ["duplicada", "unidade_alheia", "bloco_alheio"])
def test_distribuicao_invalida_e_recusada(cliente, auth, problema):
    event_id = _evento([4])
    outro = _evento([2])
    _distribuir(cliente, auth, event_id, 4)
    _distribuir(cliente, auth, outro, 2)
    (b1,) = _quadro(cliente, auth, event_id)["blocos"]
    (alheio,) = _quadro(cliente, auth, outro)["blocos"]

    itens = {
        "duplicada": [{"bloco_id": b1["bloco"]["id"], "unidades": [_ids(b1)[0], _ids(b1)[0]]}],
        "unidade_alheia": [{"bloco_id": b1["bloco"]["id"], "unidades": [_ids(alheio)[0]]}],
        "bloco_alheio": [{"bloco_id": alheio["bloco"]["id"], "unidades": []}],
    }[problema]
    assert _salvar(cliente, auth, event_id, itens).status_code == 422


def test_distribuicao_e_atomica(cliente, auth):
    """Uma regra violada impede tudo: nenhuma movimentacao parcial e gravada."""
    event_id = _evento([6])
    _distribuir(cliente, auth, event_id, 2)
    b1, b2, b3 = _quadro(cliente, auth, event_id)["blocos"]
    _acao(cliente, auth, event_id, b3["bloco"]["id"], "iniciar")
    antes = _quadro(cliente, auth, event_id)

    resposta = _salvar(
        cliente, auth, event_id,
        [
            {"bloco_id": b1["bloco"]["id"], "unidades": list(reversed(_ids(b1)))},  # valido
            {"bloco_id": b3["bloco"]["id"], "unidades": []},  # invalido: bloco iniciado
        ],
    )
    assert resposta.status_code == 409
    assert _quadro(cliente, auth, event_id) == antes


# ------------------------------------------------------------------ criar, editar e excluir
def test_criar_editar_e_excluir_bloco(cliente, auth):
    event_id = _evento([4])
    _distribuir(cliente, auth, event_id, 4)

    novo = cliente.post(_url(event_id), json={}, headers=auth)
    assert novo.status_code == 201
    assert novo.json()["numero"] == 2
    assert novo.json()["nome"] == "Bloco 02"
    assert novo.json()["capacidade"] == 4  # herda a capacidade padrao do evento

    editado = cliente.patch(
        _url(event_id, f"/{novo.json()['id']}"), json={"nome": "Bloco final", "capacidade": 10}, headers=auth
    )
    assert editado.status_code == 200
    assert (editado.json()["nome"], editado.json()["capacidade"]) == ("Bloco final", 10)

    assert cliente.delete(_url(event_id, f"/{novo.json()['id']}"), headers=auth).status_code == 204


def test_capacidade_nao_fica_abaixo_das_unidades_do_bloco(cliente, auth):
    event_id = _evento([5])
    (bloco,) = _distribuir(cliente, auth, event_id, 5).json()["blocos"]
    resposta = cliente.patch(_url(event_id, f"/{bloco['id']}"), json={"capacidade": 3}, headers=auth)
    assert resposta.status_code == 409


def test_excluir_bloco_planejado_libera_unidades_e_iniciado_nao_pode(cliente, auth):
    event_id = _evento([4])
    b1, b2 = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    _acao(cliente, auth, event_id, b1["id"], "iniciar")

    assert cliente.delete(_url(event_id, f"/{b1['id']}"), headers=auth).status_code == 409
    assert cliente.delete(_url(event_id, f"/{b2['id']}"), headers=auth).status_code == 204
    assert _blocos(cliente, auth, event_id)["unidades_sem_bloco"] == 2


# ------------------------------------------------------------------ ciclo de vida
def test_iniciar_pausar_retomar_e_finalizar(cliente, auth):
    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    bid = bloco["id"]

    iniciado = _acao(cliente, auth, event_id, bid, "iniciar").json()
    assert iniciado["status"] == "EM_ANDAMENTO" and iniciado["iniciado_em"]
    assert _acao(cliente, auth, event_id, bid, "iniciar").status_code == 200  # duplo clique

    assert _acao(cliente, auth, event_id, bid, "pausar").json()["status"] == "PAUSADO"
    retomado = _acao(cliente, auth, event_id, bid, "iniciar").json()
    assert retomado["status"] == "EM_ANDAMENTO"
    assert retomado["iniciado_em"] == iniciado["iniciado_em"]  # retomar nao reinicia

    for i in range(3):
        _sortear_proxima(cliente, auth, event_id, bid, f"ciclo-{i:04d}")
    final = _acao(cliente, auth, event_id, bid, "finalizar")
    assert final.status_code == 200
    assert final.json()["status"] == "FINALIZADO"
    assert final.json()["finalizado_por"] == "Organizador"
    assert final.json()["percentual"] == 100

    acoes = [
        linha["acao"]
        for linha in cliente.get(f"/api/events/{event_id}/relatorio/auditoria", headers=auth).json()
    ]
    for esperado in ("bloco_iniciado", "bloco_pausado", "bloco_retomado", "bloco_finalizado"):
        assert esperado in acoes


def test_so_um_bloco_em_andamento_por_vez(cliente, auth):
    event_id = _evento([4])
    b1, b2 = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    _acao(cliente, auth, event_id, b1["id"], "iniciar")
    resposta = _acao(cliente, auth, event_id, b2["id"], "iniciar")
    assert resposta.status_code == 409
    assert "já está em andamento" in resposta.json()["detail"]

    _acao(cliente, auth, event_id, b1["id"], "pausar")
    assert _acao(cliente, auth, event_id, b2["id"], "iniciar").status_code == 200


def test_indice_do_banco_impede_dois_blocos_em_andamento():
    event_id = _evento([2])
    with session_scope() as db:
        db.add_all(
            [
                BlocoSorteio(event_id=event_id, numero=1, nome="A", status="EM_ANDAMENTO"),
                BlocoSorteio(event_id=event_id, numero=2, nome="B"),
            ]
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as conexao:
            conexao.execute(text("UPDATE blocos_sorteio SET status = 'EM_ANDAMENTO'"))


def test_finalizar_com_pendencias_exige_confirmacao(cliente, auth):
    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")

    sem = _acao(cliente, auth, event_id, bloco["id"], "finalizar")
    assert sem.status_code == 409
    assert "3 unidade" in sem.json()["detail"]
    com = _acao(cliente, auth, event_id, bloco["id"], "finalizar", {"confirmar_pendentes": True})
    assert com.status_code == 200


@pytest.mark.parametrize("situacao", ["finalizado", "vazio", "planejado_finalizar"])
def test_transicoes_invalidas(cliente, auth, situacao):
    event_id = _evento([2])
    (bloco,) = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    bid = bloco["id"]
    if situacao == "finalizado":
        _acao(cliente, auth, event_id, bid, "iniciar")
        _acao(cliente, auth, event_id, bid, "finalizar", {"confirmar_pendentes": True})
        assert _acao(cliente, auth, event_id, bid, "iniciar").status_code == 409
    elif situacao == "vazio":
        vazio = cliente.post(_url(event_id), json={}, headers=auth).json()
        assert _acao(cliente, auth, event_id, vazio["id"], "iniciar").status_code == 409
    else:
        assert _acao(cliente, auth, event_id, bid, "finalizar").status_code == 409


# ------------------------------------------------------------------ execucao
def test_sorteio_so_no_bloco_em_andamento(cliente, auth):
    event_id = _evento([4])
    b1, b2 = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    _acao(cliente, auth, event_id, b1["id"], "iniciar")

    fora = _sortear(cliente, auth, event_id, _disponiveis(cliente, auth, event_id, b2["id"])[0], "fora-0001")
    assert fora.status_code == 409
    assert "ainda não foi iniciado" in fora.json()["detail"]

    dentro = _sortear(cliente, auth, event_id, _disponiveis(cliente, auth, event_id, b1["id"])[0], "dentro-0001")
    assert dentro.status_code == 200
    assert (dentro.json()["bloco_id"], dentro.json()["bloco_numero"]) == (b1["id"], 1)


def test_bloco_pausado_nao_sorteia(cliente, auth):
    event_id = _evento([2])
    (bloco,) = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    _acao(cliente, auth, event_id, bloco["id"], "pausar")
    unidade = _disponiveis(cliente, auth, event_id, bloco["id"])[0]

    conferencia = cliente.get(
        f"/api/events/{event_id}/sorteio/elegiveis", params={"prize_unit_id": unidade}, headers=auth
    ).json()
    assert conferencia["pode_sortear"] is False
    assert any("pausado" in b for b in conferencia["bloqueios"])
    assert _sortear(cliente, auth, event_id, unidade, "pausado-0001").status_code == 409


def test_unidade_sem_bloco_nao_sorteia_quando_ha_blocos(cliente, auth):
    event_id = _evento([3])
    _distribuir(cliente, auth, event_id, 2)
    (b1, _b2) = _quadro(cliente, auth, event_id)["blocos"]
    solta = _ids(b1)[-1]
    _salvar(cliente, auth, event_id, [{"bloco_id": b1["bloco"]["id"], "unidades": _ids(b1)[:-1]}])
    _acao(cliente, auth, event_id, b1["bloco"]["id"], "iniciar")
    resposta = _sortear(cliente, auth, event_id, solta, "solta-0001")
    assert resposta.status_code == 409
    assert "não foi distribuída" in resposta.json()["detail"]


def test_evento_sem_blocos_continua_no_modo_anterior(cliente, auth):
    event_id = _evento([2])
    assert _blocos(cliente, auth, event_id)["modo_blocos"] is False
    with session_scope() as db:
        unidade = db.scalar(select(PrizeUnit.id).join(Prize).where(Prize.event_id == event_id))
    resposta = _sortear(cliente, auth, event_id, unidade, "legado-0001")
    assert resposta.status_code == 200
    assert resposta.json()["bloco_id"] is None


def test_novo_sorteio_aguarda_a_revelacao_no_telao(cliente, auth):
    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    u1, u2, _u3 = _disponiveis(cliente, auth, event_id, bloco["id"])

    primeiro = _sortear(cliente, auth, event_id, u1, "revela-0001")
    assert primeiro.status_code == 200
    segundo = _sortear(cliente, auth, event_id, u2, "revela-0002")
    assert segundo.status_code == 409
    assert "Aguarde" in segundo.json()["detail"]

    # A mesma requisicao repetida (clique duplo, nova tentativa) segue idempotente.
    repetido = _sortear(cliente, auth, event_id, u1, "revela-0001")
    assert repetido.status_code == 200
    assert repetido.json()["reaproveitado"] is True
    assert repetido.json()["id"] == primeiro.json()["id"]

    _liberar_telao(event_id)
    assert _sortear(cliente, auth, event_id, u2, "revela-0002").status_code == 200


def test_progresso_do_bloco(cliente, auth):
    event_id = _evento([4])
    (bloco,) = _distribuir(cliente, auth, event_id, 4).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    sorteio = _sortear_proxima(cliente, auth, event_id, bloco["id"], "progresso-0001")
    _sortear_proxima(cliente, auth, event_id, bloco["id"], "progresso-0002")
    cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/entrega", json={"entregue": True}, headers=auth
    )

    (atual,) = _blocos(cliente, auth, event_id)["blocos"]
    assert (atual["total"], atual["sorteadas"], atual["restantes"], atual["entregues"]) == (4, 2, 2, 1)
    assert atual["percentual"] == 50


# ------------------------------------------------------------------ concorrencia
def _em_paralelo(funcoes) -> list:
    resultados: list = [None] * len(funcoes)
    barreira = threading.Barrier(len(funcoes))

    def rodar(indice, funcao):
        barreira.wait(timeout=30)
        resultados[indice] = funcao()

    threads = [threading.Thread(target=rodar, args=(i, f)) for i, f in enumerate(funcoes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return resultados


def test_dois_operadores_iniciando_blocos_diferentes_ao_mesmo_tempo(cliente, auth):
    event_id = _evento([4])
    b1, b2 = _distribuir(cliente, auth, event_id, 2).json()["blocos"]

    respostas = _em_paralelo(
        [
            lambda: _acao(cliente, auth, event_id, b1["id"], "iniciar"),
            lambda: _acao(cliente, auth, event_id, b2["id"], "iniciar"),
        ]
    )
    assert Counter(r.status_code for r in respostas) == Counter({200: 1, 409: 1})
    assert sum(b["status"] == "EM_ANDAMENTO" for b in _blocos(cliente, auth, event_id)["blocos"]) == 1


def test_dois_operadores_sorteando_no_mesmo_bloco_ao_mesmo_tempo(cliente, auth):
    """Unidades diferentes, mesmo instante: so um sorteio e aceito por revelacao."""
    event_id = _evento([4])
    (bloco,) = _distribuir(cliente, auth, event_id, 4).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    u1, u2, *_ = _disponiveis(cliente, auth, event_id, bloco["id"])

    respostas = _em_paralelo(
        [
            lambda: _sortear(cliente, auth, event_id, u1, "paralelo-a-0001"),
            lambda: _sortear(cliente, auth, event_id, u2, "paralelo-b-0001"),
        ]
    )
    assert Counter(r.status_code for r in respostas) == Counter({200: 1, 409: 1})
    with session_scope() as db:
        assert len(db.scalars(select(Draw).where(Draw.event_id == event_id)).all()) == 1


def test_pausa_e_sorteio_simultaneos_nunca_deixam_sorteio_em_bloco_pausado(cliente, auth):
    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    unidade = _disponiveis(cliente, auth, event_id, bloco["id"])[0]

    sorteio, pausa = _em_paralelo(
        [
            lambda: _sortear(cliente, auth, event_id, unidade, "corrida-0001"),
            lambda: _acao(cliente, auth, event_id, bloco["id"], "pausar"),
        ]
    )
    assert pausa.status_code == 200
    # As transacoes sao serializadas: ou o sorteio entrou antes da pausa (200),
    # ou foi recusado por encontrar o bloco ja pausado (409). Nunca os dois.
    assert sorteio.status_code in {200, 409}
    with session_scope() as db:
        total = len(db.scalars(select(Draw).where(Draw.event_id == event_id)).all())
    assert total == (1 if sorteio.status_code == 200 else 0)


# ------------------------------------------------------------------ anulacao e remanescentes
def test_anulacao_no_bloco_em_andamento_devolve_a_unidade_ao_mesmo_bloco(cliente, auth):
    event_id = _evento([2])
    (bloco,) = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    primeiro = _sortear_proxima(cliente, auth, event_id, bloco["id"], "anula-0001")
    cliente.post(
        f"/api/events/{event_id}/sorteios/{primeiro['id']}/anular",
        json={"motivo": "Ganhador ausente no palco", "tipo": "ausencia"},
        headers=auth,
    )
    assert _blocos(cliente, auth, event_id)["blocos"][0]["restantes"] == 2

    novo = _sortear(cliente, auth, event_id, primeiro["unidade_id"], "anula-0002")
    assert novo.status_code == 200
    assert novo.json()["bloco_id"] == bloco["id"]
    assert novo.json()["draw_anterior_id"] == primeiro["id"]


def test_anulacao_em_bloco_finalizado_vai_para_remanescentes(cliente, auth):
    event_id = _evento([2, 1])
    b1, b2 = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    _acao(cliente, auth, event_id, b1["id"], "iniciar")
    primeiro = _sortear_proxima(cliente, auth, event_id, b1["id"], "rem-0001")
    _sortear_proxima(cliente, auth, event_id, b1["id"], "rem-0002")
    _acao(cliente, auth, event_id, b1["id"], "finalizar")

    cliente.post(
        f"/api/events/{event_id}/sorteios/{primeiro['id']}/anular",
        json={"motivo": "Desistiu apos o encerramento", "tipo": "desistencia"},
        headers=auth,
    )
    assert _blocos(cliente, auth, event_id)["unidades_remanescentes"] == 1

    rem = cliente.post(_url(event_id, "/remanescentes"), json={}, headers=auth)
    assert rem.status_code == 201
    assert rem.json()["nome"] == "Prêmios remanescentes"
    assert (rem.json()["numero"], rem.json()["total"], rem.json()["capacidade"]) == (3, 1, 1)
    assert _detalhe(cliente, auth, event_id, rem.json()["id"])["unidades"][0]["id"] == primeiro["unidade_id"]

    _acao(cliente, auth, event_id, rem.json()["id"], "iniciar")
    # Fase 7: finalizar o bloco 1 abriu o carrossel; o operador o encerra antes de sortear.
    cliente.post(
        f"/api/events/{event_id}/telao/carrossel", json={"acao": "encerrar"}, headers=auth
    )
    novo = _sortear(cliente, auth, event_id, primeiro["unidade_id"], "rem-0003").json()
    assert novo["bloco_id"] == rem.json()["id"]

    with session_scope() as db:
        assert db.get(Draw, primeiro["id"]).bloco_id == b1["id"]  # historico intacto
    premiados_b1 = cliente.get(_url(event_id, f"/{b1['id']}/premiados"), headers=auth).json()
    assert [p["rodada"] for p in premiados_b1] == [2]  # anulado fica de fora
    # O bloco 2 nao foi tocado.
    assert _detalhe(cliente, auth, event_id, b2["id"])["bloco"]["status"] == "PLANEJADO"


def test_finalizar_com_pendencias_e_criar_remanescentes(cliente, auth):
    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    _sortear_proxima(cliente, auth, event_id, bloco["id"], "pend-0001")
    _acao(cliente, auth, event_id, bloco["id"], "finalizar", {"confirmar_pendentes": True})

    rem = cliente.post(_url(event_id, "/remanescentes"), json={"nome": "Sobras"}, headers=auth).json()
    assert (rem["nome"], rem["total"]) == ("Sobras", 2)
    assert _detalhe(cliente, auth, event_id, bloco["id"])["bloco"]["total"] == 1


def test_sem_remanescentes(cliente, auth):
    event_id = _evento([2])
    _distribuir(cliente, auth, event_id, 2)
    assert cliente.post(_url(event_id, "/remanescentes"), json={}, headers=auth).status_code == 409


# ------------------------------------------------------------------ resultados e telao
def test_premiados_do_bloco_em_ordem_e_sem_dados_pessoais(cliente, auth):
    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    sorteios = [_sortear_proxima(cliente, auth, event_id, bloco["id"], f"prem-{i:04d}") for i in range(3)]

    resposta = cliente.get(_url(event_id, f"/{bloco['id']}/premiados"), headers=auth)
    premiados = resposta.json()
    assert [p["rodada"] for p in premiados] == [s["rodada"] for s in sorteios]
    assert [p["ganhador_nome"] for p in premiados] == [s["ganhador_nome"] for s in sorteios]
    assert "matricula" not in resposta.text and "pulseira" not in resposta.text


def test_reconexao_recupera_bloco_e_resultado_sem_novo_sorteio(cliente, auth):
    event_id = _evento([3])
    (bloco,) = _distribuir(cliente, auth, event_id, 3).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    sorteio = _sortear(
        cliente, auth, event_id, _disponiveis(cliente, auth, event_id, bloco["id"])[0], "reconecta-0001"
    ).json()
    _liberar_telao(event_id)

    with session_scope() as db:
        token = db.get(Event, event_id).telao_token
    for _ in range(4):  # F5 / reconexao do telao e do painel
        estado = cliente.get(f"/api/public/{token}/estado").json()
        assert estado["estado"] == "resultado"
        assert estado["bloco"] == {"numero": 1, "nome": "Bloco 01"}
        assert estado["ganhador"]["nome"] == sorteio["ganhador_nome"]
        painel = _blocos(cliente, auth, event_id)
        assert painel["bloco_ativo_id"] == bloco["id"]
        assert painel["blocos"][0]["sorteadas"] == 1

    with session_scope() as db:
        assert len(db.scalars(select(Draw).where(Draw.event_id == event_id)).all()) == 1


def test_telao_mostra_o_bloco_ao_apresentar_o_premio(cliente, auth):
    event_id = _evento([2])
    (bloco,) = _distribuir(cliente, auth, event_id, 2).json()["blocos"]
    unidade = _disponiveis(cliente, auth, event_id, bloco["id"])[0]
    cliente.post(
        f"/api/events/{event_id}/telao", json={"estado": "premio", "prize_unit_id": unidade}, headers=auth
    )
    with session_scope() as db:
        token = db.get(Event, event_id).telao_token
    bruto = cliente.get(f"/api/public/{token}/estado")
    assert bruto.json()["bloco"]["numero"] == 1
    assert "matricula" not in bruto.text
