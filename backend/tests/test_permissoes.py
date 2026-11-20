"""Mapa de permissoes por perfil (app/permissoes.py).

A verificacao rota a rota, perfil a perfil, esta em test_acesso.py.
"""

from __future__ import annotations

from app.database import session_scope
from app.models import Papel, User
from app.permissoes import (
    PAPEIS_INTERNOS,
    PERMISSOES_POR_PAPEL,
    Permissao,
    permissoes_do_papel,
    tem_alguma_permissao,
    tem_permissao,
)
from app.security import hash_senha
from conftest import montar_evento


def test_todo_papel_tem_permissoes_definidas():
    assert set(PERMISSOES_POR_PAPEL) == set(Papel)


def test_admin_tem_acesso_completo():
    assert permissoes_do_papel("ADMIN") == frozenset(Permissao)


def test_operador_de_sorteio_conforme_especificacao():
    concedidas = permissoes_do_papel("SORTEIO")
    assert concedidas == {
        Permissao.VISUALIZAR_EVENTO,
        Permissao.VISUALIZAR_BLOCOS,
        Permissao.CONTROLAR_SORTEIO,
        Permissao.CONTROLAR_TELAO,
        Permissao.CONSULTAR_RESULTADOS,
        Permissao.ACESSAR_AREA_PESSOAL,  # o proprio cartao, se tambem for participante
    }
    # Nao pode: usuarios, regras de elegibilidade, configuracoes criticas,
    # alterar resultados nem confirmar entrega.
    for proibida in (
        Permissao.GERENCIAR_USUARIOS,
        Permissao.GERENCIAR_EVENTOS,
        Permissao.DEFINIR_REGRAS,
        Permissao.ANULAR_RESULTADO,
        Permissao.CONFIGURAR_BLOCOS,
        Permissao.GERENCIAR_PARTICIPANTES,
        Permissao.CONFIRMAR_ENTREGA,
    ):
        assert proibida not in concedidas


def test_organizador_rh_configura_o_evento_mas_nao_administra():
    assert tem_permissao(
        "ORGANIZADOR",
        Permissao.CONFIGURAR_EVENTO,
        Permissao.GERENCIAR_PARTICIPANTES,
        Permissao.CADASTRAR_PREMIOS,
        Permissao.CONFIGURAR_BLOCOS,
        Permissao.DEFINIR_REGRAS,
        Permissao.ACOMPANHAR_CREDENCIAMENTO,
        Permissao.AUXILIAR_CREDENCIAMENTO,
        Permissao.CONFIRMAR_ENTREGA,
        Permissao.DESFAZER_ENTREGA,
        Permissao.CONSULTAR_RELATORIOS,
    )
    for proibida in (
        Permissao.GERENCIAR_USUARIOS,
        Permissao.GERENCIAR_EVENTOS,  # criar eventos / configuracao global
        Permissao.ANULAR_RESULTADO,
        Permissao.VISUALIZAR_AUDITORIA,
        Permissao.CONTROLAR_SORTEIO,  # so com "pode operar sorteios"
        Permissao.CONTROLAR_TELAO,
    ):
        assert not tem_permissao("ORGANIZADOR", proibida)


def test_organizador_rh_autorizado_opera_sorteios():
    autorizado = User(usuario="rh", nome="RH", senha_hash="x", papel="ORGANIZADOR", pode_sortear=True)
    comum = User(usuario="rh2", nome="RH 2", senha_hash="x", papel="ORGANIZADOR", pode_sortear=False)
    assert tem_permissao(autorizado, Permissao.CONTROLAR_SORTEIO, Permissao.CONTROLAR_TELAO)
    assert not tem_permissao(comum, Permissao.CONTROLAR_SORTEIO)
    # A autorizacao nao vale para outros perfis.
    entregas = User(usuario="e", nome="E", senha_hash="x", papel="ENTREGAS", pode_sortear=True)
    assert not tem_permissao(entregas, Permissao.CONTROLAR_SORTEIO)


def test_equipe_de_entregas_so_entrega():
    assert permissoes_do_papel("ENTREGAS") == {
        Permissao.VISUALIZAR_EVENTO,
        Permissao.PESQUISAR_COLABORADORES,
        Permissao.CONFIRMAR_ENTREGA,
        Permissao.CONSULTAR_ATENDIMENTOS,
        Permissao.ACESSAR_AREA_PESSOAL,
    }


def test_recepcao_faz_checkin_credenciamento_e_pulseiras():
    # O check-in e a consulta do numero sao publicos; com a conta, tambem o credenciamento.
    assert permissoes_do_papel("RECEPCAO") == {
        Permissao.VISUALIZAR_EVENTO,
        Permissao.ACOMPANHAR_CREDENCIAMENTO,
        Permissao.AUXILIAR_CREDENCIAMENTO,
        Permissao.ACESSAR_AREA_PESSOAL,
    }


def test_colaborador_so_acessa_a_propria_area():
    assert permissoes_do_papel("COLABORADOR") == {Permissao.ACESSAR_AREA_PESSOAL}
    assert Papel.COLABORADOR not in PAPEIS_INTERNOS


def test_papel_desconhecido_nao_recebe_nada():
    assert permissoes_do_papel("SUPERUSUARIO") == frozenset()
    assert not tem_permissao("", Permissao.CONSULTAR_RESULTADOS)
    assert not tem_alguma_permissao("", *Permissao)


def test_organizador_existente_continua_com_acesso_total(cliente, auth):
    montar_evento()
    assert cliente.get("/api/events", headers=auth).status_code == 200
    me = cliente.get("/api/auth/me", headers=auth).json()
    assert me["papel"] == "ADMIN"
    assert set(me["permissoes"]) == {p.value for p in Permissao}
    assert me["deve_trocar_senha"] is False


def test_conta_inativa_nao_entra(cliente):
    with session_scope() as db:
        db.add(
            User(
                usuario="inativo",
                nome="Inativo",
                senha_hash=hash_senha("senha-forte1"),
                papel="ADMIN",
                ativo=False,
            )
        )
    resposta = cliente.post("/api/auth/login", json={"usuario": "inativo", "senha": "senha-forte1"})
    assert resposta.status_code == 401
