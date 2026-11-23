"""Distribuicao com "Misturar os premios": o mesmo premio nao sai varias vezes seguidas."""
from __future__ import annotations

import random

import pytest

from app.services.blocos import misturar_por_premio
from test_blocos import _acao, _detalhe, _distribuir, _evento, _sortear_proxima


def _misturar(contagens: dict[str, int]) -> list[tuple[str, int]]:
    itens = [(premio, k) for premio, c in contagens.items() for k in range(c)]
    return misturar_por_premio(itens, lambda item: item[0])


def _repeticoes(premios: list) -> int:
    return sum(1 for a, b in zip(premios, premios[1:]) if a == b)


def test_exemplo_intercala_e_espalha():
    assert "".join(p for p, _k in _misturar({"A": 4, "T": 2, "B": 1})) == "ATABATA"


@pytest.mark.parametrize("semente", range(5))
def test_nunca_repete_quando_e_possivel_e_nao_perde_unidades(semente):
    sorteio = random.Random(semente)
    for _ in range(400):
        contagens = {chr(65 + i): sorteio.randint(1, 15) for i in range(sorteio.randint(1, 12))}
        sequencia = _misturar(contagens)
        # Nenhuma unidade some ou duplica, e cada premio segue unidade 1, 2, 3...
        for premio, c in contagens.items():
            assert [k for p, k in sequencia if p == premio] == list(range(c))
        if max(contagens.values()) <= (sum(contagens.values()) + 1) // 2:
            assert _repeticoes([p for p, _k in sequencia]) == 0, contagens


def test_premio_maioria_fica_espalhado_e_nao_amontoado_no_fim():
    # 8 de 10: repetir e inevitavel, mas os outros ficam no meio da fila.
    assert "".join(p for p, _k in _misturar({"A": 8, "B": 2})) == "AABAAAABAA"


def _premios_do_bloco(cliente, auth, event_id, bloco_id) -> list[str]:
    return [u["premio_nome"] for u in _detalhe(cliente, auth, event_id, bloco_id)["unidades"]]


def test_distribuir_misturando(cliente, auth):
    event_id = _evento([3, 3, 3])
    resposta = cliente.post(
        f"/api/events/{event_id}/blocos/distribuir", json={"capacidade": 9, "misturar": True}, headers=auth
    )
    assert resposta.status_code == 200, resposta.text
    (bloco,) = resposta.json()["blocos"]
    assert _premios_do_bloco(cliente, auth, event_id, bloco["id"]) == ["Premio 1", "Premio 2", "Premio 3"] * 3


def test_distribuir_sem_misturar_mantem_a_ordem_do_cadastro(cliente, auth):
    event_id = _evento([2, 2])
    (bloco,) = _distribuir(cliente, auth, event_id, 4).json()["blocos"]
    assert _premios_do_bloco(cliente, auth, event_id, bloco["id"]) == ["Premio 1"] * 2 + ["Premio 2"] * 2


def test_remanescentes_misturando(cliente, auth):
    event_id = _evento([3, 3])
    (bloco,) = _distribuir(cliente, auth, event_id, 6).json()["blocos"]
    _acao(cliente, auth, event_id, bloco["id"], "iniciar")
    _sortear_proxima(cliente, auth, event_id, bloco["id"], "misturar-000001")
    _acao(cliente, auth, event_id, bloco["id"], "finalizar", {"confirmar_pendentes": True})
    cliente.post(f"/api/events/{event_id}/telao/carrossel", json={"acao": "encerrar"}, headers=auth)

    criado = cliente.post(
        f"/api/events/{event_id}/blocos/remanescentes", json={"capacidade": 10, "misturar": True}, headers=auth
    )
    assert criado.status_code == 201, criado.text
    premios = _premios_do_bloco(cliente, auth, event_id, criado.json()["id"])
    assert sorted(premios) == ["Premio 1"] * 2 + ["Premio 2"] * 3
    assert _repeticoes(premios) == 0
