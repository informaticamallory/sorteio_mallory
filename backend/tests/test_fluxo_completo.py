"""Fase 8: o fluxo completo do evento, de ponta a ponta, so pela API.

Cada passo usa a conta do perfil que o executa na vida real (admin,
colaborador, sorteador, organizador). Os dados sao ficticios e vivem no banco
temporario dos testes, isolado do banco real.
"""

from __future__ import annotations

import io
import time
from datetime import timedelta

from openpyxl import load_workbook
from sqlalchemy import select, update

from app.database import session_scope
from app.models import AuditLog, DisplayState, Event, Notificacao, utcnow
from apoio import cabecalho, concluir, conta, cpf_valido, imagem

PESSOAS = [
    ("Ana Ribeiro", "000101", "Financeiro"),
    ("Bruno Lima", "000102", "Logística"),
    ("Carla Souza", "000103", "TI"),
    ("Diego Alves", "000104", "Comercial"),
]


def _ok(resposta, codigo: int = 200):
    assert resposta.status_code == codigo, resposta.text
    return resposta.json() if resposta.content and resposta.headers.get("content-type", "").startswith("application/json") else resposta


def _revelar(event_id: int) -> None:
    """Fim da animacao do telao (sem esperar o tempo real)."""
    with session_scope() as db:
        ds = db.get(DisplayState, event_id)
        if ds.revelar_em is not None:
            ds.revelar_em = utcnow() - timedelta(milliseconds=1)
        db.execute(update(Notificacao).values(disponivel_em=utcnow() - timedelta(milliseconds=1)))


def test_fluxo_completo_do_evento(cliente, auth):
    admin = auth
    operador = cabecalho(conta("SORTEIO", login="operador"))
    organizador = cabecalho(conta("ORGANIZADOR", login="org.evento"))

    # 1. O administrador configura o evento.
    evento = _ok(cliente.post("/api/events", json={"nome": "Confraternização Teste", "empresa_nome": "Mallory"}, headers=admin), 201)
    eid = evento["id"]
    E = f"/api/events/{eid}"
    _ok(cliente.patch(E, json={
        "autocadastro_ativo": True, "autocadastro_confirma_presenca": True,
        "recepcao_publica_ativa": True,  # abre o check-in sem login
        "carrossel_segundos": 5, "duracao_animacao_ms": 1000,
    }, headers=admin))
    _ok(cliente.patch(f"{E}/regras", json={"exige_presenca": True, "permite_multiplas_vitorias": False}, headers=admin))
    _ok(cliente.post(f"{E}/regras/confirmar", headers=admin))
    ids = {}
    for nome, matricula, setor in PESSOAS:
        ids[matricula] = _ok(cliente.post(f"{E}/participantes", json={"nome": nome, "matricula": matricula, "setor": setor}, headers=admin), 201)["id"]
    _ok(cliente.post(f"{E}/premios", json={"nome": 'Smart TV 50"', "quantidade": 1, "ordem": 1}, headers=admin), 201)
    _ok(cliente.post(f"{E}/premios", json={"nome": "Fone Bluetooth", "quantidade": 1, "ordem": 2}, headers=admin), 201)

    # 2. Os premios sao distribuidos em blocos.
    blocos = _ok(cliente.post(f"{E}/blocos/distribuir", json={"capacidade": 2}, headers=admin))["blocos"]
    assert len(blocos) == 1 and blocos[0]["total"] == 2
    bloco_id = blocos[0]["id"]

    # 3. A planilha com CPF e nascimento completa a identificacao de todos.
    planilha_csv = "nome;matricula;setor;data_nascimento;cpf\r\n" + "".join(
        f"{nome};{matricula};{setor};15/03/1990;{cpf_valido(500_000_000 + i)}\r\n"
        for i, (nome, matricula, setor) in enumerate(PESSOAS)
    )
    previa = _ok(cliente.post(
        f"{E}/participantes/importar/previa",
        files={"arquivo": ("colaboradores.csv", planilha_csv.encode("utf-8"), "text/csv")},
        headers=admin,
    ))
    assert previa["com_identificacao"] == len(PESSOAS) and previa["com_erro"] == 0
    assert "cpf" not in str(previa["linhas"][0]).lower().replace("codigo_cpf", "")
    importado = _ok(cliente.post(
        f"{E}/participantes/importar/confirmar",
        json={"linhas": previa["linhas"], "atualizar_identificacao": True},
        headers=admin,
    ))
    assert importado["identificacoes_atualizadas"] == len(PESSOAS)

    # 4 a 7. Cada colaborador se cadastra pelo QR Code (matricula, nascimento,
    # 5 digitos do CPF, foto e senha); a Recepcao faz o check-in e o admin
    # registra a pulseira (pulseira e so do admin).
    tokens = {}
    for indice, (nome, matricula, _setor) in enumerate(PESSOAS):
        cpf = cpf_valido(500_000_000 + indice)
        identificado = _ok(cliente.post(
            f"/api/autocadastro/{eid}/identificar",
            json={"matricula": matricula, "nascimento": "1990-03-15", "cpf5": cpf[:5]},
        ))
        assert identificado["nome"] == nome
        resultado = _ok(concluir(
            cliente, eid, matricula, passe=identificado["passe"], cpf5=cpf[:5], foto=imagem()
        ))
        assert resultado["cartao"]["numero_sorteio"] is not None
        assert resultado["cartao"]["presente"] is False  # cadastro nao e check-in
        tokens[matricula] = {"Authorization": f"Bearer {resultado['access_token']}"}
        _ok(cliente.post(f"/api/recepcao/{eid}/checkin", json={"participante_id": ids[matricula]}))
        _ok(cliente.post(
            f"{E}/credenciamento/participantes/{ids[matricula]}/pulseira",
            json={"pulseira": f"MAL-{indice + 1:03d}"},
            headers=admin,
        ))
    resumo = _ok(cliente.get(f"{E}/credenciamento/resumo", headers=organizador))
    assert resumo["presentes"] == resumo["com_pulseira"] == resumo["com_conta"] == len(PESSOAS)

    # 8. O operador inicia o bloco.
    _ok(cliente.post(f"{E}/blocos/{bloco_id}/iniciar", headers=operador))

    # 9. O backend sorteia (duas rodadas, uma por unidade do bloco).
    detalhe = _ok(cliente.get(f"{E}/blocos/{bloco_id}", headers=operador))
    sorteios = []
    for i, unidade in enumerate(detalhe["unidades"]):
        if i:
            _revelar(eid)
        sorteios.append(_ok(cliente.post(f"{E}/sorteio", json={"prize_unit_id": unidade["id"], "idempotency_key": f"fluxo-completo-{i}"}, headers=operador)))
    ganhadores = {s["ganhador_matricula"] for s in sorteios}
    assert len(ganhadores) == 2  # cada pessoa ganha uma vez

    # 10. Antes da revelacao o ganhador ainda nao ve nada; depois, ve a notificacao.
    primeiro = sorteios[0]
    tok_ganhador = tokens[primeiro["ganhador_matricula"]]
    _revelar(eid)
    notificacoes = _ok(cliente.get("/api/minha-area/notificacoes", headers=tok_ganhador))
    assert any(n["sorteio_id"] == primeiro["id"] and n["situacao"] == "aguardando_retirada" for n in notificacoes)
    perdedor = next(m for m in tokens if m not in ganhadores)
    assert _ok(cliente.get("/api/minha-area/notificacoes", headers=tokens[perdedor])) == []

    # 11. O telao publico apresenta o resultado (sem matricula nem pulseira).
    with session_scope() as db:
        telao_token = db.get(Event, eid).telao_token
    estado = _ok(cliente.get(f"/api/public/{telao_token}/estado"))
    assert estado["estado"] == "resultado"
    assert estado["ganhador"]["nome"] == sorteios[-1]["ganhador_nome"]
    assert "matricula" not in str(estado["ganhador"])

    # 12. O operador finaliza o bloco e o carrossel comeca no telao.
    _ok(cliente.post(f"{E}/blocos/{bloco_id}/finalizar", json={}, headers=operador))
    estado = _ok(cliente.get(f"/api/public/{telao_token}/estado"))
    assert estado["estado"] == "carrossel_ganhadores"
    assert {s["ganhador_nome"] for s in estado["carrossel"]["slides"]} == {s["ganhador_nome"] for s in sorteios}

    # 13. O organizador localiza o ganhador pela pulseira.
    pulseira = f"MAL-{[m for _n, m, _s in PESSOAS].index(primeiro['ganhador_matricula']) + 1:03d}"
    busca = _ok(cliente.get(f"{E}/recepcao/busca", params={"q": pulseira}, headers=organizador))
    assert busca[0]["premios"][0]["sorteio_id"] == primeiro["id"]

    # 14. O organizador confere a pulseira e confirma a entrega.
    errada = cliente.post(f"{E}/sorteios/{primeiro['id']}/entrega", json={"entregue": True, "pulseira_conferida": "MAL-999"}, headers=organizador)
    assert errada.status_code == 409
    _ok(cliente.post(f"{E}/sorteios/{primeiro['id']}/entrega", json={"entregue": True, "pulseira_conferida": pulseira}, headers=organizador))

    # 15. O colaborador ve a situacao atualizada.
    area = _ok(cliente.get("/api/minha-area", headers=tok_ganhador))
    assert area["participacoes"][0]["premios"][0]["entregue"] is True
    notificacoes = _ok(cliente.get("/api/minha-area/notificacoes", headers=tok_ganhador))
    assert next(n for n in notificacoes if n["sorteio_id"] == primeiro["id"])["situacao"] == "entregue"

    # 16. O historico registra tudo e exporta.
    historico = _ok(cliente.get("/api/sorteios", params={"event_id": eid}, headers=admin))
    assert historico["total"] == 2
    entregue = next(i for i in historico["itens"] if i["id"] == primeiro["id"])
    assert entregue["entregue"] is True and entregue["entregue_por"] == "Conta Organizador"
    with session_scope() as db:
        acoes = set(db.scalars(select(AuditLog.acao).where(AuditLog.event_id == eid)).all())
    assert {
        "evento_criado", "regras_confirmadas", "autocadastro_concluido",
        "pulseira_atribuida", "bloco_iniciado", "sorteio_realizado", "bloco_finalizado",
        "carrossel_iniciado", "entrega_registrada",
    } <= acoes, acoes
    csv = cliente.get("/api/sorteios/export.csv", params={"event_id": eid}, headers=admin)
    assert csv.status_code == 200 and pulseira in csv.content.decode("utf-8-sig")
    xlsx = cliente.get("/api/sorteios/export.xlsx", params={"event_id": eid}, headers=admin)
    planilha = load_workbook(io.BytesIO(xlsx.content)).active
    assert planilha.max_row == 3  # cabecalho + 2 resultados

    # A apresentacao nao iniciou o proximo bloco nem sorteou nada sozinha.
    time.sleep(0.01)
    assert _ok(cliente.get("/api/sorteios", params={"event_id": eid}, headers=admin))["total"] == 2
