from __future__ import annotations

import time

from app.database import session_scope
from app.models import Event
from conftest import montar_evento


def _token_telao(event_id: int) -> str:
    with session_scope() as db:
        return db.get(Event, event_id).telao_token


def test_estado_inicial_e_aguardando(cliente):
    event_id, _, _ = montar_evento()
    estado = cliente.get(f"/api/public/{_token_telao(event_id)}/estado").json()
    assert estado["estado"] == "aguardando"
    assert estado["ganhador"] is None
    assert estado["evento"]["nome"] == "Evento de Teste"


def test_reconexao_recupera_resultado_sem_novo_sorteio(cliente, auth):
    """F5 no telao depois da animacao deve mostrar o mesmo ganhador."""
    event_id, _, unidades = montar_evento(participantes=10)
    token = _token_telao(event_id)

    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "telao-0001"},
        headers=auth,
    ).json()

    durante = cliente.get(f"/api/public/{token}/estado").json()
    assert durante["estado"] == "sorteando"
    assert durante["ganhador"] is None  # nada de vencedor antes da revelacao
    assert len(durante["nomes_animacao"]) > 0

    # duracao_animacao_ms do fixture = 1000
    time.sleep(1.2)

    primeira_leitura = cliente.get(f"/api/public/{token}/estado").json()
    assert primeira_leitura["estado"] == "resultado"
    assert primeira_leitura["ganhador"]["nome"] == sorteio["ganhador_nome"]

    # Varias releituras (equivalente a F5 / reconexao) nao mudam nada.
    for _ in range(5):
        releitura = cliente.get(f"/api/public/{token}/estado").json()
        assert releitura["estado"] == "resultado"
        assert releitura["ganhador"]["nome"] == sorteio["ganhador_nome"]

    historico = cliente.get(f"/api/events/{event_id}/historico", headers=auth).json()
    assert len(historico) == 1


def test_telao_nunca_recebe_matricula_nem_lista_completa(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=10)
    token = _token_telao(event_id)

    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "privacidade-01"},
        headers=auth,
    )
    time.sleep(1.2)
    estado = cliente.get(f"/api/public/{token}/estado").json()

    bruto = cliente.get(f"/api/public/{token}/estado").text
    assert "matricula" not in bruto
    assert "00001" not in bruto
    # O numero do sorteio e aleatorio e publico por decisao do evento (nao e dado pessoal).
    assert set(estado["ganhador"].keys()) == {"nome", "setor", "foto_url", "numero_sorteio"}


def test_tema_mallory_claro_gira_numeros_sem_enviar_nomes(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=10)
    token = _token_telao(event_id)
    assert cliente.get(f"/api/public/{token}/estado").json()["evento"]["tema_telao"] == "classico"

    assert cliente.patch(f"/api/events/{event_id}", json={"tema_telao": "neon"}, headers=auth).status_code == 422
    resposta = cliente.patch(f"/api/events/{event_id}", json={"tema_telao": "mallory_claro"}, headers=auth)
    assert resposta.status_code == 200 and resposta.json()["tema_telao"] == "mallory_claro"
    # null nao apaga o tema (a coluna e obrigatoria).
    assert cliente.patch(f"/api/events/{event_id}", json={"tema_telao": None}, headers=auth).json()["tema_telao"] == "mallory_claro"

    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "tema-claro-01"},
        headers=auth,
    ).json()
    durante = cliente.get(f"/api/public/{token}/estado").json()
    assert durante["estado"] == "sorteando" and durante["evento"]["tema_telao"] == "mallory_claro"
    # So a quantidade de rolos: nenhum nome de elegivel e nenhum digito do ganhador.
    assert durante["nomes_animacao"] == []
    assert durante["digitos_animacao"] == 4
    assert durante["ganhador"] is None

    time.sleep(1.2)
    depois = cliente.get(f"/api/public/{token}/estado").json()
    assert depois["estado"] == "resultado"
    assert depois["ganhador"]["nome"] == sorteio["ganhador_nome"]
    assert depois["digitos_animacao"] is None


def test_animacao_nao_mostra_inelegiveis(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=6, presentes=2)
    token = _token_telao(event_id)

    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "animacao-0001"},
        headers=auth,
    )
    estado = cliente.get(f"/api/public/{token}/estado").json()
    nomes = set(estado["nomes_animacao"])
    assert nomes <= {"Participante 1", "Participante 2"}
    assert "Participante 3" not in nomes


def test_telao_sem_autenticacao_nao_acessa_rotas_administrativas(cliente):
    event_id, _, unidades = montar_evento()
    assert cliente.get(f"/api/events/{event_id}/participantes").status_code == 401
    assert cliente.get(f"/api/events/{event_id}/historico").status_code == 401
    assert (
        cliente.post(
            f"/api/events/{event_id}/sorteio",
            json={"prize_unit_id": unidades[0], "idempotency_key": "sem-auth-0001"},
        ).status_code
        == 401
    )
    assert cliente.get(f"/api/events/{event_id}/relatorio/export.csv").status_code == 401


def test_token_invalido_nao_expoe_telao(cliente):
    montar_evento()
    assert cliente.get("/api/public/token-que-nao-existe/estado").status_code == 404


def test_comando_sorteando_e_recusado_no_endpoint_de_telao(cliente, auth):
    """O estado 'sorteando' so pode nascer de um sorteio real do backend."""
    event_id, _, unidades = montar_evento()
    resposta = cliente.post(
        f"/api/events/{event_id}/telao",
        json={"estado": "sorteando", "prize_unit_id": unidades[0]},
        headers=auth,
    )
    assert resposta.status_code == 400


def test_versao_do_estado_avanca_a_cada_mudanca(cliente, auth):
    event_id, _, unidades = montar_evento()
    token = _token_telao(event_id)
    v0 = cliente.get(f"/api/public/{token}/estado").json()["versao"]

    cliente.post(
        f"/api/events/{event_id}/telao",
        json={"estado": "premio", "prize_unit_id": unidades[0]},
        headers=auth,
    )
    v1 = cliente.get(f"/api/public/{token}/estado").json()["versao"]
    assert v1 > v0
