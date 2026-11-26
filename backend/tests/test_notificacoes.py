"""Fase 6: notificacoes individuais, canal privado e situacao da entrega."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta

from sqlalchemy import select, update

from app import bus
from app.database import session_scope
from app.models import AuditLog, Notificacao, User, utcnow
from app.routers.minha_area import eventos_privados, verificar_sessao
from apoio import autocadastrar, configurar_evento
from conftest import montar_evento


def _sortear(cliente, auth, event_id: int, unidade: int, chave: str = "k1"):
    resposta = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidade, "idempotency_key": f"chave-teste-{chave}"},
        headers=auth,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _revelar_tudo() -> None:
    """Avanca o relogio das notificacoes (fim da animacao do telao)."""
    with session_scope() as db:
        db.execute(update(Notificacao).values(disponivel_em=utcnow() - timedelta(seconds=1)))


def _colaborador(cliente, auth, event_id, pid, matricula, pulseira="P-1") -> dict:
    resultado = autocadastrar(cliente, auth, event_id, pid, matricula, pulseira=pulseira)
    return {"Authorization": f"Bearer {resultado['access_token']}"}


def _notificacoes(cliente, cab) -> list[dict]:
    resposta = cliente.get("/api/minha-area/notificacoes", headers=cab)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


# ------------------------------------------------------------------ criacao
def test_ganhador_recebe_notificacao_persistente_ligada_ao_sorteio(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = _colaborador(cliente, auth, event_id, participantes[0], "00001")

    sorteio = _sortear(cliente, auth, event_id, unidades[0])

    with session_scope() as db:
        n = db.scalar(select(Notificacao))
        assert (n.event_id, n.participant_id, n.draw_id, n.tipo) == (
            event_id, participantes[0], sorteio["id"], "PREMIO_GANHO",
        )
        assert n.prize_id == sorteio["premio_id"]
        assert n.usuario_id is not None
        assert n.disponivel_em is not None and n.disponivel_em > utcnow()

    # Antes do telao revelar, nem a notificacao nem o premio aparecem.
    assert _notificacoes(cliente, cab) == []
    area = cliente.get("/api/minha-area", headers=cab).json()
    assert area["participacoes"][0]["premios"] == [] and area["notificacoes_nao_lidas"] == 0

    _revelar_tudo()
    [notificacao] = _notificacoes(cliente, cab)
    assert notificacao["titulo"] == "🎉 Parabéns! Você foi sorteado!"
    assert "Seu número da sorte foi contemplado no Sorteio Empresa Teste." in notificacao["mensagem"]
    assert "Prêmio: Premio Teste" in notificacao["mensagem"]
    assert notificacao["situacao"] == "aguardando_retirada"
    assert notificacao["premio_nome"] == "Premio Teste" and notificacao["lida"] is False
    area = cliente.get("/api/minha-area", headers=cab).json()
    assert area["notificacoes_nao_lidas"] == 1
    assert len(area["participacoes"][0]["premios"]) == 1


def test_notificacao_criada_antes_da_conta_aparece_depois_do_autocadastro(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    _sortear(cliente, auth, event_id, unidades[0])
    _revelar_tudo()
    with session_scope() as db:
        assert db.scalar(select(Notificacao.usuario_id)) is None

    cab = _colaborador(cliente, auth, event_id, participantes[0], "00001")
    [notificacao] = _notificacoes(cliente, cab)
    assert notificacao["tipo"] == "PREMIO_GANHO"
    with session_scope() as db:
        assert db.scalar(select(Notificacao.usuario_id)) is not None


def test_clique_duplicado_nao_duplica_a_notificacao(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=2)
    primeiro = _sortear(cliente, auth, event_id, unidades[0], chave="mesma")
    segundo = _sortear(cliente, auth, event_id, unidades[0], chave="mesma")
    assert segundo["reaproveitado"] is True and segundo["id"] == primeiro["id"]
    with session_scope() as db:
        assert len(db.scalars(select(Notificacao)).all()) == 1


def test_notificacoes_sao_privadas(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=2, exige_presenca=False)
    configurar_evento(event_id)
    cab_a = _colaborador(cliente, auth, event_id, participantes[0], "00001", "P-A")
    cab_b = _colaborador(cliente, auth, event_id, participantes[1], "00002", "P-B")

    sorteio = _sortear(cliente, auth, event_id, unidades[0])
    _revelar_tudo()
    ganhador, outro = (cab_a, cab_b) if sorteio["ganhador_id"] == participantes[0] else (cab_b, cab_a)

    [notificacao] = _notificacoes(cliente, ganhador)
    assert _notificacoes(cliente, outro) == []
    # Marcar a notificacao alheia responde como se ela nao existisse.
    alheia = cliente.post(f"/api/minha-area/notificacoes/{notificacao['id']}/lida", headers=outro)
    assert alheia.status_code == 404
    with session_scope() as db:
        assert db.get(Notificacao, notificacao["id"]).lida is False


def test_marcar_como_lida_e_todas(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1, quantidade_premio=2, permite_multiplas_vitorias=True)
    configurar_evento(event_id)
    cab = _colaborador(cliente, auth, event_id, participantes[0], "00001")
    _sortear(cliente, auth, event_id, unidades[0], "a")
    _sortear(cliente, auth, event_id, unidades[1], "b")
    _revelar_tudo()

    primeira, _segunda = _notificacoes(cliente, cab)
    resposta = cliente.post(f"/api/minha-area/notificacoes/{primeira['id']}/lida", headers=cab)
    assert resposta.json() == {"nao_lidas": 1}
    assert cliente.post("/api/minha-area/notificacoes/lidas", headers=cab).json()["marcadas"] == 1
    assert all(n["lida"] for n in _notificacoes(cliente, cab))
    assert cliente.get("/api/minha-area", headers=cab).json()["notificacoes_nao_lidas"] == 0


# ------------------------------------------------------------------ anulacao e entrega
def test_anulacao_registra_e_notifica_o_colaborador_uma_vez(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = _colaborador(cliente, auth, event_id, participantes[0], "00001")
    sorteio = _sortear(cliente, auth, event_id, unidades[0])
    _revelar_tudo()

    url = f"/api/events/{event_id}/sorteios/{sorteio['id']}/anular"
    corpo = {"motivo": "Ganhador nao estava presente", "tipo": "ausencia"}
    assert cliente.post(url, json=corpo, headers=auth).status_code == 200
    assert cliente.post(url, json=corpo, headers=auth).status_code == 409

    notificacoes = _notificacoes(cliente, cab)
    assert [n["tipo"] for n in notificacoes] == ["SORTEIO_ANULADO", "PREMIO_GANHO"]
    assert all(n["situacao"] == "anulado" for n in notificacoes)
    assert "ausência" in notificacoes[0]["mensagem"]
    # O motivo escrito pelo admin nao vai para o colaborador; so a categoria.
    assert "nao estava presente" not in notificacoes[0]["mensagem"]
    with session_scope() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.acao == "sorteio_anulado")) is not None
    assert cliente.get("/api/minha-area", headers=cab).json()["participacoes"][0]["premios"] == []


def test_anulacao_durante_a_animacao_nao_aparece_antes_do_premio(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = _colaborador(cliente, auth, event_id, participantes[0], "00001")
    sorteio = _sortear(cliente, auth, event_id, unidades[0])
    cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/anular",
        json={"motivo": "Erro de operacao", "tipo": "erro_operacional"},
        headers=auth,
    )
    assert _notificacoes(cliente, cab) == []
    _revelar_tudo()
    assert len(_notificacoes(cliente, cab)) == 2


def test_entrega_atualiza_a_situacao_na_area_pessoal(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = _colaborador(cliente, auth, event_id, participantes[0], "00001", pulseira="P-77")
    sorteio = _sortear(cliente, auth, event_id, unidades[0])
    _revelar_tudo()

    entrega = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/entrega",
        json={"entregue": True, "pulseira_conferida": "P-77"},
        headers=auth,
    )
    assert entrega.status_code == 200, entrega.text
    [notificacao] = _notificacoes(cliente, cab)
    assert notificacao["situacao"] == "entregue"
    premio = cliente.get("/api/minha-area", headers=cab).json()["participacoes"][0]["premios"][0]
    assert premio["entregue"] is True


# ------------------------------------------------------------------ tempo real
def _drenar(fila: asyncio.Queue) -> list[dict]:
    mensagens = []
    while not fila.empty():
        mensagens.append(json.loads(fila.get_nowait()))
    return mensagens


def test_aviso_vai_so_pelo_canal_privado_e_na_hora_da_revelacao(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    resultado = autocadastrar(cliente, auth, event_id, participantes[0], "00001", pulseira="P-9")
    usuario_id = resultado["usuario"]["id"]

    publico = bus.assinar(event_id)
    privado = bus.assinar(bus.canal_usuario(usuario_id))
    outro = bus.assinar(bus.canal_usuario(usuario_id + 1000))
    try:
        sorteio = _sortear(cliente, auth, event_id, unidades[0])
        time.sleep(0.3)
        assert _drenar(privado) == []  # animacao (1 s) ainda nao terminou
        time.sleep(1.2)
        assert _drenar(privado) == [{"tipo": "notificacao"}]

        cliente.post(
            f"/api/events/{event_id}/sorteios/{sorteio['id']}/entrega",
            json={"entregue": True},
            headers=auth,
        )
        time.sleep(0.2)
        assert _drenar(privado) == [{"tipo": "atualizacao"}]

        mensagens_publicas = _drenar(publico)
        assert mensagens_publicas and all(m["tipo"] == "estado" for m in mensagens_publicas)
        texto = json.dumps(mensagens_publicas, ensure_ascii=False)
        assert "00001" not in texto and "P-9" not in texto and "Parabéns" not in texto
        assert _drenar(outro) == []
    finally:
        bus.cancelar(event_id, publico)
        bus.cancelar(bus.canal_usuario(usuario_id), privado)
        bus.cancelar(bus.canal_usuario(usuario_id + 1000), outro)


def test_gerador_do_canal_privado_entrega_e_encerra_sessao_invalida():
    async def cenario() -> list[str]:
        fila: asyncio.Queue = asyncio.Queue()
        valida = {"ok": True}

        async def desconectado() -> bool:
            return False

        async def sessao_valida() -> bool:
            return valida["ok"]

        gerador = eventos_privados(fila, desconectado, sessao_valida, heartbeat=0.05)
        partes = [await gerador.__anext__()]
        await fila.put(json.dumps({"tipo": "notificacao"}))
        partes.append(await gerador.__anext__())
        partes.append(await gerador.__anext__())  # ping (sessao ainda valida)
        valida["ok"] = False
        partes.append(await gerador.__anext__())
        try:
            await gerador.__anext__()
            partes.append("CONTINUOU")
        except StopAsyncIteration:
            pass
        return partes

    partes = asyncio.run(cenario())
    assert '"pronto"' in partes[0]
    assert partes[1] == 'data: {"tipo": "notificacao"}\n\n'
    assert partes[2] == ": ping\n\n"
    assert '"sessao_encerrada"' in partes[3]
    assert "CONTINUOU" not in partes


def test_canal_privado_confere_token_conta_e_perfil(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    resultado = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    token = resultado["access_token"]

    assert verificar_sessao(None) == (401, None)
    assert verificar_sessao("lixo") == (401, None)
    assert verificar_sessao(token) == (200, resultado["usuario"]["id"])
    with session_scope() as db:
        db.get(User, resultado["usuario"]["id"]).sessao_versao += 1
    assert verificar_sessao(token)[0] == 401
    assert cliente.get("/api/minha-area/stream").status_code == 401


# ------------------------------------------------------------------ evento de teste
def test_evento_de_teste_some_do_portal_sem_apagar_nada(cliente, auth):
    from apoio import cabecalho, conta

    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = _colaborador(cliente, auth, event_id, participantes[0], "00001")
    _sortear(cliente, auth, event_id, unidades[0], chave="evento-teste")
    _revelar_tudo()
    assert len(_notificacoes(cliente, cab)) == 1
    assert [p["evento_id"] for p in cliente.get("/api/minha-area", headers=cab).json()["participacoes"]] == [event_id]

    # So o admin marca o evento como teste (o Organizador - RH configura, mas nao marca).
    rh = cabecalho(conta("ORGANIZADOR", login="rh.teste"))
    assert cliente.patch(f"/api/events/{event_id}", json={"evento_teste": True}, headers=rh).status_code == 403
    resposta = cliente.patch(f"/api/events/{event_id}", json={"evento_teste": True}, headers=auth)
    assert resposta.status_code == 200 and resposta.json()["evento_teste"] is True

    # Portal: sem aba, sem premios, sem avisos e sem contador. Nada foi apagado.
    area = cliente.get("/api/minha-area", headers=cab).json()
    assert area["participacoes"] == [] and area["notificacoes_nao_lidas"] == 0
    assert _notificacoes(cliente, cab) == []
    with session_scope() as db:
        assert db.scalar(select(Notificacao).where(Notificacao.event_id == event_id)) is not None
    # Fora da lista de cadastro pelo QR Code.
    assert event_id not in [e["id"] for e in cliente.get("/api/autocadastro/eventos").json()]

    # Desmarcar volta tudo como estava.
    cliente.patch(f"/api/events/{event_id}", json={"evento_teste": False}, headers=auth)
    assert len(_notificacoes(cliente, cab)) == 1
    assert len(cliente.get("/api/minha-area", headers=cab).json()["participacoes"]) == 1
