"""Importacao de premios por planilha (CSV/XLSX), com previa e sem duplicar."""
from __future__ import annotations

import io

from openpyxl import Workbook

from test_blocos import _evento


def _previa(cliente, auth, event_id, conteudo: bytes, nome: str):
    return cliente.post(
        f"/api/events/{event_id}/premios/importar/previa",
        files={"arquivo": (nome, conteudo, "application/octet-stream")},
        headers=auth,
    )


def test_previa_e_importacao_csv(cliente, auth):
    event_id = _evento([])
    csv = (
        "﻿Prêmio;Descrição;Qtd\r\n"
        "Air Fryer 5L;Marca X;10\r\n"
        "Bicicleta;;\r\n"
        "TV 50;;0\r\n"
        "air fryer 5l;;2\r\n"
        ";sem nome;1\r\n"
    ).encode("utf-8")
    previa = _previa(cliente, auth, event_id, csv, "premios.csv")
    assert previa.status_code == 200, previa.text
    linhas = {l["linha"]: l for l in previa.json()["linhas"]}
    assert linhas[2]["nome"] == "Air Fryer 5L" and linhas[2]["quantidade"] == 10 and not linhas[2]["erros"]
    assert linhas[3]["quantidade"] == 1 and not linhas[3]["erros"]  # quantidade em branco vale 1
    assert linhas[4]["erros"]  # quantidade 0
    assert any("Repetido" in e for e in linhas[5]["erros"])
    assert linhas[6]["erros"] == ["Sem nome"]
    assert cliente.get(f"/api/events/{event_id}/premios", headers=auth).json() == []  # nada gravado

    validas = [
        {"nome": l["nome"], "descricao": l["descricao"], "quantidade": l["quantidade"]}
        for l in linhas.values()
        if not l["erros"]
    ]
    feito = cliente.post(
        f"/api/events/{event_id}/premios/importar/confirmar", json={"linhas": validas}, headers=auth
    )
    assert feito.status_code == 200
    assert feito.json() == {"criados": 2, "ignorados": 0, "atualizados": 0, "nao_atualizados": []}
    premios = cliente.get(f"/api/events/{event_id}/premios", headers=auth).json()
    assert [(p["nome"], p["quantidade"], len(p["unidades"])) for p in premios] == [
        ("Air Fryer 5L", 10, 10),
        ("Bicicleta", 1, 1),
    ]

    # Importar de novo nao duplica: quem ja existe aparece marcado e fica de fora.
    de_novo = _previa(cliente, auth, event_id, csv, "premios.csv").json()["linhas"]
    assert de_novo[0]["ja_existe"] is True
    repetido = cliente.post(
        f"/api/events/{event_id}/premios/importar/confirmar", json={"linhas": validas}, headers=auth
    )
    assert repetido.json() == {"criados": 0, "ignorados": 2, "atualizados": 0, "nao_atualizados": []}


def test_cabecalho_de_quantidade_variado_e_aviso_quando_nao_lida(cliente, auth):
    event_id = _evento([])
    for cabecalho in ("Quantidade de prêmios", "QTD. TOTAL", "Unid.", "Qtde"):
        previa = _previa(cliente, auth, event_id, f"nome;{cabecalho}\r\nTV;4\r\n".encode(), "p.csv").json()
        assert previa["linhas"][0]["quantidade"] == 4, cabecalho
        assert previa["avisos"] == []
    sem_coluna = _previa(cliente, auth, event_id, b"nome;valor\r\nTV;1500\r\n", "p.csv").json()
    assert sem_coluna["linhas"][0]["quantidade"] == 1
    assert "Não encontrei a coluna de quantidade" in sem_coluna["avisos"][0]
    # Formula sem valor salvo chega vazia: avisa em vez de virar 1 em silencio.
    vazia = _previa(cliente, auth, event_id, b"nome;quantidade\r\nTV;\r\nFone;\r\n", "p.csv").json()
    assert "vazia em todas as linhas" in vazia["avisos"][0]


def test_reimportar_atualiza_quantidade_dos_que_ja_existem(cliente, auth):
    event_id = _evento([])
    url = f"/api/events/{event_id}/premios/importar/confirmar"
    cliente.post(url, json={"linhas": [{"nome": "TV", "quantidade": 1}, {"nome": "Fone", "quantidade": 5}]}, headers=auth)
    previa = _previa(cliente, auth, event_id, b"nome;quantidade\r\ntv;3\r\nFone;2\r\n", "p.csv").json()
    assert [(l["ja_existe"], l["quantidade_atual"]) for l in previa["linhas"]] == [(True, 1), (True, 5)]

    linhas = [{"nome": "tv", "quantidade": 3}, {"nome": "Fone", "quantidade": 2}]
    sem_marcar = cliente.post(url, json={"linhas": linhas}, headers=auth).json()
    assert sem_marcar["atualizados"] == 0 and sem_marcar["ignorados"] == 2

    feito = cliente.post(url, json={"linhas": linhas, "atualizar_existentes": True}, headers=auth).json()
    assert feito == {"criados": 0, "ignorados": 0, "atualizados": 2, "nao_atualizados": []}
    premios = {p["nome"]: p for p in cliente.get(f"/api/events/{event_id}/premios", headers=auth).json()}
    assert premios["TV"]["quantidade"] == 3 and len(premios["TV"]["unidades"]) == 3
    assert premios["Fone"]["quantidade"] == 2 and len(premios["Fone"]["unidades"]) == 2


def test_importacao_xlsx_e_coluna_obrigatoria(cliente, auth):
    event_id = _evento([])
    wb = Workbook()
    wb.active.append(["nome", "quantidade"])
    wb.active.append(["Fone Bluetooth", 3])
    buffer = io.BytesIO()
    wb.save(buffer)
    previa = _previa(cliente, auth, event_id, buffer.getvalue(), "premios.xlsx")
    assert previa.status_code == 200, previa.text
    assert previa.json()["linhas"][0]["quantidade"] == 3

    sem_nome = _previa(cliente, auth, event_id, b"produto_x;qtd\r\nA;1\r\n", "x.csv")
    assert sem_nome.status_code == 422 and "nome" in sem_nome.json()["detail"]


def test_modelos_baixam(cliente, auth):
    assert cliente.get("/api/premios/modelo.csv", headers=auth).content.decode("utf-8-sig").startswith("nome;descricao")
    assert cliente.get("/api/premios/modelo.xlsx", headers=auth).status_code == 200
