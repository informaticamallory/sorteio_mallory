"""Fase 7: carrossel dos ganhadores no telao."""

from __future__ import annotations

import json
import time
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import bus
from app.database import session_scope
from app.models import AuditLog, DisplayState, Draw, Event, StatusSorteio, utcnow
from app.services import carrossel
from apoio import configurar_evento
from conftest import montar_evento


def _api(event_id: int, caminho: str) -> str:
    return f"/api/events/{event_id}{caminho}"


def _bloco_com_ganhadores(cliente, auth, ganhadores: int, *, finalizar: bool = True, segundos: int = 6):
    """Evento com um bloco e `ganhadores` sorteios validos. Devolve (event_id, bloco_id)."""
    event_id, _participantes, unidades = montar_evento(
        participantes=ganhadores + 3, quantidade_premio=ganhadores
    )
    # Animacao de 1 ms: os sorteios do teste nao esperam a revelacao.
    configurar_evento(event_id, autocadastro_ativo=False, duracao_animacao_ms=1, carrossel_segundos=segundos)
    blocos = cliente.post(_api(event_id, "/blocos/distribuir"), json={"capacidade": ganhadores}, headers=auth)
    bloco_id = blocos.json()["blocos"][0]["id"]
    assert cliente.post(_api(event_id, f"/blocos/{bloco_id}/iniciar"), headers=auth).status_code == 200
    for i, unidade in enumerate(unidades):
        time.sleep(0.005)
        resposta = cliente.post(
            _api(event_id, "/sorteio"),
            json={"prize_unit_id": unidade, "idempotency_key": f"carrossel-{i:04d}"},
            headers=auth,
        )
        assert resposta.status_code == 200, resposta.text
    time.sleep(0.005)
    if finalizar:
        resposta = cliente.post(_api(event_id, f"/blocos/{bloco_id}/finalizar"), json={}, headers=auth)
        assert resposta.status_code == 200, resposta.text
    return event_id, bloco_id


def _telao(cliente, event_id: int) -> dict:
    with session_scope() as db:
        token = db.get(Event, event_id).telao_token
    resposta = cliente.get(f"/api/public/{token}/estado")
    assert resposta.status_code == 200
    return resposta.json()


def _comando(cliente, auth, event_id: int, acao: str, bloco_id: int | None = None):
    return cliente.post(
        _api(event_id, "/telao/carrossel"), json={"acao": acao, "bloco_id": bloco_id}, headers=auth
    )


def _recuar_relogio(event_id: int, segundos: float) -> None:
    """Simula a passagem do tempo movendo o inicio da reproducao para tras."""
    with session_scope() as db:
        ds = db.get(DisplayState, event_id)
        if ds.carrossel_desde is not None:
            ds.carrossel_desde -= timedelta(seconds=segundos)


# ------------------------------------------------------------------ inicio automatico
@pytest.mark.parametrize("quantidade", [1, 25])
def test_finalizar_bloco_apresenta_todos_os_ganhadores(cliente, auth, quantidade):
    event_id, bloco_id = _bloco_com_ganhadores(cliente, auth, quantidade)
    estado = _telao(cliente, event_id)

    assert estado["estado"] == "carrossel_ganhadores"
    dados = estado["carrossel"]
    assert dados["total"] == quantidade == len(dados["slides"])
    assert dados["posicao"] == 0 and dados["pausado"] is False
    assert estado["bloco"]["numero"] == 1
    slide = dados["slides"][0]
    assert set(slide) == {
        "premio_nome", "premio_imagem_url", "premio_descricao", "unidade_numero",
        "ganhador_nome", "ganhador_setor", "ganhador_foto_url",
        "ganhador_numero",  # numero do sorteio: aleatorio, nao e dado pessoal
    }
    assert isinstance(slide["ganhador_numero"], int)
    # Telao publico: nada de matricula ou pulseira.
    texto = json.dumps(estado)
    assert "matricula" not in texto and "pulseira" not in texto
    with session_scope() as db:
        auditoria = db.scalar(select(AuditLog).where(AuditLog.acao == "carrossel_iniciado"))
        assert auditoria.detalhes["automatico"] is True


def test_bloco_sem_ganhadores_nao_inicia_carrossel(cliente, auth):
    event_id, _p, _u = montar_evento(participantes=3, quantidade_premio=2)
    configurar_evento(event_id, autocadastro_ativo=False)
    bloco_id = cliente.post(_api(event_id, "/blocos/distribuir"), json={"capacidade": 2}, headers=auth).json()["blocos"][0]["id"]
    cliente.post(_api(event_id, f"/blocos/{bloco_id}/iniciar"), headers=auth)
    cliente.post(_api(event_id, f"/blocos/{bloco_id}/finalizar"), json={"confirmar_pendentes": True}, headers=auth)
    assert _telao(cliente, event_id)["estado"] != "carrossel_ganhadores"
    assert _comando(cliente, auth, event_id, "iniciar", bloco_id).status_code == 409


def test_fim_de_bloco_durante_a_animacao_nao_corta_a_revelacao(cliente, auth):
    event_id, bloco_id = _bloco_com_ganhadores(cliente, auth, 2, finalizar=False)
    configurar_evento(event_id, autocadastro_ativo=False, duracao_animacao_ms=60_000)
    with session_scope() as db:
        ds = db.get(DisplayState, event_id)
        ds.estado = "sorteando"
        ds.revelar_em = utcnow() + timedelta(seconds=30)
        ds.draw_id = db.scalar(select(Draw.id).order_by(Draw.id.desc()))

    cliente.post(_api(event_id, f"/blocos/{bloco_id}/finalizar"), json={}, headers=auth)
    estado = _telao(cliente, event_id)
    assert estado["estado"] == "sorteando"  # a revelacao continua
    assert estado["carrossel_agendado_em"] is not None

    # Revelacao + pausa terminadas: a proxima leitura ja mostra o carrossel.
    with session_scope() as db:
        ds = db.get(DisplayState, event_id)
        ds.revelar_em = utcnow() - timedelta(seconds=10)
        ds.carrossel_desde = utcnow() - timedelta(seconds=1)
    assert _telao(cliente, event_id)["estado"] == "carrossel_ganhadores"


# ------------------------------------------------------------------ tempo e controles
def test_cada_ganhador_fica_pelo_menos_1_segundo(cliente, auth):
    event_id, _p, _u = montar_evento(participantes=1)
    for segundos in (0, -1, 61):
        resposta = cliente.patch(_api(event_id, ""), json={"carrossel_segundos": segundos}, headers=auth)
        assert resposta.status_code == 422
    assert cliente.patch(_api(event_id, ""), json={"carrossel_segundos": 1}, headers=auth).json()["carrossel_segundos"] == 1
    assert cliente.patch(_api(event_id, ""), json={"carrossel_segundos": 9}, headers=auth).json()["carrossel_segundos"] == 9

    # Com 1 s, o carrossel avanca a cada segundo.
    with session_scope() as db:
        ds = DisplayState(event_id=999, carrossel_indice=0, carrossel_duracao_s=1, carrossel_desde=utcnow() - timedelta(seconds=0.9))
        assert carrossel.posicao(ds, total=10) == 0
        ds.carrossel_desde = utcnow() - timedelta(seconds=1.1)
        assert carrossel.posicao(ds, total=10) == 1
        # Mesmo que o banco tenha um valor menor (manipulado), o servidor usa 1 s.
        ds.carrossel_duracao_s = 0
        ds.carrossel_desde = utcnow() - timedelta(seconds=0.5)
        assert carrossel.posicao(ds, total=10) == 0
        db.rollback()


def test_avanca_sozinho_e_termina_no_resumo(cliente, auth):
    event_id, _bloco = _bloco_com_ganhadores(cliente, auth, 3, segundos=5)
    _recuar_relogio(event_id, 5.2)
    assert _telao(cliente, event_id)["carrossel"]["posicao"] == 1
    _recuar_relogio(event_id, 60)
    # Para no slide-resumo (posicao == total), sem iniciar nada sozinho.
    estado = _telao(cliente, event_id)
    assert estado["carrossel"]["posicao"] == 3
    assert estado["estado"] == "carrossel_ganhadores"


def test_pausa_e_retomada_preservam_a_posicao(cliente, auth):
    event_id, _bloco = _bloco_com_ganhadores(cliente, auth, 5, segundos=5)
    _recuar_relogio(event_id, 11)  # dois slides
    pausado = _comando(cliente, auth, event_id, "pausar").json()["carrossel"]
    assert pausado["pausado"] is True and pausado["posicao"] == 2

    _recuar_relogio(event_id, 100)  # sem efeito enquanto pausado
    time.sleep(0.01)
    assert _telao(cliente, event_id)["carrossel"]["posicao"] == 2

    retomado = _comando(cliente, auth, event_id, "continuar").json()["carrossel"]
    assert retomado["pausado"] is False and retomado["posicao"] == 2
    _recuar_relogio(event_id, 5.1)
    assert _telao(cliente, event_id)["carrossel"]["posicao"] == 3


def test_proximo_anterior_repetir_e_encerrar(cliente, auth):
    event_id, bloco_id = _bloco_com_ganhadores(cliente, auth, 3)
    assert _comando(cliente, auth, event_id, "anterior").json()["carrossel"]["posicao"] == 0
    assert _comando(cliente, auth, event_id, "proximo").json()["carrossel"]["posicao"] == 1
    for _ in range(5):
        _comando(cliente, auth, event_id, "proximo")
    assert _telao(cliente, event_id)["carrossel"]["posicao"] == 3  # nao passa do resumo
    assert _comando(cliente, auth, event_id, "repetir").json()["carrossel"]["posicao"] == 0

    encerrado = _comando(cliente, auth, event_id, "encerrar").json()
    assert encerrado["estado"] == "aguardando" and encerrado["carrossel"] is None
    assert _comando(cliente, auth, event_id, "pausar").status_code == 409
    # Pode ser reapresentado manualmente.
    assert _comando(cliente, auth, event_id, "iniciar", bloco_id).json()["estado"] == "carrossel_ganhadores"


def test_carrossel_nao_altera_resultados_nem_sorteia(cliente, auth):
    event_id, bloco_id = _bloco_com_ganhadores(cliente, auth, 3)
    with session_scope() as db:
        antes = [(d.id, d.participant_id, d.status) for d in db.scalars(select(Draw).order_by(Draw.id))]
    for acao in ("pausar", "continuar", "proximo", "anterior", "repetir", "encerrar"):
        _comando(cliente, auth, event_id, acao)
    _comando(cliente, auth, event_id, "iniciar", bloco_id)
    with session_scope() as db:
        depois = [(d.id, d.participant_id, d.status) for d in db.scalars(select(Draw).order_by(Draw.id))]
    assert antes == depois


def test_proximo_bloco_nao_sorteia_com_o_carrossel_na_tela(cliente, auth):
    event_id, _bloco1 = _bloco_com_ganhadores(cliente, auth, 2)
    with session_scope() as db:
        evento = db.get(Event, event_id)
        from app.models import Prize, PrizeUnit

        premio = Prize(event_id=event_id, nome="Segundo", quantidade=1, ordem=2)
        db.add(premio)
        db.flush()
        unidade = PrizeUnit(prize_id=premio.id, numero=1)
        db.add(unidade)
        db.flush()
        unidade_id = unidade.id
        assert evento is not None
    bloco2 = cliente.post(_api(event_id, "/blocos/remanescentes"), json={}, headers=auth).json()["id"]
    assert cliente.post(_api(event_id, f"/blocos/{bloco2}/iniciar"), headers=auth).status_code == 200
    # Iniciar o bloco seguinte nao encerra a apresentacao.
    assert _telao(cliente, event_id)["estado"] == "carrossel_ganhadores"

    sortear = lambda chave: cliente.post(  # noqa: E731
        _api(event_id, "/sorteio"), json={"prize_unit_id": unidade_id, "idempotency_key": chave}, headers=auth
    )
    recusado = sortear("bloco2-tentativa-1")
    assert recusado.status_code == 409 and "apresentação" in recusado.json()["detail"]
    _comando(cliente, auth, event_id, "encerrar")
    assert sortear("bloco2-tentativa-2").status_code == 200


def test_anulacao_some_do_carrossel(cliente, auth):
    event_id, _bloco = _bloco_com_ganhadores(cliente, auth, 3)
    with session_scope() as db:
        alvo = db.scalar(select(Draw).where(Draw.status == StatusSorteio.VALIDO.value).order_by(Draw.id))
        alvo_id = alvo.id
    cliente.post(
        _api(event_id, f"/sorteios/{alvo_id}/anular"),
        json={"motivo": "Teste de anulacao", "tipo": "outro"},
        headers=auth,
    )
    assert _telao(cliente, event_id)["carrossel"]["total"] == 2


# ------------------------------------------------------------------ reconexao e sincronia
def test_reconexao_recupera_o_mesmo_slide(cliente, auth):
    event_id, _bloco = _bloco_com_ganhadores(cliente, auth, 4, segundos=5)
    _comando(cliente, auth, event_id, "proximo")
    _comando(cliente, auth, event_id, "proximo")
    _comando(cliente, auth, event_id, "pausar")
    # Telao recarregado (F5) e painel autenticado leem o mesmo estado oficial.
    primeiro = _telao(cliente, event_id)
    segundo = _telao(cliente, event_id)
    painel = cliente.get(_api(event_id, "/telao/estado"), headers=auth).json()
    for estado in (primeiro, segundo, painel):
        assert estado["estado"] == "carrossel_ganhadores"
        assert estado["carrossel"]["posicao"] == 2 and estado["carrossel"]["pausado"] is True
    assert primeiro["versao"] == segundo["versao"] == painel["versao"]


def test_cada_comando_e_transmitido_ao_telao(cliente, auth):
    event_id, _bloco = _bloco_com_ganhadores(cliente, auth, 2)
    fila = bus.assinar(event_id)
    try:
        _comando(cliente, auth, event_id, "pausar")
        _comando(cliente, auth, event_id, "proximo")
        time.sleep(0.2)
        mensagens = []
        while not fila.empty():
            mensagens.append(json.loads(fila.get_nowait()))
    finally:
        bus.cancelar(event_id, fila)
    assert [m["carrossel"]["posicao"] for m in mensagens] == [0, 1]
    assert all(m["carrossel"]["pausado"] for m in mensagens)
    assert mensagens[0]["versao"] < mensagens[1]["versao"]
