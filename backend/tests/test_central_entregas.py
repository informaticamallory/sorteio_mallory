"""Central de Entregas e perfis (Administrador, Organizador - RH, Equipe de Entregas)."""

from __future__ import annotations

import threading

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, Draw, Participant, User
from app.services.erros import RegraDeNegocio
from app.services.sorteio import registrar_entrega
from apoio import autocadastrar, cabecalho, configurar_evento, conta
from conftest import montar_evento


def _sortear(cliente, auth, event_id, unidade, chave):
    resposta = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidade, "idempotency_key": f"central-{chave}"},
        headers=auth,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _entrega(cliente, cab, event_id, draw_id, **corpo):
    return cliente.post(f"/api/events/{event_id}/sorteios/{draw_id}/entrega", json={"entregue": True, **corpo}, headers=cab)


def _resumo(cliente, cab, event_id):
    return cliente.get(f"/api/events/{event_id}/recepcao/resumo", headers=cab).json()


def _evento_com_ganhador(cliente, auth, unidades=2):
    """Um unico participante presente ganha todas as unidades."""
    event_id, participantes, ids_unidades = montar_evento(
        participantes=1, quantidade_premio=unidades, permite_multiplas_vitorias=True
    )
    sorteios = [_sortear(cliente, auth, event_id, u, f"{event_id}-{i}") for i, u in enumerate(ids_unidades)]
    return event_id, participantes[0], sorteios


# ------------------------------------------------------------------ perfis
def test_equipe_de_entregas_entrega_mas_nao_desfaz_nem_sorteia(cliente, auth):
    event_id, _pid, sorteios = _evento_com_ganhador(cliente, auth)
    entregas = cabecalho(conta("ENTREGAS", login="balcao"))
    assert _entrega(cliente, entregas, event_id, sorteios[0]["id"]).status_code == 200
    desfazer = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteios[0]['id']}/entrega",
        json={"entregue": False, "motivo": "Entregue para a pessoa errada"},
        headers=entregas,
    )
    assert desfazer.status_code == 403
    assert cliente.get(f"/api/events/{event_id}/blocos", headers=entregas).status_code == 403
    assert cliente.get("/api/usuarios", headers=entregas).status_code == 403
    me = cliente.get("/api/auth/me", headers=entregas).json()
    assert "confirmar_entrega" in me["permissoes"] and "desfazer_entrega" not in me["permissoes"]


def test_rh_desfaz_com_justificativa_e_o_historico_fica(cliente, auth):
    event_id, _pid, sorteios = _evento_com_ganhador(cliente, auth, unidades=1)
    rh = cabecalho(conta("ORGANIZADOR", login="rh"))
    draw = sorteios[0]["id"]
    assert _entrega(cliente, rh, event_id, draw).status_code == 200
    url = f"/api/events/{event_id}/sorteios/{draw}/entrega"
    assert cliente.post(url, json={"entregue": False}, headers=rh).status_code == 422  # sem justificativa
    assert cliente.post(url, json={"entregue": False, "motivo": "abc"}, headers=rh).status_code == 422
    ok = cliente.post(url, json={"entregue": False, "motivo": "Prêmio com defeito, troca"}, headers=rh)
    assert ok.status_code == 200 and ok.json()["entregue"] is False
    # Desfazer de novo: nao ha entrega.
    assert cliente.post(url, json={"entregue": False, "motivo": "De novo por engano"}, headers=rh).status_code == 409

    with session_scope() as db:
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "entrega_revertida"))
        assert registro.detalhes["motivo"] == "Prêmio com defeito, troca"
        assert registro.detalhes["entrega_original"]["entregue_em"]
        assert registro.detalhes["estado"] == {"antes": "entregue", "depois": "pendente"}
        # O registro da entrega original continua la.
        assert db.scalar(select(AuditLog).where(AuditLog.acao == "entrega_registrada")) is not None

    historico = cliente.get(f"/api/events/{event_id}/recepcao/historico", headers=rh).json()
    assert historico["total"] == 2
    desfeita = next(i for i in historico["itens"] if i["acao"] == "entrega_revertida")
    assert desfeita["motivo"] == "Prêmio com defeito, troca" and desfeita["situacao_atual"] == "pendente"


def test_rh_so_sorteia_quando_autorizado_e_usuarios_tem_setor(cliente, auth):
    event_id, _participantes, unidades = montar_evento(participantes=2)
    criado = cliente.post(
        "/api/usuarios", json={"usuario": "ana.rh", "nome": "Ana RH", "papel": "ORGANIZADOR", "setor": "RH"}, headers=auth
    ).json()
    user_id = criado["usuario"]["id"]
    assert criado["usuario"]["setor"] == "RH" and criado["usuario"]["pode_sortear"] is False
    with session_scope() as db:
        db.get(User, user_id).deve_trocar_senha = False
    rh = cabecalho(user_id)
    corpo = {"prize_unit_id": unidades[0], "idempotency_key": "rh-autorizado-1"}
    assert cliente.post(f"/api/events/{event_id}/sorteio", json=corpo, headers=rh).status_code == 403

    alterado = cliente.patch(f"/api/usuarios/{user_id}", json={"pode_sortear": True}, headers=auth)
    assert alterado.status_code == 200 and alterado.json()["pode_sortear"] is True
    rh = cabecalho(user_id)  # sessao renovada (permissoes mudaram)
    assert cliente.post(f"/api/events/{event_id}/sorteio", json=corpo, headers=rh).status_code == 200

    # Autorizacao so para Organizador - RH; mudar de perfil a retira.
    sorteador = conta("SORTEIO", login="sorteador.x")
    assert cliente.patch(f"/api/usuarios/{sorteador}", json={"pode_sortear": True}, headers=auth).status_code == 422
    mudou = cliente.patch(f"/api/usuarios/{user_id}", json={"papel": "ENTREGAS"}, headers=auth).json()
    assert mudou["pode_sortear"] is False
    with session_scope() as db:
        acoes = [a.detalhes.get("mudancas", {}) for a in db.scalars(select(AuditLog).where(AuditLog.acao == "usuario_alterado"))]
    assert any("pode_sortear" in m for m in acoes)


def test_admin_promove_colaborador_a_rh_com_senha_temporaria_e_mantem_o_cartao(cliente, auth):
    from apoio import senha_de

    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    colaborador = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    user_id = colaborador["usuario"]["id"]
    antigo = {"Authorization": f"Bearer {colaborador['access_token']}"}

    promovido = cliente.patch(f"/api/usuarios/{user_id}", json={"papel": "ORGANIZADOR", "setor": "RH"}, headers=auth)
    assert promovido.status_code == 200, promovido.text
    corpo = promovido.json()
    assert corpo["papel"] == "ORGANIZADOR" and corpo["setor"] == "RH" and corpo["deve_trocar_senha"] is True
    temporaria = corpo["senha_temporaria"]
    assert temporaria and len(temporaria) >= 12

    # Sessao antiga encerrada; a senha fraca (5 digitos do CPF) deixa de valer.
    assert cliente.get("/api/auth/me", headers=antigo).status_code == 401
    assert cliente.post("/api/auth/login", json={"usuario": "00001", "senha": senha_de(participantes[0])}).status_code == 401
    login = cliente.post("/api/auth/login", json={"usuario": "00001", "senha": temporaria})
    assert login.status_code == 200 and login.json()["usuario"]["deve_trocar_senha"] is True
    token = login.json()["access_token"]
    trocada = cliente.post(
        "/api/auth/trocar-senha",
        json={"senha_atual": temporaria, "senha_nova": "RhForte2026x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert trocada.status_code == 200, trocada.text
    cab = {"Authorization": f"Bearer {trocada.json()['access_token']}"}
    me = cliente.get("/api/auth/me", headers=cab).json()
    assert me["tem_cartao"] is True and "configurar_blocos" in me["permissoes"]
    # Continua participante: ve o proprio cartao.
    area = cliente.get("/api/minha-area", headers=cab).json()
    assert area["participacoes"][0]["matricula"] == "00001"
    # E opera como RH.
    assert cliente.get(f"/api/events/{event_id}/blocos", headers=cab).status_code == 200

    # Equipe nao volta a ser colaborador; editar de novo nao gera outra senha.
    assert cliente.patch(f"/api/usuarios/{user_id}", json={"papel": "COLABORADOR"}, headers=auth).status_code == 409
    sorteador = cliente.patch(f"/api/usuarios/{user_id}", json={"papel": "SORTEIO"}, headers=auth).json()
    assert sorteador["papel"] == "SORTEIO" and sorteador["senha_temporaria"] is None
    with session_scope() as db:
        registro = db.scalars(select(AuditLog).where(AuditLog.acao == "usuario_alterado")).first()
        assert registro.detalhes["mudancas"]["papel"] == ["COLABORADOR", "ORGANIZADOR"]
        assert "senha" in registro.detalhes["mudancas"] and temporaria not in str(registro.detalhes)


# ------------------------------------------------------------------ confirmacao
def test_entrega_duplicada_e_bloqueada(cliente, auth):
    event_id, _pid, sorteios = _evento_com_ganhador(cliente, auth, unidades=1)
    draw = sorteios[0]["id"]
    assert _entrega(cliente, auth, event_id, draw).status_code == 200
    segunda = _entrega(cliente, auth, event_id, draw)
    assert segunda.status_code == 409 and "já foi entregue" in segunda.json()["detail"]
    with session_scope() as db:
        assert len(db.scalars(select(AuditLog).where(AuditLog.acao == "entrega_registrada")).all()) == 1


def test_dois_atendentes_ao_mesmo_tempo_so_um_entrega(cliente, auth):
    event_id, _pid, sorteios = _evento_com_ganhador(cliente, auth, unidades=1)
    draw = sorteios[0]["id"]
    atendentes = [conta("ENTREGAS", login=f"balcao{i}") for i in range(2)]
    resultados: list[str] = []
    barreira = threading.Barrier(2)

    def tentar(user_id: int) -> None:
        barreira.wait()
        try:
            with session_scope() as db:
                registrar_entrega(db, db.get(Draw, draw), True, db.get(User, user_id))
            resultados.append("ok")
        except RegraDeNegocio:
            resultados.append("recusado")

    threads = [threading.Thread(target=tentar, args=(u,)) for u in atendentes]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(resultados) == ["ok", "recusado"]


def test_lote_do_mesmo_ganhador_tudo_ou_nada(cliente, auth):
    event_id, pid, sorteios = _evento_com_ganhador(cliente, auth, unidades=3)
    ids = [s["id"] for s in sorteios]
    url = f"/api/events/{event_id}/recepcao/entregar"
    # Uma ja entregue: o lote inteiro e recusado.
    assert _entrega(cliente, auth, event_id, ids[2]).status_code == 200
    recusado = cliente.post(url, json={"sorteios": ids}, headers=auth)
    assert recusado.status_code == 409
    with session_scope() as db:
        assert [db.get(Draw, i).entregue for i in ids] == [False, False, True]
    ok = cliente.post(url, json={"sorteios": ids[:2]}, headers=auth)
    assert ok.status_code == 200 and ok.json() == {"sorteados": 3, "entregues": 3, "pendentes": 0, "percentual": 100}
    with session_scope() as db:
        assert len(db.scalars(select(AuditLog).where(AuditLog.acao == "entrega_registrada")).all()) == 3


def test_foto_opcional_da_entrega_fica_no_historico(cliente, auth):
    from apoio import imagem

    event_id, _pid, sorteios = _evento_com_ganhador(cliente, auth, unidades=2)
    balcao = cabecalho(conta("ENTREGAS", login="balcao-foto"))
    url = f"/api/events/{event_id}/recepcao/entregar"

    # A equipe do balcao consegue enviar a foto (e so imagem valida).
    envio = cliente.post("/api/uploads/imagem", files={"arquivo": ("foto.png", imagem(), "image/png")}, headers=balcao)
    assert envio.status_code == 200, envio.text
    foto = envio.json()["url"]
    # Link externo nao e aceito como foto.
    externo = cliente.post(url, json={"sorteios": [sorteios[0]["id"]], "foto_url": "https://x.com/a.jpg"}, headers=balcao)
    assert externo.status_code == 422

    assert cliente.post(url, json={"sorteios": [sorteios[0]["id"]], "foto_url": foto}, headers=balcao).status_code == 200
    # Sem foto continua funcionando (ela e opcional).
    assert cliente.post(url, json={"sorteios": [sorteios[1]["id"]]}, headers=balcao).status_code == 200

    historico = cliente.get(f"/api/events/{event_id}/recepcao/historico", headers=auth).json()["itens"]
    fotos = {h["sorteio_id"]: h["foto_url"] for h in historico if h["acao"] == "entrega_registrada"}
    assert fotos == {sorteios[0]["id"]: foto, sorteios[1]["id"]: None}


def test_lote_de_ganhadores_diferentes_ou_anulado_e_recusado(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=2, quantidade_premio=2)
    s1 = _sortear(cliente, auth, event_id, unidades[0], "dif-1")
    s2 = _sortear(cliente, auth, event_id, unidades[1], "dif-2")
    url = f"/api/events/{event_id}/recepcao/entregar"
    assert cliente.post(url, json={"sorteios": [s1["id"], s2["id"]]}, headers=auth).status_code == 422
    cliente.post(
        f"/api/events/{event_id}/sorteios/{s1['id']}/anular",
        json={"motivo": "Ganhador ausente no palco", "tipo": "erro_operacional"},
        headers=auth,
    )
    assert cliente.post(url, json={"sorteios": [s1["id"]]}, headers=auth).status_code == 409
    # Anulado nao conta como pendencia.
    resumo = _resumo(cliente, auth, event_id)
    assert resumo["sorteados"] == resumo["pendentes"] + resumo["entregues"]
    assert all(i["sorteio_id"] != s1["id"] for i in cliente.get(f"/api/events/{event_id}/recepcao/premiados", headers=auth).json()["itens"])


# ------------------------------------------------------------------ busca e filtros
def test_busca_por_nome_matricula_pulseira_numero_e_qr_isolada_por_evento(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=3)
    outro_evento, outros, _ = montar_evento(participantes=3)
    _sortear(cliente, auth, event_id, unidades[0], "busca-1")
    with session_scope() as db:
        p = db.get(Participant, participantes[1])
        p.nome = "José da Conceição"
        p.pulseira = "MAL-077"
        numero = p.numero_sorteio
        numero_outro = db.get(Participant, outros[0]).numero_sorteio
    url = f"/api/events/{event_id}/recepcao/busca"

    def ids(q):
        resposta = cliente.get(url, params={"q": q}, headers=auth)
        assert resposta.status_code == 200, resposta.text
        return [c["id"] for c in resposta.json()]

    assert ids("jose conceicao") == [participantes[1]]  # sem acento, todas as palavras
    assert participantes[1] in ids("002")  # matricula 00002 sem os zeros
    assert ids("mal-077") == [participantes[1]]
    assert ids(str(numero)) == [participantes[1]]
    assert ids(f"MALLORY-SORTE:{event_id}:{numero}") == [participantes[1]]
    # QR de outro evento nao mistura eventos.
    assert cliente.get(url, params={"q": f"MALLORY-SORTE:{outro_evento}:{numero_outro}"}, headers=auth).status_code == 404
    assert outros[0] not in ids(str(numero_outro))


def test_lista_de_premiados_com_filtros_combinados(cliente, auth):
    event_id, pid, sorteios = _evento_com_ganhador(cliente, auth, unidades=3)
    rh_id = conta("ORGANIZADOR", login="rh.filtro")
    rh = cabecalho(rh_id)
    _entrega(cliente, rh, event_id, sorteios[0]["id"])
    url = f"/api/events/{event_id}/recepcao/premiados"
    pendentes = cliente.get(url, headers=auth).json()  # padrao: pendentes
    assert pendentes["total"] == 2
    entregues = cliente.get(url, params={"situacao": "entregues", "operador_id": rh_id}, headers=auth).json()
    assert [i["sorteio_id"] for i in entregues["itens"]] == [sorteios[0]["id"]]
    assert entregues["itens"][0]["entregue_por"] == "Conta Organizador"
    from datetime import date

    hoje = date.today().isoformat()
    todos_hoje = cliente.get(url, params={"situacao": "todos", "de": hoje, "ate": hoje}, headers=auth).json()
    assert todos_hoje["total"] == 3
    nenhum = cliente.get(url, params={"situacao": "todos", "de": "2001-01-01", "ate": "2001-01-02"}, headers=auth).json()
    assert nenhum["total"] == 0
    paginado = cliente.get(url, params={"situacao": "todos", "por_pagina": 2, "pagina": 2}, headers=auth).json()
    assert paginado["paginas"] == 2 and len(paginado["itens"]) == 1
    filtros = cliente.get(f"/api/events/{event_id}/recepcao/filtros", headers=auth).json()
    assert [o["nome"] for o in filtros["operadores"]] == ["Conta Organizador"]
    assert filtros["premios"][0]["nome"] == "Premio Teste"


def test_historico_exporta_csv_so_para_perfil_autorizado(cliente, auth):
    event_id, _pid, sorteios = _evento_com_ganhador(cliente, auth, unidades=1)
    _entrega(cliente, auth, event_id, sorteios[0]["id"])
    csv = cliente.get(f"/api/events/{event_id}/recepcao/historico/export.csv", headers=auth)
    assert csv.status_code == 200
    texto = csv.content.decode("utf-8-sig")
    assert "Entrega confirmada" in texto and "00001" in texto
    entregas = cabecalho(conta("ENTREGAS", login="balcao.csv"))
    assert cliente.get(f"/api/events/{event_id}/recepcao/historico/export.csv", headers=entregas).status_code == 403


def test_registro_antigo_nao_empresta_o_ganhador_de_resultado_com_id_reaproveitado(cliente, auth):
    """Registro de entrega antigo (so com sorteio_id) cujo resultado foi apagado
    na limpeza da demonstracao: o id reaproveitado nao pode virar outro ganhador."""
    from datetime import timedelta

    from app.models import utcnow

    event_id, participantes, unidades = montar_evento(participantes=1)
    with session_scope() as db:
        db.add(
            AuditLog(
                event_id=event_id,
                usuario_id=None,
                acao="entrega_registrada",
                detalhes={"sorteio_id": 1},
                criado_em=utcnow() - timedelta(days=5),
            )
        )
    sorteio = _sortear(cliente, auth, event_id, unidades[0], "id-reaproveitado")
    assert sorteio["id"] == 1  # mesmo id do registro antigo
    itens = cliente.get(f"/api/events/{event_id}/recepcao/historico", headers=auth).json()["itens"]
    antigo = next(i for i in itens if i["sorteio_id"] == 1)
    assert antigo["participante"] is None and antigo["matricula"] is None and antigo["situacao_atual"] is None
    assert all(a["participante"] is None for a in cliente.get(f"/api/events/{event_id}/recepcao/atendimentos", headers=auth).json())


# ------------------------------------------------------------------ portal do colaborador
def test_entrega_e_desfazimento_aparecem_no_portal(cliente, auth):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[0], '00001')['access_token']}"}
    sorteio = _sortear(cliente, auth, event_id, unidades[0], "portal-1")
    with session_scope() as db:
        from app.models import Notificacao, utcnow
        from datetime import timedelta
        from sqlalchemy import update

        db.execute(update(Notificacao).values(disponivel_em=utcnow() - timedelta(seconds=1)))
    _entrega(cliente, auth, event_id, sorteio["id"])
    premio = cliente.get("/api/minha-area", headers=cab).json()["participacoes"][0]["premios"][0]
    assert premio["entregue"] is True
    cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/entrega",
        json={"entregue": False, "motivo": "Retirada registrada por engano"},
        headers=auth,
    )
    premio = cliente.get("/api/minha-area", headers=cab).json()["participacoes"][0]["premios"][0]
    assert premio["entregue"] is False
    # QR Code do cartao: so para o proprio colaborador.
    qr = cliente.get(f"/api/minha-area/{event_id}/qrcode.png", headers=cab)
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/png"
