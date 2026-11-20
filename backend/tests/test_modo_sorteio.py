"""Modo de sorteio por evento: numero da sorte (padrao) ou faixa de matriculas."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, Draw, Event, Participant, RuleChange
from app.services import sorteio as servico
from conftest import montar_evento


def _regras(cliente, auth, event_id, **campos):
    return cliente.patch(f"/api/events/{event_id}/regras", json=campos, headers=auth)


def _sortear(cliente, auth, event_id, unidade, chave):
    return cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidade, "idempotency_key": chave},
        headers=auth,
    )


def _matricula(participante_id: int) -> str:
    with session_scope() as db:
        return db.get(Participant, participante_id).matricula


def test_evento_novo_continua_no_modo_numero_da_sorte(cliente, auth):
    event_id, _, _ = montar_evento(participantes=4)
    regras = cliente.get(f"/api/events/{event_id}/regras", headers=auth).json()
    assert regras["modo_sorteio"] == "numero_sorte"
    assert regras["matricula_faixa_inicio"] is None
    resumo = cliente.get(f"/api/events/{event_id}/regras/resumo", headers=auth).json()
    assert resumo["elegiveis_agora"] == 4
    assert resumo["itens"][0].startswith("Modo do sorteio: número da sorte")


def test_faixa_filtra_elegiveis_e_o_ganhador_sempre_esta_na_faixa(cliente, auth):
    # Matriculas 00001..00010; faixa 3..6 -> so 4 pessoas concorrem.
    event_id, _, unidades = montar_evento(participantes=10, quantidade_premio=4, permite_multiplas_vitorias=True)
    r = _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula", matricula_faixa_inicio=3, matricula_faixa_fim=6)
    assert r.status_code == 200, r.text

    conferencia = cliente.get(
        f"/api/events/{event_id}/sorteio/elegiveis", params={"prize_unit_id": unidades[0]}, headers=auth
    ).json()
    assert conferencia["total"] == 4

    for i, unidade in enumerate(unidades):
        resposta = _sortear(cliente, auth, event_id, unidade, f"faixa-{i:04d}")
        assert resposta.status_code == 200, resposta.text
        with session_scope() as db:
            ganhador = db.get(Draw, resposta.json()["id"]).participant_id
        assert 3 <= int(_matricula(ganhador)) <= 6

    with session_scope() as db:
        log = db.scalars(select(AuditLog).where(AuditLog.acao == "sorteio_realizado")).first()
        assert log.detalhes["modo_sorteio"] == "faixa_matricula"
        assert log.detalhes["faixa_matricula"] == [3, 6]
        assert all(d.elegiveis_total == 4 for d in db.scalars(select(Draw)).all())


def test_faixa_mantem_as_demais_regras(cliente, auth):
    # 6 pessoas, so as 3 primeiras presentes; faixa 2..6 -> elegiveis: 2 e 3.
    event_id, _, unidades = montar_evento(participantes=6, presentes=3)
    _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula", matricula_faixa_inicio=2, matricula_faixa_fim=6)
    total = cliente.get(
        f"/api/events/{event_id}/sorteio/elegiveis", params={"prize_unit_id": unidades[0]}, headers=auth
    ).json()["total"]
    assert total == 2


def test_matricula_com_letras_nunca_entra_na_faixa(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=3)
    with session_scope() as db:
        p = db.get(Participant, ids[0])
        p.matricula = "A-0001"  # o listener refaz a matricula normalizada
    _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula", matricula_faixa_inicio=0, matricula_faixa_fim=99999)
    previa = cliente.get(
        f"/api/events/{event_id}/regras/faixa-matricula", params={"inicio": 0, "fim": 99999}, headers=auth
    ).json()
    assert previa == {
        "inicio": 0, "fim": 99999, "participantes_ativos": 3, "dentro_da_faixa": 2, "fora_da_faixa": 0,
        "matricula_nao_numerica": 1, "menor_matricula": 2, "maior_matricula": 3,
    }
    assert cliente.get(
        f"/api/events/{event_id}/sorteio/elegiveis", params={"prize_unit_id": unidades[0]}, headers=auth
    ).json()["total"] == 2


def test_zeros_a_esquerda_nao_importam(cliente, auth):
    # "00026" e 26: a faixa compara o numero.
    event_id, _, _ = montar_evento(participantes=30)
    _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula", matricula_faixa_inicio=26, matricula_faixa_fim=26)
    resumo = cliente.get(f"/api/events/{event_id}/regras/resumo", headers=auth).json()
    assert resumo["elegiveis_agora"] == 1
    assert "de 26 a 26" in resumo["itens"][0]


def test_faixa_obrigatoria_e_valida(cliente, auth):
    event_id, _, _ = montar_evento(participantes=3)
    sem_faixa = _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula")
    assert sem_faixa.status_code == 422
    invertida = _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula", matricula_faixa_inicio=9, matricula_faixa_fim=1)
    assert invertida.status_code == 422
    assert _regras(cliente, auth, event_id, modo_sorteio="sorteio_magico").status_code == 422
    assert _regras(cliente, auth, event_id, matricula_faixa_inicio=-1).status_code == 422
    # Nada foi gravado.
    regras = cliente.get(f"/api/events/{event_id}/regras", headers=auth).json()
    assert regras["modo_sorteio"] == "numero_sorte"


def test_faixa_sem_ninguem_bloqueia_o_sorteio_com_mensagem_clara(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=3)
    _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula", matricula_faixa_inicio=500, matricula_faixa_fim=900)
    resposta = _sortear(cliente, auth, event_id, unidades[0], "faixa-vazia-1")
    assert resposta.status_code == 409
    assert "entre 500 e 900" in resposta.json()["detail"]


def test_voltar_ao_numero_da_sorte_libera_todos_e_fica_no_historico(cliente, auth):
    event_id, _, _ = montar_evento(participantes=5)
    _regras(cliente, auth, event_id, modo_sorteio="faixa_matricula", matricula_faixa_inicio=1, matricula_faixa_fim=2)
    assert cliente.get(f"/api/events/{event_id}/regras/resumo", headers=auth).json()["elegiveis_agora"] == 2
    assert _regras(cliente, auth, event_id, modo_sorteio="numero_sorte").status_code == 200
    assert cliente.get(f"/api/events/{event_id}/regras/resumo", headers=auth).json()["elegiveis_agora"] == 5
    with session_scope() as db:
        campos = [m.campo for m in db.scalars(select(RuleChange).where(RuleChange.event_id == event_id)).all()]
    assert campos.count("modo_sorteio") == 2
    assert "matricula_faixa_inicio" in campos and "matricula_faixa_fim" in campos


def test_distribuicao_uniforme_dentro_da_faixa():
    # Sem HTTP: muitos sorteios sobre a lista filtrada; cada um dos 4 da faixa
    # deve sair perto de 1/4 das vezes e ninguem de fora deve sair.
    event_id, _, _ = montar_evento(participantes=8)
    with session_scope() as db:
        evento = db.get(Event, event_id)
        evento.modo_sorteio = "faixa_matricula"
        evento.matricula_faixa_inicio, evento.matricula_faixa_fim = 5, 8
    with session_scope() as db:
        from app.services.elegibilidade import participantes_elegiveis

        evento = db.get(Event, event_id)
        elegiveis = participantes_elegiveis(db, evento)
        assert sorted(int(p.matricula) for p in elegiveis) == [5, 6, 7, 8]
        contagem = Counter(elegiveis[servico.escolher_indice(len(elegiveis))].matricula for _ in range(8000))
    assert set(contagem) == {"00005", "00006", "00007", "00008"}
    assert all(1700 < n < 2300 for n in contagem.values()), contagem
