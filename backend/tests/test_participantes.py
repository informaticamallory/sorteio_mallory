from __future__ import annotations

import io

from openpyxl import Workbook

from conftest import montar_evento


def _planilha_xlsx(linhas: list[list], formatar_texto: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["nome", "matricula", "setor"])
    for linha in linhas:
        ws.append(linha)
    if formatar_texto:
        for linha in ws.iter_rows(min_col=2, max_col=2):
            for celula in linha:
                celula.number_format = "@"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_importacao_preserva_zeros_a_esquerda(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    conteudo = "nome;matricula;setor\r\nMaria Souza;000123;Financeiro\r\nJoao Lima;000124;Producao\r\n"

    previa = cliente.post(
        f"/api/events/{event_id}/participantes/importar/previa",
        files={"arquivo": ("lista.csv", conteudo.encode("utf-8-sig"), "text/csv")},
        headers=auth,
    )
    assert previa.status_code == 200, previa.text
    dados = previa.json()
    assert dados["total_linhas"] == 2
    assert dados["com_erro"] == 0
    assert [linha["matricula"] for linha in dados["linhas"]] == ["000123", "000124"]

    confirmacao = cliente.post(
        f"/api/events/{event_id}/participantes/importar/confirmar",
        json={
            "linhas": [
                {"nome": linha["nome"], "matricula": linha["matricula"], "setor": linha["setor"]}
                for linha in dados["linhas"]
            ]
        },
        headers=auth,
    )
    assert confirmacao.status_code == 200
    assert confirmacao.json()["criados"] == 2

    lista = cliente.get(f"/api/events/{event_id}/participantes", headers=auth).json()
    assert sorted(p["matricula"] for p in lista) == ["000123", "000124"]


def test_importacao_xlsx_com_matricula_textual(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    conteudo = _planilha_xlsx([["Ana Paula", "000987", "Qualidade"]])

    previa = cliente.post(
        f"/api/events/{event_id}/participantes/importar/previa",
        files={
            "arquivo": (
                "lista.xlsx",
                conteudo,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=auth,
    ).json()
    assert previa["linhas"][0]["matricula"] == "000987"


def test_previa_aponta_erros_e_duplicadas(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    cliente.post(
        f"/api/events/{event_id}/participantes",
        json={"nome": "Ja Existe", "matricula": "00777", "setor": "TI"},
        headers=auth,
    )
    conteudo = (
        "nome;matricula;setor\r\n"
        "Sem Matricula;;TI\r\n"
        ";00555;TI\r\n"
        "Repetido A;00111;TI\r\n"
        "Repetido B;00111;TI\r\n"
        "Conflito;00777;TI\r\n"
    )
    previa = cliente.post(
        f"/api/events/{event_id}/participantes/importar/previa",
        files={"arquivo": ("lista.csv", conteudo.encode("utf-8"), "text/csv")},
        headers=auth,
    ).json()

    assert previa["total_linhas"] == 5
    assert previa["com_erro"] == 3  # sem matricula, sem nome, repetido
    linhas = {linha["linha"]: linha for linha in previa["linhas"]}
    assert "Matricula em branco" in linhas[2]["erros"]
    assert "Nome em branco" in linhas[3]["erros"]
    assert linhas[5]["duplicada_na_planilha"] is True
    assert linhas[6]["ja_existe_no_evento"] is True


def test_matricula_duplicada_no_cadastro_manual(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    corpo = {"nome": "Primeiro", "matricula": "00042", "setor": "TI"}
    assert cliente.post(
        f"/api/events/{event_id}/participantes", json=corpo, headers=auth
    ).status_code == 201
    repetido = cliente.post(
        f"/api/events/{event_id}/participantes",
        json={**corpo, "nome": "Segundo"},
        headers=auth,
    )
    assert repetido.status_code == 409


def test_importacao_sem_coluna_obrigatoria(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    resposta = cliente.post(
        f"/api/events/{event_id}/participantes/importar/previa",
        files={"arquivo": ("lista.csv", b"apelido;area\r\nFulano;TI\r\n", "text/csv")},
        headers=auth,
    )
    assert resposta.status_code == 422
    assert "matricula" in resposta.json()["detail"]


def test_filtros_de_busca(cliente, auth):
    event_id, ids, _ = montar_evento(participantes=6, presentes=3)
    cliente.post(
        f"/api/events/{event_id}/participantes/{ids[5]}/participacao",
        json={"participando": False, "motivo": "Afastado no periodo do evento"},
        headers=auth,
    )

    presentes = cliente.get(
        f"/api/events/{event_id}/participantes",
        params={"presenca": "presentes"},
        headers=auth,
    ).json()
    assert len(presentes) == 3

    excluidos = cliente.get(
        f"/api/events/{event_id}/participantes",
        params={"participacao": "excluidos"},
        headers=auth,
    ).json()
    assert len(excluidos) == 1
    assert excluidos[0]["motivo_participacao"] == "Afastado no periodo do evento"

    por_matricula = cliente.get(
        f"/api/events/{event_id}/participantes", params={"busca": "00003"}, headers=auth
    ).json()
    assert len(por_matricula) == 1


def test_modelo_de_planilha_disponivel(cliente, auth):
    csv = cliente.get("/api/participantes/modelo.csv", headers=auth)
    assert csv.status_code == 200
    assert b"matricula" in csv.content

    xlsx = cliente.get("/api/participantes/modelo.xlsx", headers=auth)
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"


def test_participante_com_resultado_nao_pode_ser_apagado(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=1)
    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "protege-0001"},
        headers=auth,
    )
    resposta = cliente.delete(
        f"/api/events/{event_id}/participantes/{ids[0]}", headers=auth
    )
    assert resposta.status_code == 409


# ---------------------------------------------------------------- pulseira
def _criar(cliente, auth, event_id, matricula, pulseira):
    return cliente.post(
        f"/api/events/{event_id}/participantes",
        json={"nome": f"Pessoa {matricula}", "matricula": matricula, "pulseira": pulseira},
        headers=auth,
    )


def test_pulseira_normalizada_e_com_zeros_preservados(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    resposta = _criar(cliente, auth, event_id, "00010", "  a-0042 ")
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["pulseira"] == "A-0042"

    vazia = _criar(cliente, auth, event_id, "00011", "   ")
    assert vazia.json()["pulseira"] is None


def test_pulseira_duplicada_e_recusada_com_mensagem_clara(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    assert _criar(cliente, auth, event_id, "00020", "0100").status_code == 201

    repetida = _criar(cliente, auth, event_id, "00021", "0100")
    assert repetida.status_code == 409
    assert "pulseira" in repetida.json()["detail"].lower()

    # Mesma pulseira, so que digitada em minusculas: continua sendo a mesma.
    outra_grafia = _criar(cliente, auth, event_id, "00022", "a1")
    assert outra_grafia.status_code == 201
    assert _criar(cliente, auth, event_id, "00023", "A1").status_code == 409


def test_trocar_pulseira_para_uma_ocupada_e_recusado(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    _criar(cliente, auth, event_id, "00030", "500")
    segundo = _criar(cliente, auth, event_id, "00031", "501").json()

    resposta = cliente.patch(
        f"/api/events/{event_id}/participantes/{segundo['id']}",
        json={"pulseira": "500"},
        headers=auth,
    )
    assert resposta.status_code == 409


def test_troca_e_remocao_de_pulseira_ficam_na_auditoria(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    participante = _criar(cliente, auth, event_id, "00040", "700").json()
    url = f"/api/events/{event_id}/participantes/{participante['id']}"

    trocada = cliente.patch(url, json={"pulseira": "701"}, headers=auth)
    assert trocada.json()["pulseira"] == "701"
    removida = cliente.patch(url, json={"pulseira": None}, headers=auth)
    assert removida.json()["pulseira"] is None
    # Editar outro campo nao mexe na pulseira nem gera registro de troca.
    cliente.patch(url, json={"setor": "RH"}, headers=auth)

    trocas = [
        linha["detalhes"]
        for linha in cliente.get(f"/api/events/{event_id}/relatorio/auditoria", headers=auth).json()
        if linha["acao"] == "pulseira_alterada"
    ]
    assert trocas == [
        {"participante_id": participante["id"], "anterior": "701", "nova": None},
        {"participante_id": participante["id"], "anterior": "700", "nova": "701"},
    ]


def test_pulseira_com_caracteres_invalidos_e_rejeitada(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    resposta = _criar(cliente, auth, event_id, "00050", "12 34; DROP")
    assert resposta.status_code == 422
