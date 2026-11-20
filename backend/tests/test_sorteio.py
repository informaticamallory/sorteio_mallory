"""Cenarios criticos do sorteio ao vivo."""

from __future__ import annotations

import threading
from collections import Counter

import pytest
from sqlalchemy import select

from app.database import SessionLocal, session_scope
from app.models import Draw, Event, StatusSorteio, User
from app.services.sorteio import RegraDeNegocio, escolher_indice, realizar_sorteio
from conftest import montar_evento


# ---------------------------------------------------------------- idempotencia
def test_clique_duplicado_nao_cria_dois_resultados(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=10)
    corpo = {"prize_unit_id": unidades[0], "idempotency_key": "clique-duplo-0001"}

    primeira = cliente.post(f"/api/events/{event_id}/sorteio", json=corpo, headers=auth)
    segunda = cliente.post(f"/api/events/{event_id}/sorteio", json=corpo, headers=auth)

    assert primeira.status_code == 200, primeira.text
    assert segunda.status_code == 200, segunda.text
    assert primeira.json()["id"] == segunda.json()["id"]
    assert primeira.json()["ganhador_id"] == segunda.json()["ganhador_id"]
    assert primeira.json()["reaproveitado"] is False
    assert segunda.json()["reaproveitado"] is True

    historico = cliente.get(f"/api/events/{event_id}/historico", headers=auth).json()
    assert len(historico) == 1


def test_chaves_diferentes_na_mesma_unidade_sao_bloqueadas(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=10)
    base = {"prize_unit_id": unidades[0]}

    primeira = cliente.post(
        f"/api/events/{event_id}/sorteio", json={**base, "idempotency_key": "chave-aaaa-1"},
        headers=auth,
    )
    segunda = cliente.post(
        f"/api/events/{event_id}/sorteio", json={**base, "idempotency_key": "chave-bbbb-2"},
        headers=auth,
    )

    assert primeira.status_code == 200
    assert segunda.status_code == 409
    assert "já foi sorteada" in segunda.json()["detail"]


# ---------------------------------------------------------------- concorrencia
def test_sorteios_concorrentes_na_mesma_unidade(cliente, auth):
    """Duas requisicoes simultaneas na mesma unidade: apenas uma pode vencer."""
    event_id, _, unidades = montar_evento(participantes=30)
    resultados: list[tuple[int, dict]] = []
    barreira = threading.Barrier(2)

    def disparar(indice: int) -> None:
        barreira.wait()
        resposta = cliente.post(
            f"/api/events/{event_id}/sorteio",
            json={
                "prize_unit_id": unidades[0],
                "idempotency_key": f"concorrente-{indice:04d}",
            },
            headers=auth,
        )
        resultados.append((resposta.status_code, resposta.json()))

    threads = [threading.Thread(target=disparar, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    codigos = Counter(codigo for codigo, _ in resultados)
    assert codigos[200] == 1, resultados
    assert codigos[409] == 1, resultados

    with session_scope() as db:
        validos = db.query(Draw).filter(
            Draw.prize_unit_id == unidades[0], Draw.status == StatusSorteio.VALIDO.value
        ).count()
    assert validos == 1


def test_transacao_imediata_serializa_sorteios_no_banco():
    """4 threads com conexoes proprias disputando a mesma unidade.

    Exercita diretamente o BEGIN IMMEDIATE do SQLite, sem passar pela camada
    HTTP: so uma transacao pode confirmar o resultado.
    """
    event_id, _, unidades = montar_evento(participantes=20)
    confirmados: list[int] = []
    recusados: list[Exception] = []
    barreira = threading.Barrier(4)

    def worker(indice: int) -> None:
        # A barreira vem ANTES de abrir a sessao: como toda transacao e
        # BEGIN IMMEDIATE, qualquer leitura ja tomaria o lock de escrita e as
        # demais threads nunca chegariam ate aqui.
        barreira.wait(timeout=30)
        db = SessionLocal()
        try:
            evento = db.get(Event, event_id)
            usuario = db.scalar(select(User))
            sorteio, _ = realizar_sorteio(
                db, evento, unidades[0], f"thread-direta-{indice:04d}", usuario
            )
            db.commit()
            confirmados.append(sorteio.id)
        except Exception as exc:  # noqa: BLE001 - o teste classifica abaixo
            db.rollback()
            recusados.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(confirmados) == 1, (confirmados, recusados)
    assert len(recusados) == 3
    assert all(isinstance(e, RegraDeNegocio) for e in recusados), recusados

    with session_scope() as db:
        assert (
            db.query(Draw)
            .filter(Draw.prize_unit_id == unidades[0], Draw.status == StatusSorteio.VALIDO.value)
            .count()
            == 1
        )


def test_duas_unidades_em_paralelo_geram_ganhadores_distintos(cliente, auth):
    """Com regra de vitoria unica, sorteios paralelos nao podem repetir pessoa."""
    event_id, _, unidades = montar_evento(participantes=8, quantidade_premio=2)
    resultados: list[dict] = []
    barreira = threading.Barrier(2)

    def disparar(indice: int) -> None:
        barreira.wait()
        resposta = cliente.post(
            f"/api/events/{event_id}/sorteio",
            json={
                "prize_unit_id": unidades[indice],
                "idempotency_key": f"paralelo-{indice:04d}",
            },
            headers=auth,
        )
        resultados.append({"status": resposta.status_code, "corpo": resposta.json()})

    threads = [threading.Thread(target=disparar, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    sucessos = [r["corpo"] for r in resultados if r["status"] == 200]
    assert len(sucessos) == 2, resultados
    assert sucessos[0]["ganhador_id"] != sucessos[1]["ganhador_id"]


# ---------------------------------------------------------------- elegibilidade
def test_bloqueia_sem_participantes_elegiveis(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=3, presentes=0)

    conferencia = cliente.get(
        f"/api/events/{event_id}/sorteio/elegiveis",
        params={"prize_unit_id": unidades[0]},
        headers=auth,
    ).json()
    assert conferencia["total"] == 0
    assert conferencia["pode_sortear"] is False

    resposta = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "sem-elegiveis-1"},
        headers=auth,
    )
    assert resposta.status_code == 409
    assert "elegíveis" in resposta.json()["detail"]


def test_ganhador_nao_repete_quando_regra_proibe(cliente, auth):
    """3 participantes, 4 unidades: a quarta rodada deve ser bloqueada."""
    event_id, _, unidades = montar_evento(participantes=3, quantidade_premio=4)

    ganhadores = []
    for indice in range(3):
        resposta = cliente.post(
            f"/api/events/{event_id}/sorteio",
            json={"prize_unit_id": unidades[indice], "idempotency_key": f"unica-{indice:04d}"},
            headers=auth,
        )
        assert resposta.status_code == 200, resposta.text
        ganhadores.append(resposta.json()["ganhador_id"])

    assert len(set(ganhadores)) == 3

    quarta = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[3], "idempotency_key": "unica-0004"},
        headers=auth,
    )
    assert quarta.status_code == 409


def test_permite_repetir_quando_regra_autoriza(cliente, auth):
    event_id, _, unidades = montar_evento(
        participantes=1, quantidade_premio=3, permite_multiplas_vitorias=True
    )
    for indice in range(3):
        resposta = cliente.post(
            f"/api/events/{event_id}/sorteio",
            json={"prize_unit_id": unidades[indice], "idempotency_key": f"multi-{indice:04d}"},
            headers=auth,
        )
        assert resposta.status_code == 200, resposta.text


def test_exige_presenca_filtra_ausentes(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=6, presentes=2, quantidade_premio=1)
    resposta = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "presenca-0001"},
        headers=auth,
    )
    assert resposta.status_code == 200
    assert resposta.json()["ganhador_id"] in ids[:2]
    assert resposta.json()["elegiveis_total"] == 2


def test_participante_excluido_nao_concorre(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=2, quantidade_premio=1)
    excluido = ids[0]
    resposta = cliente.post(
        f"/api/events/{event_id}/participantes/{excluido}/participacao",
        json={"participando": False, "motivo": "Nao e elegivel pelo regulamento interno"},
        headers=auth,
    )
    assert resposta.status_code == 200

    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "excluido-0001"},
        headers=auth,
    ).json()
    assert sorteio["ganhador_id"] == ids[1]
    assert sorteio["elegiveis_total"] == 1


# ---------------------------------------------------------------- anulacao
def test_anulacao_exige_justificativa_e_permite_novo_sorteio(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=5, quantidade_premio=1)
    primeiro = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "anular-0001"},
        headers=auth,
    ).json()

    sem_motivo = cliente.post(
        f"/api/events/{event_id}/sorteios/{primeiro['id']}/anular",
        json={"motivo": "x", "tipo": "ausencia"},
        headers=auth,
    )
    assert sem_motivo.status_code == 422

    anulado = cliente.post(
        f"/api/events/{event_id}/sorteios/{primeiro['id']}/anular",
        json={"motivo": "Ganhador nao estava presente no salao", "tipo": "ausencia"},
        headers=auth,
    )
    assert anulado.status_code == 200
    assert anulado.json()["status"] == "anulado"

    novo = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "anular-0002"},
        headers=auth,
    )
    assert novo.status_code == 200, novo.text
    assert novo.json()["draw_anterior_id"] == primeiro["id"]
    # Regra padrao: anulado por ausencia nao reconcorre.
    assert novo.json()["ganhador_id"] != primeiro["ganhador_id"]

    with session_scope() as db:
        validos = db.query(Draw).filter(
            Draw.prize_unit_id == unidades[0], Draw.status == StatusSorteio.VALIDO.value
        ).count()
        total = db.query(Draw).filter(Draw.prize_unit_id == unidades[0]).count()
    assert validos == 1
    assert total == 2  # o resultado anulado continua registrado


def test_anular_entregue_exige_confirmacao_de_estorno(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=5, quantidade_premio=1)
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "estorno-0001"},
        headers=auth,
    ).json()

    entrega = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/entrega",
        json={"entregue": True},
        headers=auth,
    )
    assert entrega.status_code == 200
    assert entrega.json()["entregue"] is True

    sem_confirmacao = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/anular",
        json={"motivo": "Premio entregue a pessoa errada", "tipo": "erro_operacional"},
        headers=auth,
    )
    assert sem_confirmacao.status_code == 409
    assert "estorno" in sem_confirmacao.json()["detail"].lower()

    com_confirmacao = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/anular",
        json={
            "motivo": "Premio entregue a pessoa errada",
            "tipo": "erro_operacional",
            "confirmar_estorno": True,
        },
        headers=auth,
    )
    assert com_confirmacao.status_code == 200
    assert com_confirmacao.json()["estorno_entrega"] is True
    assert com_confirmacao.json()["entregue"] is False


def test_nao_existe_rota_para_editar_ganhador(cliente, auth):
    """Garante que nao expomos nenhuma forma de escolher ou trocar o vencedor."""
    caminhos = [rota.path for rota in cliente.app.routes]
    assert not any("ganhador" in caminho for caminho in caminhos)
    for rota in cliente.app.routes:
        metodos = getattr(rota, "methods", set())
        if "/sorteios/" in rota.path and metodos & {"PATCH", "PUT"}:
            pytest.fail(f"Rota de edicao de resultado encontrada: {rota.path}")


# ---------------------------------------------------------------- aleatoriedade
def test_distribuicao_uniforme_do_sorteio():
    """Sanidade estatistica do CSPRNG: nenhum indice fica fora de uma faixa larga."""
    total = 10
    amostras = 20_000
    contagem = Counter(escolher_indice(total) for _ in range(amostras))
    esperado = amostras / total
    assert set(contagem) == set(range(total))
    for indice in range(total):
        assert abs(contagem[indice] - esperado) < esperado * 0.25, contagem


def test_snapshot_de_elegiveis_e_gravado(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=7, quantidade_premio=1)
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "snapshot-0001"},
        headers=auth,
    ).json()

    with session_scope() as db:
        registro = db.get(Draw, sorteio["id"])
        assert sorted(registro.elegiveis_ids) == sorted(ids)
        assert registro.elegiveis_total == 7
        assert registro.participant_id in registro.elegiveis_ids
