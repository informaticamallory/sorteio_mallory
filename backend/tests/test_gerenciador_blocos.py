"""Gerenciador de Blocos: previas, descricao, exclusao segura, reordenacao,
remanescentes com capacidade e edicao simultanea."""

from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, BlocoSorteio, Draw, PrizeUnit
from test_blocos import _acao, _blocos, _distribuir, _evento, _liberar_telao, _sortear, _url


def _criar(cliente, auth, event_id, **corpo):
    return cliente.post(_url(event_id), json=corpo, headers=auth)


def _distribuicao(cliente, auth, event_id) -> dict:
    return cliente.get(_url(event_id, "/distribuicao"), headers=auth).json()


# ------------------------------------------------------------------ criacao e edicao
def test_criar_bloco_vazio_com_nome_descricao_e_capacidade(cliente, auth):
    event_id = _evento([3])
    criado = _criar(cliente, auth, event_id, nome="Bloco 03 — Prêmios Especiais", capacidade=10, descricao=" Só eletrônicos ")
    assert criado.status_code == 201, criado.text
    corpo = criado.json()
    assert corpo["nome"] == "Bloco 03 — Prêmios Especiais" and corpo["descricao"] == "Só eletrônicos"
    assert corpo["capacidade"] == 10 and corpo["status"] == "PLANEJADO" and corpo["total"] == 0
    # Nome repetido (sem diferenca de maiusculas) e recusado.
    assert _criar(cliente, auth, event_id, nome="bloco 03 — prêmios especiais").status_code == 409
    # Bloco vazio nao pode ser iniciado.
    assert _acao(cliente, auth, event_id, corpo["id"], "iniciar").status_code == 409


def test_editar_nome_descricao_e_capacidade_minima(cliente, auth):
    event_id = _evento([5])
    _distribuir(cliente, auth, event_id, 5)
    bloco = _blocos(cliente, auth, event_id)["blocos"][0]
    url = _url(event_id, f"/{bloco['id']}")
    ok = cliente.patch(url, json={"nome": "Abertura", "descricao": "Primeiro bloco"}, headers=auth)
    assert ok.status_code == 200 and ok.json()["nome"] == "Abertura" and ok.json()["descricao"] == "Primeiro bloco"
    assert cliente.patch(url, json={"descricao": ""}, headers=auth).json()["descricao"] is None
    # Capacidade abaixo das unidades ja atribuidas.
    assert cliente.patch(url, json={"capacidade": 4}, headers=auth).status_code == 409


# ------------------------------------------------------------------ previa da distribuicao
def test_previa_nao_grava_e_bate_com_a_distribuicao(cliente, auth):
    event_id = _evento([40, 40, 27])  # 107 unidades
    previa = cliente.post(_url(event_id, "/distribuir/previa"), json={"capacidade": 25}, headers=auth)
    assert previa.status_code == 200, previa.text
    corpo = previa.json()
    assert corpo["unidades"] == 107
    assert [b["unidades"] for b in corpo["blocos"]] == [25, 25, 25, 25, 7]
    assert corpo["planejados_refeitos"] == []
    assert _blocos(cliente, auth, event_id)["blocos"] == []  # nada gravado

    _distribuir(cliente, auth, event_id, 25)
    reais = _blocos(cliente, auth, event_id)["blocos"]
    assert [(b["numero"], b["nome"], b["total"]) for b in reais] == [
        (b["numero"], b["nome"], b["unidades"]) for b in corpo["blocos"]
    ]
    # Refazer avisa quais blocos planejados serao recriados.
    de_novo = cliente.post(_url(event_id, "/distribuir/previa"), json={"capacidade": 50}, headers=auth).json()
    assert len(de_novo["planejados_refeitos"]) == 5 and [b["unidades"] for b in de_novo["blocos"]] == [50, 50, 7]


# ------------------------------------------------------------------ exclusao segura
def test_excluir_bloco_planejado_devolve_premios_sem_apagar_nada(cliente, auth):
    event_id = _evento([6])
    _distribuir(cliente, auth, event_id, 4)
    b1, b2 = _blocos(cliente, auth, event_id)["blocos"]
    vazio = _criar(cliente, auth, event_id, nome="Vazio").json()

    assert cliente.delete(_url(event_id, f"/{vazio['id']}"), headers=auth).status_code == 204
    assert cliente.delete(_url(event_id, f"/{b2['id']}"), headers=auth).status_code == 204
    resumo = _blocos(cliente, auth, event_id)
    assert resumo["unidades_total"] == 6 and resumo["unidades_sem_bloco"] == 2  # premios preservados
    with session_scope() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.acao == "bloco_removido").order_by(AuditLog.id.desc())).detalhes[
            "unidades_liberadas"
        ] == 2
    assert b1["id"]


def test_admin_exclui_bloco_em_qualquer_situacao_sem_perder_sorteios(cliente, auth):
    # Regra atual: o admin exclui bloco iniciado, pausado ou finalizado. Sem
    # sorteios o bloco e apagado; com sorteios ele so sai da gestao de blocos.
    event_id = _evento([4])
    _distribuir(cliente, auth, event_id, 2)
    b1, b2 = _blocos(cliente, auth, event_id)["blocos"]
    _acao(cliente, auth, event_id, b1["id"], "iniciar")
    _acao(cliente, auth, event_id, b1["id"], "pausar")
    assert cliente.delete(_url(event_id, f"/{b1['id']}"), headers=auth).status_code == 204  # pausado
    with session_scope() as db:
        assert db.get(BlocoSorteio, b1["id"]) is None  # sem sorteio: apagado

    _acao(cliente, auth, event_id, b2["id"], "iniciar")
    with session_scope() as db:
        unidade = db.scalar(select(PrizeUnit).where(PrizeUnit.bloco_id == b2["id"]))
        unidade_id = unidade.id
    assert _sortear(cliente, auth, event_id, unidade_id, "excluir-com-sorteio").status_code == 200
    _liberar_telao(event_id)
    assert cliente.delete(_url(event_id, f"/{b2['id']}"), headers=auth).status_code == 204  # em andamento
    with session_scope() as db:
        bloco = db.get(BlocoSorteio, b2["id"])
        assert bloco is not None and bloco.excluido_em is not None  # com sorteio: preservado
        assert db.scalar(select(Draw).where(Draw.bloco_id == b2["id"])) is not None
    assert _blocos(cliente, auth, event_id)["blocos"] == []


# ------------------------------------------------------------------ reordenacao
def test_reordenar_so_planejados_sem_mexer_nos_iniciados_nem_nos_numeros(cliente, auth):
    event_id = _evento([8])
    _distribuir(cliente, auth, event_id, 2)  # 4 blocos
    b1, b2, b3, b4 = _blocos(cliente, auth, event_id)["blocos"]
    _acao(cliente, auth, event_id, b1["id"], "iniciar")  # b1 fica onde esta

    nova = [b4["id"], b2["id"], b3["id"]]
    resposta = cliente.post(_url(event_id, "/reordenar"), json={"blocos": nova}, headers=auth)
    assert resposta.status_code == 200, resposta.text
    ordem = [(b["numero"], b["status"]) for b in resposta.json()["blocos"]]
    assert ordem == [(1, "EM_ANDAMENTO"), (4, "PLANEJADO"), (2, "PLANEJADO"), (3, "PLANEJADO")]

    # Lista incompleta, com bloco iniciado ou repetida: recusada.
    for invalida in ([b4["id"], b2["id"]], [b1["id"], b2["id"], b3["id"], b4["id"]], [b2["id"], b2["id"], b3["id"]]):
        assert cliente.post(_url(event_id, "/reordenar"), json={"blocos": invalida}, headers=auth).status_code == 409


# ------------------------------------------------------------------ remanescentes
def test_remanescentes_respeitam_a_capacidade_e_tem_previa(cliente, auth):
    event_id = _evento([30])
    cliente.patch(f"/api/events/{event_id}", json={}, headers=auth)
    previa = cliente.post(_url(event_id, "/remanescentes/previa"), json={"capacidade": 25}, headers=auth).json()
    assert previa["unidades"] == 30 and [b["unidades"] for b in previa["blocos"]] == [25, 5]
    assert [b["nome"] for b in previa["blocos"]] == ["Prêmios remanescentes 1", "Prêmios remanescentes 2"]
    assert _blocos(cliente, auth, event_id)["blocos"] == []

    criado = cliente.post(_url(event_id, "/remanescentes"), json={"capacidade": 25}, headers=auth)
    assert criado.status_code == 201
    blocos = _blocos(cliente, auth, event_id)["blocos"]
    assert [(b["nome"], b["total"], b["capacidade"]) for b in blocos] == [
        ("Prêmios remanescentes 1", 25, 25), ("Prêmios remanescentes 2", 5, 5),
    ]
    # Nada duplicado: cada unidade em um bloco so.
    with session_scope() as db:
        assert db.scalar(select(PrizeUnit).where(PrizeUnit.bloco_id.is_(None))) is None


# ------------------------------------------------------------------ edicao simultanea
def test_organizacao_salva_em_cima_de_versao_antiga_e_recusada(cliente, auth):
    event_id = _evento([4])
    _distribuir(cliente, auth, event_id, 2)
    leitura = _distribuicao(cliente, auth, event_id)
    b1, b2 = leitura["blocos"]
    mover = {
        "versao": leitura["versao"],
        "blocos": [
            {"bloco_id": b1["bloco"]["id"], "unidades": [u["id"] for u in b1["unidades"]][:1]},
            {"bloco_id": b2["bloco"]["id"], "unidades": [u["id"] for u in b2["unidades"]] + [b1["unidades"][1]["id"]], "capacidade": 3},
        ],
    }
    # Outro administrador cria um bloco depois da leitura.
    _criar(cliente, auth, event_id, nome="Outro admin")
    recusada = cliente.put(_url(event_id, "/distribuicao"), json=mover, headers=auth)
    assert recusada.status_code == 409 and "Outro usuário" in recusada.json()["detail"]
    # Relendo, salva.
    mover["versao"] = _distribuicao(cliente, auth, event_id)["versao"]
    assert cliente.put(_url(event_id, "/distribuicao"), json=mover, headers=auth).status_code == 200
    totais = {b["nome"]: b["total"] for b in _blocos(cliente, auth, event_id)["blocos"]}
    assert totais["Bloco 01"] == 1 and totais["Bloco 02"] == 3
