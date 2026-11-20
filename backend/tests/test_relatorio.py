from __future__ import annotations

import io

from openpyxl import load_workbook

from conftest import montar_evento


def test_relatorio_filtra_entregues_e_pendentes(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=6, quantidade_premio=2)
    primeiro = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "rel-0001"},
        headers=auth,
    ).json()
    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[1], "idempotency_key": "rel-0002"},
        headers=auth,
    )
    cliente.post(
        f"/api/events/{event_id}/sorteios/{primeiro['id']}/entrega",
        json={"entregue": True},
        headers=auth,
    )

    entregues = cliente.get(
        f"/api/events/{event_id}/relatorio", params={"filtro": "entregues"}, headers=auth
    ).json()
    pendentes = cliente.get(
        f"/api/events/{event_id}/relatorio", params={"filtro": "pendentes"}, headers=auth
    ).json()
    assert len(entregues) == 1
    assert len(pendentes) == 1
    assert entregues[0]["entregue_por"] == "Organizador"
    assert entregues[0]["entregue_em"] is not None


def test_exportacao_csv_e_xlsx(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=4)
    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "export-0001"},
        headers=auth,
    )

    csv = cliente.get(f"/api/events/{event_id}/relatorio/export.csv", headers=auth)
    assert csv.status_code == 200
    assert "attachment" in csv.headers["content-disposition"]
    texto = csv.content.decode("utf-8-sig")
    assert "ganhador" in texto.splitlines()[0]
    assert len(texto.strip().splitlines()) == 2

    xlsx = cliente.get(f"/api/events/{event_id}/relatorio/export.xlsx", headers=auth)
    assert xlsx.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert wb["resultados"].max_row == 2
    assert "evento" in wb.sheetnames


def test_resumo_do_evento(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=10, presentes=7, quantidade_premio=3)
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "resumo-0001"},
        headers=auth,
    ).json()
    cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/entrega",
        json={"entregue": True},
        headers=auth,
    )

    resumo = cliente.get(f"/api/events/{event_id}/resumo", headers=auth).json()
    assert resumo["participantes_total"] == 10
    assert resumo["participantes_presentes"] == 7
    assert resumo["participantes_elegiveis"] == 6  # o ganhador saiu da lista
    assert resumo["unidades_total"] == 3
    assert resumo["unidades_disponiveis"] == 2
    assert resumo["unidades_entregues"] == 1


def test_alteracao_de_regras_fica_no_historico(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=4)
    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "regras-0001"},
        headers=auth,
    )
    resposta = cliente.patch(
        f"/api/events/{event_id}/regras",
        json={"permite_multiplas_vitorias": True},
        headers=auth,
    )
    assert resposta.status_code == 200

    historico = cliente.get(f"/api/events/{event_id}/regras/historico", headers=auth).json()
    assert len(historico) == 1
    assert historico[0]["campo"] == "permite_multiplas_vitorias"
    assert historico[0]["apos_primeiro_sorteio"] is True
    assert historico[0]["usuario_nome"] == "Organizador"


def test_auditoria_registra_sorteio_e_anulacao(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=4)
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "audit-0001"},
        headers=auth,
    ).json()
    cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/anular",
        json={"motivo": "Participante desistiu do premio", "tipo": "desistencia"},
        headers=auth,
    )
    acoes = {
        linha["acao"]
        for linha in cliente.get(
            f"/api/events/{event_id}/relatorio/auditoria", headers=auth
        ).json()
    }
    assert {"sorteio_realizado", "sorteio_anulado"} <= acoes
