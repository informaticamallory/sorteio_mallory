"""Foto da entrega tirada depois (Central de Entregas): registro, troca e LGPD."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.models import AuditLog, Event
from apoio import autocadastrar, cabecalho, configurar_evento, conta, imagem
from conftest import montar_evento


def _sortear(cliente, auth, event_id, unidade, chave):
    resposta = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidade, "idempotency_key": f"foto-entrega-{chave}"},
        headers=auth,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["id"]


def _enviar_imagem(cliente, cab) -> str:
    envio = cliente.post("/api/uploads/imagem", files={"arquivo": ("foto.png", imagem(), "image/png")}, headers=cab)
    assert envio.status_code == 200, envio.text
    return envio.json()["url"]


def _foto(cliente, cab, event_id, draw_id, url):
    return cliente.post(f"/api/events/{event_id}/recepcao/entregas/{draw_id}/foto", json={"foto_url": url}, headers=cab)


def _premio_na_busca(cliente, cab, event_id, draw_id) -> dict:
    achados = cliente.get(
        f"/api/events/{event_id}/recepcao/busca", params={"q": "00001", "somente_ganhadores": True}, headers=cab
    ).json()
    return next(p for c in achados for p in c["premios"] if p["sorteio_id"] == draw_id)


def _evento(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1, quantidade_premio=1)
    return event_id, participantes[0], _sortear(cliente, auth, event_id, unidades[0], event_id)


def test_foto_depois_da_entrega_fica_registrada_e_pode_ser_trocada(cliente, auth):
    event_id, _pid, draw_id = _evento(cliente, auth)
    balcao = cabecalho(conta("ENTREGAS", login="balcao-foto-depois"))
    primeira = _enviar_imagem(cliente, balcao)

    # Antes da entrega nao ha o que fotografar; link externo nunca e aceito.
    assert _foto(cliente, balcao, event_id, draw_id, primeira).status_code == 409
    url_entrega = f"/api/events/{event_id}/sorteios/{draw_id}/entrega"
    assert cliente.post(url_entrega, json={"entregue": True}, headers=balcao).status_code == 200
    assert _foto(cliente, balcao, event_id, draw_id, "https://x.com/a.jpg").status_code == 422
    # Sorteador nao confirma entregas: tambem nao fotografa.
    sorteador = cabecalho(conta("SORTEIO", login="sorteador-foto"))
    assert _foto(cliente, sorteador, event_id, draw_id, primeira).status_code == 403

    resposta = _foto(cliente, balcao, event_id, draw_id, primeira)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["foto_url"] == primeira and resposta.json()["foto_por"]
    premio = _premio_na_busca(cliente, balcao, event_id, draw_id)
    assert premio["foto_entrega_url"] == primeira and premio["foto_entrega_por"]
    lista = cliente.get(
        f"/api/events/{event_id}/recepcao/premiados", params={"situacao": "entregues"}, headers=balcao
    ).json()["itens"]
    assert [i["tem_foto_entrega"] for i in lista] == [True]

    # Trocar: vale a nova, a anterior continua na auditoria.
    segunda = _enviar_imagem(cliente, balcao)
    assert _foto(cliente, balcao, event_id, draw_id, segunda).status_code == 200
    assert _premio_na_busca(cliente, balcao, event_id, draw_id)["foto_entrega_url"] == segunda
    with session_scope() as db:
        registros = db.scalars(
            select(AuditLog).where(AuditLog.event_id == event_id, AuditLog.acao == "entrega_foto").order_by(AuditLog.id)
        ).all()
        assert [r.detalhes["foto_url"] for r in registros] == [primeira, segunda]
        assert registros[1].detalhes["foto_anterior"] == primeira

    # Desfazer a entrega: sem foto atual (o historico continua com ela).
    assert cliente.post(
        url_entrega, json={"entregue": False, "motivo": "Entregue para a pessoa errada"}, headers=auth
    ).status_code == 200
    assert _premio_na_busca(cliente, balcao, event_id, draw_id)["foto_entrega_url"] is None
    assert _foto(cliente, balcao, event_id, draw_id, segunda).status_code == 409


def test_foto_tirada_no_balcao_aparece_na_central_mas_nao_no_portal(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1, quantidade_premio=1)
    configurar_evento(event_id)
    cadastro = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    draw_id = _sortear(cliente, auth, event_id, unidades[0], f"portal-{event_id}")
    foto = _enviar_imagem(cliente, auth)
    entregar = cliente.post(
        f"/api/events/{event_id}/recepcao/entregar", json={"sorteios": [draw_id], "foto_url": foto}, headers=auth
    )
    assert entregar.status_code == 200, entregar.text

    assert _premio_na_busca(cliente, auth, event_id, draw_id)["foto_entrega_url"] == foto
    portal = cliente.get("/api/minha-area", headers={"Authorization": f"Bearer {cadastro['access_token']}"})
    assert portal.status_code == 200 and foto not in portal.text


def test_excluir_evento_de_teste_apaga_os_arquivos_das_fotos(cliente, auth):
    event_id, _pid, draw_id = _evento(cliente, auth)
    with session_scope() as db:
        evento = db.get(Event, event_id)
        evento.evento_teste = True
        nome = evento.nome
    assert cliente.post(
        f"/api/events/{event_id}/sorteios/{draw_id}/entrega", json={"entregue": True}, headers=auth
    ).status_code == 200
    foto = _enviar_imagem(cliente, auth)
    assert _foto(cliente, auth, event_id, draw_id, foto).status_code == 200
    arquivo = Path(settings.upload_dir) / Path(foto).name
    assert arquivo.exists()

    apagar = cliente.request(
        "DELETE", f"/api/events/{event_id}", json={"nome_confirmacao": nome, "apagar_sorteios": True}, headers=auth
    )
    assert apagar.status_code == 204, apagar.text
    assert not arquivo.exists()
