"""Fase 4: controle de acesso por perfil, sessao, login e telas por perfil.

A matriz abaixo e a especificacao executavel de quem pode chamar cada rota.
Rota nova sem linha aqui faz o teste falhar: toda rota exige uma decisao
explicita de acesso.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.models import AuditLog, Draw, Participant, Prize, User, utcnow
from app.security import criar_token, hash_senha
from conftest import montar_evento

# O = Organizador - RH (configura o evento; desde a 0010); R = Recepcao
# (check-in, credenciamento e pulseiras); N = Equipe de Entregas.
A, S, O, R, N, K = "ADMIN", "SORTEIO", "ORGANIZADOR", "RECEPCAO", "ENTREGAS", "COLABORADOR"
EQUIPE = {A, S, O, R, N}
TODOS = {A, S, O, R, N, K}

E = "/api/events/{event_id}"
MATRIZ: dict[tuple[str, str], set[str]] = {
    # autenticacao
    ("GET", "/api/auth/me"): TODOS,
    ("POST", "/api/auth/trocar-senha"): TODOS,
    ("POST", "/api/auth/encerrar-sessoes"): TODOS,
    # eventos: criar e configuracao global so o admin; configurar o evento, admin e RH
    ("GET", "/api/events"): EQUIPE,
    ("POST", "/api/events"): {A},
    ("GET", E): EQUIPE,
    ("PATCH", E): {A, O},
    ("DELETE", E): {A},  # apagar o evento: so o admin (com sorteio, so evento de teste)
    ("POST", f"{E}/ambiente-teste"): {A},  # copia de teste do evento: so o admin
    ("POST", f"{E}/recomecar-teste"): {A},  # zerar os sorteios do evento de teste: so o admin
    ("POST", f"{E}/telao/novo-token"): {A, O},
    ("GET", f"{E}/regras"): EQUIPE,
    ("GET", f"{E}/regras/resumo"): EQUIPE,
    ("PATCH", f"{E}/regras"): {A, O},
    ("POST", f"{E}/regras/confirmar"): {A, O},
    ("GET", f"{E}/regras/historico"): EQUIPE,
    # previa do modo faixa de matriculas: so quem define as regras
    ("GET", f"{E}/regras/faixa-matricula"): {A, O},
    ("GET", f"{E}/resumo"): EQUIPE,
    # participantes (o organizador importa e cadastra colaboradores)
    ("GET", f"{E}/participantes"): {A, O},
    ("GET", f"{E}/participantes/setores"): {A, O},
    ("POST", f"{E}/participantes"): {A, O},
    ("PATCH", f"{E}/participantes/{{participant_id}}"): {A, O},
    ("POST", f"{E}/participantes/{{participant_id}}/presenca"): {A, O, R},
    ("POST", f"{E}/participantes/{{participant_id}}/participacao"): {A, O},
    ("POST", f"{E}/participantes/presenca-em-lote"): {A, O},
    ("DELETE", f"{E}/participantes/{{participant_id}}"): {A, O},
    ("POST", f"{E}/participantes/importar/previa"): {A, O},
    ("POST", f"{E}/participantes/importar/confirmar"): {A, O},
    ("POST", f"{E}/participantes/zerar"): {A, O},
    ("GET", "/api/participantes/modelo.csv"): {A, O},
    ("GET", "/api/participantes/modelo.xlsx"): {A, O},
    # premios
    ("GET", f"{E}/premios"): {A, S, O},
    ("POST", f"{E}/premios"): {A, O},
    ("PATCH", f"{E}/premios/{{prize_id}}"): {A, O},
    ("POST", f"{E}/premios/reordenar"): {A, O},
    ("DELETE", f"{E}/premios/{{prize_id}}"): {A, O},
    ("POST", f"{E}/blocos/distribuir-nos-blocos/previa"): {A, O},
    ("POST", f"{E}/blocos/distribuir-nos-blocos"): {A, O},
    ("POST", f"{E}/premios/importar/previa"): {A, O},
    ("POST", f"{E}/premios/importar/confirmar"): {A, O},
    ("GET", "/api/premios/modelo.csv"): {A, O},
    ("GET", "/api/premios/modelo.xlsx"): {A, O},
    # imagens: premios, participantes, logo e a foto opcional da entrega
    ("POST", "/api/uploads/imagem"): {A, O, R, N},
    # blocos (admin e RH organizam; o sorteador conduz)
    ("GET", f"{E}/blocos"): {A, S, O},
    ("POST", f"{E}/blocos"): {A, O},
    ("POST", f"{E}/blocos/distribuir"): {A, O},
    ("GET", f"{E}/blocos/distribuicao"): {A, S, O},
    ("PUT", f"{E}/blocos/distribuicao"): {A, O},
    ("POST", f"{E}/blocos/remanescentes"): {A, O},
    ("POST", f"{E}/blocos/distribuir/previa"): {A, O},
    ("POST", f"{E}/blocos/remanescentes/previa"): {A, O},
    ("POST", f"{E}/blocos/reordenar"): {A, O},
    ("GET", f"{E}/blocos/{{bloco_id}}"): {A, S, O},
    ("PATCH", f"{E}/blocos/{{bloco_id}}"): {A, O},
    ("DELETE", f"{E}/blocos/{{bloco_id}}"): {A},
    ("POST", f"{E}/blocos/{{bloco_id}}/iniciar"): {A, S},
    ("POST", f"{E}/blocos/{{bloco_id}}/pausar"): {A, S},
    ("POST", f"{E}/blocos/{{bloco_id}}/finalizar"): {A, S},
    ("POST", f"{E}/blocos/{{bloco_id}}/reabrir"): {A, S},
    ("GET", f"{E}/blocos/{{bloco_id}}/premiados"): {A, S, O},
    # sorteio e telao
    ("GET", f"{E}/sorteio/elegiveis"): {A, S},
    ("POST", f"{E}/sorteio"): {A, S},
    ("POST", f"{E}/sorteios/{{draw_id}}/entrega"): {A, O, R, N},
    ("POST", f"{E}/sorteios/{{draw_id}}/anular"): {A},
    ("GET", f"{E}/historico"): {A, S, O},
    ("GET", f"{E}/telao/estado"): {A, S},
    ("POST", f"{E}/telao"): {A, S},
    ("POST", f"{E}/telao/carrossel"): {A, S},
    # relatorio e historico
    ("GET", f"{E}/relatorio"): {A, O},
    ("GET", f"{E}/relatorio/export.csv"): {A, O},
    ("GET", f"{E}/relatorio/export.xlsx"): {A, O},
    ("GET", f"{E}/relatorio/auditoria"): {A},
    ("GET", "/api/sorteios"): {A, S, O},
    ("GET", "/api/sorteios/operadores"): {A, S, O},
    ("GET", "/api/sorteios/export.csv"): {A, O},
    ("GET", "/api/sorteios/export.xlsx"): {A, O},
    ("GET", "/api/sorteios/{draw_id}"): {A, S, O},
    # Central de Entregas (admin, RH, Recepcao e Equipe de Entregas; exportar so admin e RH)
    ("GET", f"{E}/recepcao/busca"): {A, O, R, N},
    ("GET", f"{E}/recepcao/atendimentos"): {A, O, R, N},
    ("GET", f"{E}/recepcao/resumo"): {A, O, R, N},
    ("GET", f"{E}/recepcao/filtros"): {A, O, R, N},
    ("GET", f"{E}/recepcao/premiados"): {A, O, R, N},
    ("POST", f"{E}/recepcao/entregar"): {A, O, R, N},
    ("POST", f"{E}/recepcao/entregas/{{draw_id}}/foto"): {A, O, R, N},
    ("GET", f"{E}/recepcao/historico"): {A, O, R, N},
    ("GET", f"{E}/recepcao/historico/export.csv"): {A, O},
    # credenciamento (admin, RH e Recepcao)
    ("GET", f"{E}/credenciamento/resumo"): {A, O, R},
    ("GET", f"{E}/credenciamento/participantes"): {A, O, R},
    # pulseira e liberar novo cadastro: so o admin
    ("POST", f"{E}/credenciamento/participantes/{{participant_id}}/pulseira"): {A},
    ("POST", f"{E}/credenciamento/participantes/{{participant_id}}/liberar-cadastro"): {A},
    # usuarios
    ("GET", "/api/usuarios"): {A},
    ("POST", "/api/usuarios"): {A},
    ("PATCH", "/api/usuarios/{user_id}"): {A},
    ("DELETE", "/api/usuarios/{user_id}"): {A},
    ("POST", "/api/usuarios/{user_id}/redefinir-senha"): {A},
    ("POST", "/api/usuarios/{user_id}/desbloquear"): {A},
    ("POST", "/api/usuarios/{user_id}/encerrar-sessoes"): {A},
    ("GET", "/api/usuarios/{user_id}/auditoria"): {A},
    # area pessoal (o admin tem todas as permissoes; ve a propria area, vazia)
    ("GET", "/api/minha-area"): TODOS,
    ("GET", "/api/minha-area/notificacoes"): TODOS,
    ("POST", "/api/minha-area/notificacoes/lidas"): TODOS,
    ("POST", "/api/minha-area/notificacoes/{notificacao_id}/lida"): TODOS,
    ("GET", "/api/minha-area/stream"): TODOS,
    # Portal do Colaborador: foto e push so da propria conta
    ("POST", "/api/minha-area/{evento_id}/foto"): TODOS,
    ("DELETE", "/api/minha-area/{evento_id}/foto"): TODOS,
    ("GET", "/api/minha-area/push"): TODOS,
    ("POST", "/api/minha-area/push/inscricao"): TODOS,
    ("POST", "/api/minha-area/push/cancelar"): TODOS,
    ("GET", "/api/minha-area/{evento_id}/qrcode.png"): TODOS,
    # link e QR Code do cadastro (configuracao do evento)
    ("GET", f"{E}/portal"): {A, O},
    ("GET", f"{E}/portal/qrcode.png"): {A, O},
}

# Fluxos SSE autorizados nunca terminam; aqui so se confere a recusa.
# O fluxo autorizado e testado em tests/test_notificacoes.py.
STREAMS = {("GET", "/api/minha-area/stream")}

# Rotas sem autenticacao, por desenho.
PUBLICAS = {
    ("POST", "/api/auth/login"),
    # Recepcao sem senha em qualquer aparelho, por decisao do evento (test_recepcao.py).
    ("GET", "/api/recepcao/eventos"),
    ("POST", "/api/recepcao/{event_id}/localizar"),
    ("POST", "/api/recepcao/{event_id}/checkin"),
    ("GET", "/api/recepcao/{event_id}/consulta"),
    ("GET", "/api/saude"),
    ("GET", "/api/public/{token}/estado"),
    ("GET", "/api/public/{token}/stream"),
    # Cadastro pelo QR Code: matricula + nascimento + 5 digitos do CPF
    # conferindo com os codigos importados (tests/test_autocadastro.py).
    ("GET", "/api/autocadastro/eventos"),
    ("GET", "/api/autocadastro/{event_id}"),
    ("POST", "/api/autocadastro/{event_id}/identificar"),
    ("POST", "/api/autocadastro/{event_id}/concluir"),
}


def _rotas_do_app() -> set[tuple[str, str]]:
    from app.main import app

    return {
        (metodo, rota.path)
        for rota in app.routes
        if isinstance(rota, APIRoute) and rota.path.startswith("/api/")
        for metodo in rota.methods - {"HEAD", "OPTIONS"}
    }


def _conta(papel: str, login: str | None = None, senha: str = "senha-forte1", **extra) -> int:
    with session_scope() as db:
        user = User(
            usuario=login or f"conta_{papel.lower()}",
            nome=f"Conta {papel.title()}",
            senha_hash=hash_senha(senha),
            papel=papel,
            **extra,
        )
        db.add(user)
        db.flush()
        return user.id


def _token_atual(user_id: int) -> dict:
    """Token valido para a versao de sessao atual (sem custo de login)."""
    with session_scope() as db:
        versao = db.get(User, user_id).sessao_versao
    return {"Authorization": f"Bearer {criar_token(user_id, versao)}"}


def _login(cliente, usuario: str, senha: str = "senha-forte1"):
    return cliente.post("/api/auth/login", json={"usuario": usuario, "senha": senha})


# ------------------------------------------------------------------ matriz
def test_toda_rota_da_api_tem_decisao_de_acesso():
    rotas = _rotas_do_app()
    sem_decisao = rotas - set(MATRIZ) - PUBLICAS
    assert not sem_decisao, f"Rotas sem linha na matriz de acesso: {sorted(sem_decisao)}"
    obsoletas = set(MATRIZ) - rotas
    assert not obsoletas, f"Linhas da matriz sem rota correspondente: {sorted(obsoletas)}"


def test_matriz_de_acesso_por_perfil(cliente):
    event_id, participantes, _ = montar_evento(participantes=3)
    with session_scope() as db:
        prize_id = db.scalar(select(Prize.id).where(Prize.event_id == event_id))
    contas = {papel: _conta(papel) for papel in TODOS}
    alvo = _conta(S, login="alvo_da_matriz")
    valores = {
        "event_id": event_id,
        "participant_id": participantes[0],
        "prize_id": prize_id,
        "bloco_id": 999_999,
        "draw_id": 999_999,
        "user_id": alvo,
        "notificacao_id": 999_999,
        "evento_id": event_id,
    }

    falhas = []
    for (metodo, caminho), autorizados in sorted(MATRIZ.items()):
        url = re.sub(r"\{(\w+)\}", lambda m: str(valores[m.group(1)]), caminho)
        for papel in sorted(TODOS):
            if (metodo, caminho) in STREAMS and papel in autorizados:
                continue
            resposta = cliente.request(metodo, url, json={}, headers=_token_atual(contas[papel]))
            codigo = resposta.status_code
            if codigo >= 500:
                falhas.append(f"{papel:11s} {metodo} {caminho} -> erro {codigo}")
            elif papel in autorizados and codigo in (401, 403):
                falhas.append(f"{papel:11s} {metodo} {caminho} -> negado ({codigo}), deveria passar")
            elif papel not in autorizados and codigo != 403:
                falhas.append(f"{papel:11s} {metodo} {caminho} -> {codigo}, deveria ser 403")
    assert not falhas, "\n".join(falhas)


def test_sem_token_tudo_exige_autenticacao(cliente):
    event_id, _, _ = montar_evento()
    for metodo, caminho in sorted(MATRIZ):
        url = re.sub(r"\{(\w+)\}", lambda m: str(event_id if m.group(1) == "event_id" else 1), caminho)
        assert cliente.request(metodo, url, json={}).status_code == 401, f"{metodo} {caminho}"


# ------------------------------------------------------------------ login e redirecionamento
@pytest.mark.parametrize("papel", sorted(TODOS))
def test_login_informa_perfil_e_permissoes(cliente, papel):
    _conta(papel)
    resposta = _login(cliente, f"conta_{papel.lower()}")
    assert resposta.status_code == 200
    usuario = resposta.json()["usuario"]
    assert usuario["papel"] == papel
    assert usuario["deve_trocar_senha"] is False
    assert ("controlar_sorteio" in usuario["permissoes"]) is (papel in {A, S})
    # Todos veem a PROPRIA area (a equipe tambem pode ser participante).
    assert "acessar_area_pessoal" in usuario["permissoes"]


def test_login_registra_ultimo_acesso_e_auditoria(cliente):
    user_id = _conta(R)
    assert _login(cliente, "conta_recepcao").status_code == 200
    with session_scope() as db:
        assert db.get(User, user_id).ultimo_acesso_em is not None
        assert db.scalar(select(AuditLog).where(AuditLog.usuario_id == user_id, AuditLog.acao == "login"))


# ------------------------------------------------------------------ sessao
def test_desativar_conta_derruba_a_sessao(cliente, auth):
    user_id = _conta(S)
    token = _login(cliente, "conta_sorteio").json()["access_token"]
    cabecalho = {"Authorization": f"Bearer {token}"}
    assert cliente.get("/api/auth/me", headers=cabecalho).status_code == 200

    cliente.patch(f"/api/usuarios/{user_id}", json={"ativo": False}, headers=auth)
    assert cliente.get("/api/auth/me", headers=cabecalho).status_code == 401
    # Reativar nao ressuscita o token antigo: e preciso entrar de novo.
    cliente.patch(f"/api/usuarios/{user_id}", json={"ativo": True}, headers=auth)
    assert cliente.get("/api/auth/me", headers=cabecalho).status_code == 401
    assert _login(cliente, "conta_sorteio").status_code == 200


def test_troca_de_perfil_vale_imediatamente(cliente, auth):
    event_id, _, _ = montar_evento()
    user_id = _conta(S)
    antigo = {"Authorization": f"Bearer {_login(cliente, 'conta_sorteio').json()['access_token']}"}
    assert cliente.get(f"/api/events/{event_id}/blocos", headers=antigo).status_code == 200

    resposta = cliente.patch(f"/api/usuarios/{user_id}", json={"papel": N}, headers=auth)
    assert resposta.status_code == 200
    assert cliente.get(f"/api/events/{event_id}/blocos", headers=antigo).status_code == 401

    novo = {"Authorization": f"Bearer {_login(cliente, 'conta_sorteio').json()['access_token']}"}
    assert cliente.get(f"/api/events/{event_id}/blocos", headers=novo).status_code == 403
    assert cliente.get(f"/api/events/{event_id}/recepcao/busca?q=pa", headers=novo).status_code == 200


def test_encerrar_sessoes_de_um_usuario(cliente, auth):
    user_id = _conta(O)
    cabecalho = {"Authorization": f"Bearer {_login(cliente, 'conta_organizador').json()['access_token']}"}
    cliente.post(f"/api/usuarios/{user_id}/encerrar-sessoes", headers=auth)
    assert cliente.get("/api/auth/me", headers=cabecalho).status_code == 401


def test_encerrar_as_proprias_sessoes_mantem_este_aparelho(cliente):
    _conta(R)
    outro_aparelho = {"Authorization": f"Bearer {_login(cliente, 'conta_recepcao').json()['access_token']}"}
    este = {"Authorization": f"Bearer {_login(cliente, 'conta_recepcao').json()['access_token']}"}
    novo = cliente.post("/api/auth/encerrar-sessoes", headers=este).json()["access_token"]
    assert cliente.get("/api/auth/me", headers=outro_aparelho).status_code == 401
    assert cliente.get("/api/auth/me", headers=este).status_code == 401
    assert cliente.get("/api/auth/me", headers={"Authorization": f"Bearer {novo}"}).status_code == 200


def test_token_anterior_a_fase_4_continua_valido(cliente):
    """Tokens emitidos antes desta fase (sem versao) valem ate expirar."""
    user_id = _conta(A)
    antigo = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.secret_key,
        algorithm="HS256",
    )
    assert cliente.get("/api/auth/me", headers={"Authorization": f"Bearer {antigo}"}).status_code == 200


@pytest.mark.parametrize("caso", ["expirado", "assinatura_errada", "lixo"])
def test_token_invalido(cliente, caso):
    user_id = _conta(A)
    token = {
        "expirado": jwt.encode(
            {"sub": str(user_id), "ver": 1, "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            settings.secret_key,
            algorithm="HS256",
        ),
        "assinatura_errada": jwt.encode(
            {"sub": str(user_id), "ver": 1, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "outra-chave",
            algorithm="HS256",
        ),
        "lixo": "nao.e.um.token",
    }[caso]
    assert cliente.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ------------------------------------------------------------------ tentativas de login
def test_conta_bloqueia_apos_tentativas_e_desbloqueia_depois(cliente):
    user_id = _conta(R)
    codigos = [_login(cliente, "conta_recepcao", "errada0").status_code for _ in range(5)]
    assert codigos == [401] * 5
    # Bloqueada: nem a senha certa entra.
    bloqueado = _login(cliente, "conta_recepcao")
    assert bloqueado.status_code == 429

    with session_scope() as db:
        db.get(User, user_id).bloqueado_ate = utcnow() - timedelta(seconds=1)
    assert _login(cliente, "conta_recepcao").status_code == 200
    with session_scope() as db:
        assert db.get(User, user_id).tentativas_falhas == 0


def test_bloqueio_nao_revela_quais_contas_existem(cliente):
    _conta(R)
    existente = [_login(cliente, "conta_recepcao", "errada0") for _ in range(6)]
    inexistente = [_login(cliente, "ninguem.aqui", "errada0") for _ in range(6)]
    assert [r.status_code for r in existente] == [r.status_code for r in inexistente]
    assert [r.json()["detail"] for r in existente] == [r.json()["detail"] for r in inexistente]


def test_mesma_mensagem_para_senha_errada_usuario_inexistente_e_conta_inativa(cliente):
    _conta(R, login="ativa")
    _conta(R, login="inativa", ativo=False)
    respostas = [
        _login(cliente, "ativa", "errada0"),
        _login(cliente, "nao.existe", "errada0"),
        _login(cliente, "inativa"),  # senha certa, conta inativa
    ]
    assert {r.status_code for r in respostas} == {401}
    assert len({r.json()["detail"] for r in respostas}) == 1


def test_limite_por_ip_impede_varrer_muitas_contas(cliente):
    _conta(A, login="vitima")
    for i in range(settings.login_max_falhas_ip):
        assert _login(cliente, f"tentativa{i}", "errada0").status_code == 401
    # Mesmo uma conta valida, com a senha certa, espera a janela passar.
    assert _login(cliente, "vitima").status_code == 429


def test_login_bem_sucedido_zera_as_falhas(cliente):
    user_id = _conta(R)
    for _ in range(3):
        _login(cliente, "conta_recepcao", "errada0")
    assert _login(cliente, "conta_recepcao").status_code == 200
    with session_scope() as db:
        assert db.get(User, user_id).tentativas_falhas == 0


# ------------------------------------------------------------------ senha temporaria
def _criar_pela_tela(cliente, auth, usuario: str, papel: str) -> dict:
    resposta = cliente.post(
        "/api/usuarios", json={"usuario": usuario, "nome": "Pessoa Nova", "papel": papel}, headers=auth
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_usuario_criado_precisa_trocar_a_senha_temporaria(cliente, auth):
    montar_evento()
    criado = _criar_pela_tela(cliente, auth, "joana.op", S)
    temporaria = criado["senha_temporaria"]
    assert len(temporaria) == 12
    assert criado["usuario"]["deve_trocar_senha"] is True

    login = _login(cliente, "joana.op", temporaria).json()
    assert login["usuario"]["deve_trocar_senha"] is True
    cabecalho = {"Authorization": f"Bearer {login['access_token']}"}
    # Antes de trocar: so /me e a troca de senha respondem.
    bloqueio = cliente.get("/api/events", headers=cabecalho)
    assert bloqueio.status_code == 403
    assert "senha temporária" in bloqueio.json()["detail"]
    assert cliente.get("/api/auth/me", headers=cabecalho).status_code == 200

    trocar = "/api/auth/trocar-senha"
    assert cliente.post(trocar, json={"senha_atual": "errada0", "senha_nova": "Nova12345"}, headers=cabecalho).status_code == 401
    assert cliente.post(trocar, json={"senha_atual": temporaria, "senha_nova": "curta1"}, headers=cabecalho).status_code == 422
    assert cliente.post(trocar, json={"senha_atual": temporaria, "senha_nova": "somenteletras"}, headers=cabecalho).status_code == 422
    assert cliente.post(trocar, json={"senha_atual": temporaria, "senha_nova": "joana.op123"}, headers=cabecalho).status_code == 422

    ok = cliente.post(trocar, json={"senha_atual": temporaria, "senha_nova": "Palco2026x"}, headers=cabecalho)
    assert ok.status_code == 200
    novo = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert cliente.get("/api/events", headers=novo).status_code == 200
    assert cliente.get("/api/events", headers=cabecalho).status_code == 401  # token antigo caiu
    assert _login(cliente, "joana.op", temporaria).status_code == 401
    assert _login(cliente, "joana.op", "Palco2026x").status_code == 200


def test_redefinir_senha(cliente, auth):
    user_id = _conta(R, senha="Antiga1234")
    antigo = {"Authorization": f"Bearer {_login(cliente, 'conta_recepcao', 'Antiga1234').json()['access_token']}"}
    for _ in range(5):
        _login(cliente, "conta_recepcao", "errada0")  # deixa a conta bloqueada

    resposta = cliente.post(f"/api/usuarios/{user_id}/redefinir-senha", headers=auth)
    assert resposta.status_code == 200
    temporaria = resposta.json()["senha_temporaria"]

    assert cliente.get("/api/auth/me", headers=antigo).status_code == 401
    assert _login(cliente, "conta_recepcao", "Antiga1234").status_code == 401
    entrou = _login(cliente, "conta_recepcao", temporaria)
    assert entrou.status_code == 200  # redefinir tambem desbloqueia
    assert entrou.json()["usuario"]["deve_trocar_senha"] is True


# ------------------------------------------------------------------ gerenciamento de usuarios
def test_lista_de_usuarios_nunca_expoe_senha(cliente, auth):
    _criar_pela_tela(cliente, auth, "maria.recepcao", R)
    resposta = cliente.get("/api/usuarios", headers=auth)
    assert resposta.status_code == 200
    assert "senha_hash" not in resposta.text and "pbkdf2" not in resposta.text
    assert {u["usuario"] for u in resposta.json()} >= {"organizador", "maria.recepcao"}
    filtrado = cliente.get("/api/usuarios", params={"papel": R}, headers=auth).json()
    assert [u["usuario"] for u in filtrado] == ["maria.recepcao"]


@pytest.mark.parametrize(
    "corpo,codigo",
    [
        ({"usuario": "novo.colab", "nome": "X", "papel": K}, 422),
        ({"usuario": "Com Espaco", "nome": "X", "papel": S}, 422),
        ({"usuario": "ab", "nome": "X", "papel": S}, 422),
        ({"usuario": "organizador", "nome": "X", "papel": S}, 409),
    ],
    ids=["colaborador-pela-tela", "usuario-invalido", "usuario-curto", "duplicado"],
)
def test_criacao_de_usuario_invalida(cliente, auth, corpo, codigo):
    assert cliente.post("/api/usuarios", json=corpo, headers=auth).status_code == codigo


def test_admin_nao_desativa_nem_rebaixa_a_si_mesmo(cliente, auth):
    with session_scope() as db:
        meu_id = db.scalar(select(User.id).where(User.usuario == "organizador"))
    assert cliente.patch(f"/api/usuarios/{meu_id}", json={"ativo": False}, headers=auth).status_code == 409
    assert cliente.patch(f"/api/usuarios/{meu_id}", json={"papel": S}, headers=auth).status_code == 409


def test_colaborador_promovido_recebe_senha_temporaria_e_equipe_nao_volta_a_colaborador(cliente, auth):
    colab = _conta(K)
    promovido = cliente.patch(f"/api/usuarios/{colab}", json={"papel": O}, headers=auth)
    assert promovido.status_code == 200 and promovido.json()["senha_temporaria"]
    assert promovido.json()["deve_trocar_senha"] is True
    assert cliente.patch(f"/api/usuarios/{colab}", json={"papel": K}, headers=auth).status_code == 409


# Exclusao de usuario (so contas sem historico operacional): test_excluir_usuario.py


def test_auditoria_do_usuario(cliente, auth):
    criado = _criar_pela_tela(cliente, auth, "carlos.op", S)
    user_id = criado["usuario"]["id"]
    _login(cliente, "carlos.op", criado["senha_temporaria"])
    cliente.patch(f"/api/usuarios/{user_id}", json={"nome": "Carlos Operador"}, headers=auth)
    acoes = [r["acao"] for r in cliente.get(f"/api/usuarios/{user_id}/auditoria", headers=auth).json()]
    assert {"usuario_criado", "login", "usuario_alterado"} <= set(acoes)


# ------------------------------------------------------------------ operador
def test_operador_conduz_o_sorteio_mas_nao_altera_regras_nem_resultados(cliente, auth):
    event_id, _, unidades = montar_evento(participantes=3)
    op = _token_atual(_conta(S))
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "operador-0001"},
        headers=op,
    )
    assert sorteio.status_code == 200
    assert sorteio.json()["criado_por"] == "Conta Sorteio"
    draw_id = sorteio.json()["id"]

    proibidas = [
        ("PATCH", f"/api/events/{event_id}/regras", {"exige_presenca": False}),
        ("POST", f"/api/events/{event_id}/sorteios/{draw_id}/anular", {"motivo": "Tentativa", "tipo": "outro"}),
        ("POST", f"/api/events/{event_id}/sorteios/{draw_id}/entrega", {"entregue": True}),
        ("POST", f"/api/events/{event_id}/blocos/distribuir", {"capacidade": 25}),
        ("GET", "/api/usuarios", None),
    ]
    for metodo, url, corpo in proibidas:
        assert cliente.request(metodo, url, json=corpo, headers=op).status_code == 403, url
    with session_scope() as db:
        assert db.get(Draw, draw_id).status == "valido"
        assert db.get(Draw, draw_id).entregue is False


# ------------------------------------------------------------------ entregas (organizador)
def _evento_com_ganhador(cliente, auth) -> tuple[int, dict, int]:
    event_id, ids, unidades = montar_evento(participantes=1)
    with session_scope() as db:
        db.get(Participant, ids[0]).pulseira = "B-0007"
    sorteio = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "recepcao-0001"},
        headers=auth,
    ).json()
    return event_id, sorteio, ids[0]


def test_organizador_localiza_ganhador_por_nome_matricula_ou_pulseira(cliente, auth):
    event_id, sorteio, participante = _evento_com_ganhador(cliente, auth)
    rec = _token_atual(_conta(O))
    for termo in ("participante 1", "00001", "b-0007"):
        resultado = cliente.get(f"/api/events/{event_id}/recepcao/busca", params={"q": termo}, headers=rec).json()
        assert [c["id"] for c in resultado] == [participante], termo
        assert resultado[0]["premios"][0]["sorteio_id"] == sorteio["id"]
    assert cliente.get(f"/api/events/{event_id}/recepcao/busca", params={"q": "x"}, headers=rec).status_code == 422


def test_organizador_confere_pulseira_e_registra_atendimento(cliente, auth):
    event_id, sorteio, _ = _evento_com_ganhador(cliente, auth)
    rec = _token_atual(_conta(O))
    url = f"/api/events/{event_id}/sorteios/{sorteio['id']}/entrega"

    errada = cliente.post(url, json={"entregue": True, "pulseira_conferida": "B-0008"}, headers=rec)
    assert errada.status_code == 409
    assert "não confere" in errada.json()["detail"]

    certa = cliente.post(url, json={"entregue": True, "pulseira_conferida": "b-0007"}, headers=rec)
    assert certa.status_code == 200
    assert certa.json()["entregue_por"] == "Conta Organizador"

    (atendimento,) = cliente.get(f"/api/events/{event_id}/recepcao/atendimentos", headers=rec).json()
    assert atendimento["acao"] == "entrega_registrada"
    assert atendimento["atendente"] == "Conta Organizador"
    assert atendimento["pulseira_conferida"] == "B-0007"
    assert atendimento["participante"] == "Participante 1"


def test_atendimentos_antigos_sao_completados_pelo_sorteio(cliente, auth):
    """Entregas registradas antes da Fase 4 tinham so o sorteio_id na auditoria."""
    event_id, sorteio, _ = _evento_com_ganhador(cliente, auth)
    with session_scope() as db:
        organizador = db.scalar(select(User).where(User.usuario == "organizador"))
        db.add(
            AuditLog(
                event_id=event_id,
                usuario_id=organizador.id,
                acao="entrega_registrada",
                detalhes={"sorteio_id": sorteio["id"]},
            )
        )
    (antigo,) = cliente.get(f"/api/events/{event_id}/recepcao/atendimentos", headers=auth).json()
    assert antigo["participante"] == "Participante 1"
    assert antigo["premio"] == "Premio Teste"
    assert antigo["unidade"] == 1


def test_organizador_nao_sorteia_nem_anula(cliente, auth):
    event_id, sorteio, _ = _evento_com_ganhador(cliente, auth)
    rec = _token_atual(_conta(O))
    assert cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/anular",
        json={"motivo": "Tentativa indevida", "tipo": "outro"},
        headers=rec,
    ).status_code == 403
    assert cliente.post(
        f"/api/events/{event_id}/sorteio", json={"prize_unit_id": 1, "idempotency_key": "rec-tenta-01"}, headers=rec
    ).status_code == 403


# ------------------------------------------------------------------ credenciamento
def test_organizador_acompanha_credenciamento_marca_presenca_e_entrega_pulseira(cliente, auth):
    event_id, ids, _ = montar_evento(participantes=4, presentes=1)
    ck = _token_atual(_conta(O))
    base = f"/api/events/{event_id}/credenciamento"

    resumo = cliente.get(f"{base}/resumo", headers=ck).json()
    assert (resumo["participantes"], resumo["presentes"], resumo["sem_pulseira"]) == (4, 1, 4)

    ausentes = cliente.get(f"{base}/participantes", params={"situacao": "ausentes"}, headers=ck).json()
    assert ausentes["total"] == 3

    presenca = cliente.post(
        f"/api/events/{event_id}/participantes/{ids[1]}/presenca", json={"presente": True}, headers=ck
    )
    assert presenca.status_code == 200
    # Uma conta Recepcao confirma presenca (credenciamento), mas nao edita cadastro.
    rec = _token_atual(_conta(R))
    assert cliente.patch(
        f"/api/events/{event_id}/participantes/{ids[1]}", json={"nome": "Outro"}, headers=rec
    ).status_code == 403
    assert cliente.post(
        f"/api/events/{event_id}/participantes/{ids[2]}/presenca", json={"presente": True}, headers=rec
    ).status_code == 200
    # A Equipe de Entregas nao faz credenciamento.
    ent = _token_atual(_conta(N))
    assert cliente.post(
        f"/api/events/{event_id}/participantes/{ids[3]}/presenca", json={"presente": True}, headers=ent
    ).status_code == 403

    # Pulseira e liberar novo cadastro: so o admin (o RH e a Recepcao so marcam presenca).
    url = f"{base}/participantes/{ids[1]}/pulseira"
    assert cliente.post(url, json={"pulseira": "0042"}, headers=ck).status_code == 403
    assert cliente.post(url, json={"pulseira": "0042"}, headers=rec).status_code == 403
    assert cliente.post(url, json={"pulseira": "0042"}, headers=auth).json()["pulseira"] == "0042"
    assert cliente.post(url, json={"pulseira": "0043"}, headers=auth).status_code == 422  # troca sem motivo
    trocada = cliente.post(url, json={"pulseira": "0043", "motivo": "Pulseira rasgou"}, headers=auth)
    assert trocada.status_code == 200
    ocupada = cliente.post(f"{base}/participantes/{ids[2]}/pulseira", json={"pulseira": "0043"}, headers=auth)
    assert ocupada.status_code == 409
    # Desfazer a presenca continua com quem confirma.
    desfeita = cliente.post(
        f"/api/events/{event_id}/participantes/{ids[2]}/presenca", json={"presente": False}, headers=rec
    )
    assert desfeita.status_code == 200 and desfeita.json()["presente"] is False

    acoes = [
        (r["acao"], r["detalhes"].get("motivo"))
        for r in cliente.get(f"/api/events/{event_id}/relatorio/auditoria", headers=auth).json()
        if r["acao"].startswith("pulseira_")
    ]
    assert ("pulseira_trocada", "Pulseira rasgou") in acoes
    assert ("pulseira_atribuida", None) in acoes


# ------------------------------------------------------------------ colaborador
def test_colaborador_ve_somente_a_propria_area(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=2)
    maria = _conta(K, login="maria")
    joao = _conta(K, login="joao")
    with session_scope() as db:
        db.get(Participant, ids[0]).usuario_id = maria
        db.get(Participant, ids[1]).usuario_id = joao
        # Garante que Maria ganha: so ela concorre.
        db.get(Participant, ids[1]).presente = False
    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "colab-0001"},
        headers=auth,
    )
    # Fase 6: o premio so aparece na area pessoal depois da revelacao no telao.
    from datetime import timedelta as _td

    from sqlalchemy import update as _update

    from app.models import Notificacao

    with session_scope() as db:
        db.execute(_update(Notificacao).values(disponivel_em=utcnow() - _td(seconds=1)))

    area_maria = cliente.get("/api/minha-area", headers=_token_atual(maria)).json()
    area_joao = cliente.get("/api/minha-area", headers=_token_atual(joao)).json()
    assert [p["nome"] for p in area_maria["participacoes"]] == ["Participante 1"]
    assert len(area_maria["participacoes"][0]["premios"]) == 1
    assert [p["nome"] for p in area_joao["participacoes"]] == ["Participante 2"]
    assert area_joao["participacoes"][0]["premios"] == []
    assert "Participante 1" not in str(area_joao)


def test_colaborador_nao_alcanca_dados_de_outros(cliente, auth):
    event_id, ids, _ = montar_evento(participantes=2)
    colab = _token_atual(_conta(K))
    for url in (
        "/api/events",
        f"/api/events/{event_id}",
        f"/api/events/{event_id}/participantes",
        f"/api/events/{event_id}/recepcao/busca?q=participante",
        f"/api/events/{event_id}/credenciamento/participantes",
        "/api/sorteios?q=participante",
        "/api/usuarios",
    ):
        assert cliente.get(url, headers=colab).status_code == 403, url
    # A area pessoal nao aceita parametro para escolher outra pessoa.
    from app.main import app

    rota = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/api/minha-area")
    assert rota.dependant.query_params == [] and rota.dependant.path_params == []
