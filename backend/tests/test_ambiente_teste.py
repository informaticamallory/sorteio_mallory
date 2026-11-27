"""Ambiente de teste: copia anonimizada do evento e "Recomecar teste"."""
from __future__ import annotations

from sqlalchemy import func, select

from app.database import session_scope
from app.models import BlocoSorteio, Draw, Event, Notificacao, Participant, Prize, PrizeUnit
from apoio import autocadastrar, cabecalho, configurar_evento, conta
from conftest import montar_evento


def _api(event_id: int, caminho: str) -> str:
    return f"/api/events/{event_id}{caminho}"


def _evento_real_com_sorteio(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=4, quantidade_premio=3)
    configurar_evento(event_id)
    # Um colaborador com conta (cadastro pelo QR Code): a conta nao vai para a copia.
    autocadastrar(cliente, auth, event_id, participantes[0], "00001", pulseira="P-1")
    blocos = cliente.post(_api(event_id, "/blocos/distribuir"), json={"capacidade": 2}, headers=auth).json()["blocos"]
    cliente.post(_api(event_id, f"/blocos/{blocos[0]['id']}/iniciar"), headers=auth)
    sorteio = cliente.post(
        _api(event_id, "/sorteio"), json={"prize_unit_id": unidades[0], "idempotency_key": "real-ambiente-01"}, headers=auth
    )
    assert sorteio.status_code == 200, sorteio.text
    return event_id, blocos


def test_copia_de_teste_anonimizada_e_zerada_sem_mexer_no_real(cliente, auth):
    real_id, blocos_reais = _evento_real_com_sorteio(cliente, auth)

    rh = cabecalho(conta("ORGANIZADOR", login="rh-ambiente"))
    assert cliente.post(_api(real_id, "/ambiente-teste"), headers=rh).status_code == 403

    resposta = cliente.post(_api(real_id, "/ambiente-teste"), headers=auth)
    assert resposta.status_code == 201, resposta.text
    copia = resposta.json()
    assert copia["evento_teste"] is True and copia["nome"].startswith("TESTE — ")
    assert copia["autocadastro_ativo"] is False and copia["recepcao_publica_ativa"] is False

    with session_scope() as db:
        real = db.get(Event, real_id)
        nova = db.get(Event, copia["id"])
        assert nova.telao_token != real.telao_token
        assert nova.modo_sorteio == real.modo_sorteio and nova.tema_telao == real.tema_telao

        originais = db.scalars(select(Participant).where(Participant.event_id == real_id).order_by(Participant.id)).all()
        copiados = db.scalars(select(Participant).where(Participant.event_id == nova.id).order_by(Participant.id)).all()
        assert [p.matricula for p in copiados] == [p.matricula for p in originais]
        assert [p.nome for p in copiados] == [f"Participante {i:03d}" for i in range(1, len(originais) + 1)]
        # Nada de identificacao nem conta; todos presentes para sortear na hora.
        assert all(p.presente for p in copiados)
        assert all(p.usuario_id is None and p.cpf_hash is None and p.identificacao_hash is None for p in copiados)
        assert all(p.pulseira is None and p.foto_url is None for p in copiados)

        # Premios e blocos: mesma distribuicao, tudo disponivel e planejado.
        unidades = db.scalars(
            select(PrizeUnit).join(Prize).where(Prize.event_id == nova.id)
        ).all()
        assert len(unidades) == 3 and all(u.status == "disponivel" for u in unidades)
        blocos = db.scalars(select(BlocoSorteio).where(BlocoSorteio.event_id == nova.id)).all()
        assert len(blocos) == len(blocos_reais) and all(b.status == "PLANEJADO" for b in blocos)
        assert sum(1 for u in unidades if u.bloco_id is not None) == 3

        # Sem sorteios nem notificacoes na copia; o real continua com o seu.
        assert db.scalar(select(func.count(Draw.id)).where(Draw.event_id == nova.id)) == 0
        assert db.scalar(select(func.count(Notificacao.id)).where(Notificacao.event_id == nova.id)) == 0
        assert db.scalar(select(func.count(Draw.id)).where(Draw.event_id == real_id)) == 1
        assert real.evento_teste is False

    # Copia de uma copia nao existe.
    assert cliente.post(_api(copia["id"], "/ambiente-teste"), headers=auth).status_code == 409


def test_evento_de_teste_so_aparece_para_o_admin(cliente, auth):
    real_id, _blocos = _evento_real_com_sorteio(cliente, auth)
    copia_id = cliente.post(_api(real_id, "/ambiente-teste"), headers=auth).json()["id"]
    with session_scope() as db:
        db.get(Event, copia_id).recepcao_publica_ativa = True
        db.get(Event, real_id).recepcao_publica_ativa = True

    admin_ve = {e["id"] for e in cliente.get("/api/events", headers=auth).json()}
    assert {real_id, copia_id} <= admin_ve
    assert cliente.get(f"/api/events/{copia_id}", headers=auth).status_code == 200

    for papel in ("ORGANIZADOR", "RECEPCAO", "SORTEIO", "ENTREGAS"):
        equipe = cabecalho(conta(papel, login=f"so-real-{papel.lower()}"))
        ids = {e["id"] for e in cliente.get("/api/events", headers=equipe).json()}
        assert real_id in ids and copia_id not in ids, papel
        # Pelo numero do evento tambem nao entra (mesma resposta de inexistente).
        assert cliente.get(f"/api/events/{copia_id}", headers=equipe).status_code == 404, papel
        assert cliente.get(f"/api/events/{copia_id}/recepcao/resumo", headers=equipe).status_code in (403, 404), papel

    # Recepcao sem login: o teste nao aparece nem pelo numero.
    publicos = {e["id"] for e in cliente.get("/api/recepcao/eventos").json()}
    assert real_id in publicos and copia_id not in publicos
    assert cliente.post(f"/api/recepcao/{copia_id}/localizar", json={"matricula": "00001"}).status_code == 404


def test_sortear_na_copia_e_recomecar_do_zero(cliente, auth):
    real_id, _blocos = _evento_real_com_sorteio(cliente, auth)
    copia_id = cliente.post(_api(real_id, "/ambiente-teste"), headers=auth).json()["id"]

    blocos = cliente.get(_api(copia_id, "/blocos"), headers=auth).json()["blocos"]
    assert cliente.post(_api(copia_id, f"/blocos/{blocos[0]['id']}/iniciar"), headers=auth).status_code == 200
    with session_scope() as db:
        unidade = db.scalar(
            select(PrizeUnit.id).join(Prize).where(Prize.event_id == copia_id, PrizeUnit.bloco_id == blocos[0]["id"])
            .order_by(PrizeUnit.ordem_bloco).limit(1)
        )
    sorteio = cliente.post(
        _api(copia_id, "/sorteio"), json={"prize_unit_id": unidade, "idempotency_key": "copia-sorteio-01"}, headers=auth
    )
    assert sorteio.status_code == 200, sorteio.text
    assert sorteio.json()["ganhador_nome"].startswith("Participante ")

    # Recomecar so em evento de teste; nunca no real.
    assert cliente.post(_api(real_id, "/recomecar-teste"), headers=auth).status_code == 409
    rh = cabecalho(conta("ORGANIZADOR", login="rh-recomeca"))
    # Para o RH o evento de teste nem existe.
    assert cliente.post(_api(copia_id, "/recomecar-teste"), headers=rh).status_code == 404
    resposta = cliente.post(_api(copia_id, "/recomecar-teste"), headers=auth)
    assert resposta.status_code == 200 and resposta.json() == {"sorteios_apagados": 1}

    with session_scope() as db:
        assert db.scalar(select(func.count(Draw.id)).where(Draw.event_id == copia_id)) == 0
        assert db.scalar(select(func.count(Notificacao.id)).where(Notificacao.event_id == copia_id)) == 0
        unidades = db.scalars(select(PrizeUnit).join(Prize).where(Prize.event_id == copia_id)).all()
        assert all(u.status == "disponivel" for u in unidades)
        assert all(
            b.status == "PLANEJADO" for b in db.scalars(select(BlocoSorteio).where(BlocoSorteio.event_id == copia_id))
        )
        # O evento real nao foi tocado.
        assert db.scalar(select(func.count(Draw.id)).where(Draw.event_id == real_id)) == 1
    with session_scope() as db:
        token = db.get(Event, copia_id).telao_token
    assert cliente.get(f"/api/public/{token}/estado").json()["estado"] == "aguardando"
