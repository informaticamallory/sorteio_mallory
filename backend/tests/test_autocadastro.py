"""Cadastro pelo QR Code (Portal do Colaborador).

Matricula + data de nascimento + 5 primeiros digitos do CPF -> foto opcional
e senha -> cartao da sorte. O cadastro nao confirma presenca nem registra
pulseira (isso e do check-in da Recepcao).
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.database import session_scope
from app.models import AuditLog, Event, Participant, User, utcnow
from app.security import criar_passe_cadastro, ler_token
from app.services import autocadastro as servico
from app.services.erros import RegraDeNegocio
from apoio import (
    NASCIMENTO,
    autocadastrar,
    cabecalho,
    concluir,
    configurar_evento,
    conta,
    cpf_do,
    dar_identificacao,
    identificar,
    imagem,
    senha_de,
)
from conftest import montar_evento


def _participante(pid: int) -> Participant:
    with session_scope() as db:
        p = db.get(Participant, pid)
        db.expunge(p)
        return p


def _tentar(cliente, event_id: int, matricula: str, nascimento: str, cpf5: str):
    return cliente.post(
        f"/api/autocadastro/{event_id}/identificar",
        json={"matricula": matricula, "nascimento": nascimento, "cpf5": cpf5},
    )


# ------------------------------------------------------------------ identificacao
def test_dados_corretos_identificam_e_devolvem_so_o_necessario(cliente):
    event_id, participantes, _ = montar_evento(participantes=2)
    configurar_evento(event_id)
    cpf = dar_identificacao(participantes[0])

    resposta = _tentar(cliente, event_id, "00001", NASCIMENTO.isoformat(), cpf[:5])
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert set(corpo) == {"passe", "nome", "matricula", "foto_url", "login", "conta_equipe"}
    assert corpo["conta_equipe"] is False
    assert corpo["nome"] == "Participante 1" and corpo["login"] == "00001"
    # Nem a data de nascimento nem o CPF voltam na resposta.
    assert "1990" not in resposta.text and cpf[:5] not in resposta.text


@pytest.mark.parametrize("digitada", ["1", "001", "00001", " 00001 "])
def test_matricula_com_ou_sem_zeros_a_esquerda_e_a_mesma(cliente, digitada):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    cpf = dar_identificacao(participantes[0])
    resposta = _tentar(cliente, event_id, digitada, NASCIMENTO.isoformat(), cpf[:5])
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["matricula"] == "00001"  # a original e preservada


def test_qualquer_dado_errado_da_a_mesma_resposta_generica(cliente):
    event_id, participantes, _ = montar_evento(participantes=3)
    configurar_evento(event_id)
    cpf = dar_identificacao(participantes[0])
    # participantes[2] nao tem CPF/nascimento importados.

    respostas = [
        _tentar(cliente, event_id, "00001", "1990-03-16", cpf[:5]),  # nascimento errado
        _tentar(cliente, event_id, "00001", NASCIMENTO.isoformat(), "99999"),  # CPF errado
        _tentar(cliente, event_id, "99999", NASCIMENTO.isoformat(), cpf[:5]),  # matricula inexistente
        _tentar(cliente, event_id, "00003", NASCIMENTO.isoformat(), "12345"),  # sem identificacao
        _tentar(cliente, event_id, "00001", "15/03/90", cpf[:5]),  # formato invalido
        _tentar(cliente, event_id, "00001", NASCIMENTO.isoformat(), "12a45"),
    ]
    assert {r.status_code for r in respostas} == {401}
    assert len({r.text for r in respostas}) == 1
    assert "Participante" not in respostas[0].text


def test_matricula_fora_da_lista_nao_cria_participante(cliente):
    event_id, _p, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    resposta = concluir(cliente, event_id, "77777")
    assert resposta.status_code == 401
    with session_scope() as db:
        assert db.scalar(select(func.count(Participant.id))) == 1


def test_cadastro_fechado_ou_fora_do_periodo_nao_responde(cliente):
    event_id, participantes, _ = montar_evento(participantes=1)
    dar_identificacao(participantes[0])
    assert identificar(cliente, event_id, "00001").status_code == 404
    assert cliente.get(f"/api/autocadastro/{event_id}").status_code == 404
    assert cliente.get("/api/autocadastro/eventos").json() == []

    configurar_evento(event_id)
    abertos = cliente.get("/api/autocadastro/eventos").json()
    assert [e["id"] for e in abertos] == [event_id]
    # Apenas nome e identidade visual: nada de participantes ou tokens.
    assert set(abertos[0]) == {"id", "nome", "empresa_nome", "logo_url", "cor_fundo", "cor_primaria", "demo"}
    assert cliente.get(f"/api/autocadastro/{event_id}").json()["id"] == event_id

    configurar_evento(event_id, autocadastro_inicio=utcnow() + timedelta(hours=1))
    assert identificar(cliente, event_id, "00001").status_code == 404
    configurar_evento(event_id, autocadastro_inicio=None, autocadastro_fim=utcnow() - timedelta(minutes=1))
    assert identificar(cliente, event_id, "00001").status_code == 404
    assert cliente.get("/api/autocadastro/eventos").json() == []
    configurar_evento(event_id, autocadastro_fim=utcnow() + timedelta(hours=1))
    assert identificar(cliente, event_id, "00001").status_code == 200


def test_periodo_invalido_e_recusado_pelo_painel(cliente, auth):
    event_id, _p, _ = montar_evento(participantes=1)
    resposta = cliente.patch(
        f"/api/events/{event_id}",
        json={"autocadastro_inicio": "2026-12-01T20:00:00Z", "autocadastro_fim": "2026-12-01T18:00:00Z"},
        headers=auth,
    )
    assert resposta.status_code == 422
    ok = cliente.patch(
        f"/api/events/{event_id}",
        json={"autocadastro_inicio": "2026-12-01T18:00:00-03:00", "autocadastro_fim": None},
        headers=auth,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["autocadastro_inicio"].startswith("2026-12-01T21:00:00")  # gravado em UTC


def test_limite_de_tentativas_por_ip(cliente):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    dar_identificacao(participantes[0])
    for i in range(settings.login_max_falhas_ip):
        _tentar(cliente, event_id, f"{i + 100:05d}", "1990-01-01", "11111")
    assert identificar(cliente, event_id, "00001").status_code == 429


def test_limite_de_tentativas_por_matricula_vale_com_ou_sem_zeros(cliente):
    """Impede adivinhar nascimento e CPF de um colega por tentativa e erro."""
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    dar_identificacao(participantes[0])
    for i, matricula in enumerate(["00001", "1", "001", "0001", "01"]):
        assert _tentar(cliente, event_id, matricula, "1990-01-01", f"{i:05d}").status_code == 401
    # Mesmo com os dados certos, a matricula fica bloqueada por um tempo.
    assert identificar(cliente, event_id, "00001").status_code == 429


# ------------------------------------------------------------------ passe
def test_passe_nao_vale_como_sessao_nem_em_outro_evento(cliente):
    evento_a, pa, _ = montar_evento(participantes=1)
    evento_b, pb, _ = montar_evento(participantes=1)
    configurar_evento(evento_a)
    configurar_evento(evento_b)
    passe = identificar(cliente, evento_a, "00001").json()["passe"]

    assert ler_token(passe) is None
    assert cliente.get("/api/minha-area", headers={"Authorization": f"Bearer {passe}"}).status_code == 401
    # Passe do evento A nao conclui cadastro no evento B.
    assert concluir(cliente, evento_b, "00001", passe=passe).status_code == 401
    assert concluir(cliente, evento_a, "00001", passe=passe + "x").status_code == 401
    assert _participante(pb[0]).usuario_id is None and _participante(pa[0]).usuario_id is None


def test_passe_vencido_e_recusado(cliente, monkeypatch):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    monkeypatch.setattr(settings, "cadastro_passe_minutos", -1)
    passe = criar_passe_cadastro(event_id, participantes[0])
    resposta = concluir(cliente, event_id, "00001", passe=passe)
    assert resposta.status_code == 401 and "expirou" in resposta.json()["detail"]


# ------------------------------------------------------------------ conclusao
def test_cadastro_cria_conta_e_cartao_sem_confirmar_presenca_nem_pulseira(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=2, presentes=0)
    configurar_evento(event_id, autocadastro_confirma_presenca=True)  # legado: ignorado
    numero = _participante(participantes[0]).numero_sorteio
    resultado = autocadastrar(cliente, auth, event_id, participantes[0], "00001")

    assert resultado["conta_nova"] is True
    assert resultado["usuario"]["papel"] == "COLABORADOR"
    assert resultado["login"] == "00001"
    cartao = resultado["cartao"]
    assert cartao["numero_sorteio"] == numero  # o numero do banco, nao um novo
    assert cartao["presente"] is False and cartao["participando"] is True
    assert cartao["evento_nome"] == "Evento de Teste" and cartao["matricula"] == "00001"

    p = _participante(participantes[0])
    assert p.presente is False and p.pulseira is None and p.foto_url.startswith("/uploads/")
    assert p.numero_sorteio == numero

    # O token devolvido ja e a sessao do colaborador, com o mesmo numero.
    area = cliente.get(
        "/api/minha-area", headers={"Authorization": f"Bearer {resultado['access_token']}"}
    ).json()
    assert area["participacoes"][0]["numero_sorteio"] == numero
    # Ele entra depois com matricula (com ou sem os zeros) + 5 primeiros digitos do CPF.
    for usuario in ("00001", "1"):
        login = cliente.post("/api/auth/login", json={"usuario": usuario, "senha": senha_de(participantes[0])})
        assert login.status_code == 200, usuario
        area = cliente.get(
            "/api/minha-area", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
        ).json()
        assert area["participacoes"][0]["numero_sorteio"] == numero  # acesso repetido: mesmo numero

    with session_scope() as db:
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "autocadastro_concluido"))
        assert registro.detalhes["origem"] == "portal_qrcode"
        assert not db.scalars(select(AuditLog).where(AuditLog.acao == "pulseira_atribuida")).all()
        assert db.get(Participant, participantes[1]).usuario_id is None


def test_cpf_e_nascimento_nunca_sao_gravados_nem_auditados(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    cpf = cpf_do(participantes[0])
    autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    with session_scope() as db:
        p = db.get(Participant, participantes[0])
        assert cpf not in str(p.identificacao_hash) and cpf not in str(p.cpf_hash)
        textos = " ".join(str(a.detalhes) for a in db.scalars(select(AuditLog)).all())
    assert cpf[:5] not in textos and "1990" not in textos


def test_participante_sem_numero_recebe_cartao_sem_numero(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    with session_scope() as db:
        db.get(Participant, participantes[0]).numero_sorteio = None
    resultado = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    assert resultado["cartao"]["numero_sorteio"] is None
    # Nenhum numero e gerado no acesso.
    assert _participante(participantes[0]).numero_sorteio is None


def test_so_vale_o_primeiro_cadastro(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    primeiro = autocadastrar(cliente, auth, event_id, participantes[0], "00001")

    # Quem souber os dados de identificacao nao refaz o cadastro (nem troca foto/conta).
    assert identificar(cliente, event_id, "00001").status_code == 409
    passe = criar_passe_cadastro(event_id, participantes[0])
    repetido = concluir(cliente, event_id, "00001", passe=passe)
    assert repetido.status_code == 409
    assert cliente.get(
        "/api/minha-area", headers={"Authorization": f"Bearer {primeiro['access_token']}"}
    ).status_code == 200


def test_pulseira_entregue_pelo_checkin_e_mantida(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    with session_scope() as db:
        db.get(Participant, participantes[0]).pulseira = "P-007"
    autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    assert _participante(participantes[0]).pulseira == "P-007"


def test_senha_e_os_5_digitos_do_cpf_conferidos_de_novo_na_conclusao(cliente):
    """Decisao do cliente: a senha e os 5 primeiros digitos do CPF (so o hash e gravado)."""
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    cinco = senha_de(participantes[0])
    passe = identificar(cliente, event_id, "00001").json()["passe"]

    # O aparelho nao escolhe a senha: digitos ou nascimento diferentes sao recusados.
    for nascimento, cpf5 in [("1990-03-15", "99999"), ("1990-03-16", cinco), ("1990-03-15", "")]:
        resposta = concluir(cliente, event_id, "00001", passe=passe, nascimento=nascimento, cpf5=cpf5)
        assert resposta.status_code == 401, (nascimento, cpf5, resposta.text)
    assert _participante(participantes[0]).usuario_id is None

    assert concluir(cliente, event_id, "00001", passe=passe).status_code == 200
    with session_scope() as db:
        conta_criada = db.scalar(select(User).where(User.usuario == "00001"))
        assert cinco not in conta_criada.senha_hash  # gravado como hash, nunca os digitos
    assert cliente.post("/api/auth/login", json={"usuario": "1", "senha": cinco}).status_code == 200
    assert cliente.post("/api/auth/login", json={"usuario": "1", "senha": "00000"}).status_code == 401


def test_foto_e_opcional_e_validada_no_backend(cliente):
    event_id, participantes, _ = montar_evento(participantes=4)
    configurar_evento(event_id)

    # Arquivo que nao e imagem, mesmo com extensao de imagem.
    falsa = concluir(cliente, event_id, "00001", foto=b"%PDF-1.4 nao sou foto", nome_foto="x.jpg")
    assert falsa.status_code == 422
    # Grande demais.
    grande = b"\xff" * (settings.max_upload_bytes + 1)
    assert concluir(cliente, event_id, "00001", foto=grande).status_code == 413
    # Sem foto: permitido.
    assert concluir(cliente, event_id, "00001", enviar_foto=False).status_code == 200
    assert _participante(participantes[0]).foto_url is None

    # PNG enviado da galeria.
    png = concluir(cliente, event_id, "00002", foto=imagem("PNG"), nome_foto="g.png")
    assert png.status_code == 200
    assert _participante(participantes[1]).foto_url.endswith(".png")

    # Quem ja tem foto (importada) pode manter...
    with session_scope() as db:
        db.get(Participant, participantes[2]).foto_url = "/uploads/importada.jpg"
        db.get(Participant, participantes[3]).foto_url = "/uploads/importada-4.jpg"
    assert concluir(cliente, event_id, "00003", enviar_foto=False).status_code == 200
    assert _participante(participantes[2]).foto_url == "/uploads/importada.jpg"
    # ...ou remover.
    (settings.upload_dir / "importada-4.jpg").write_bytes(imagem())
    assert concluir(cliente, event_id, "00004", enviar_foto=False, remover_foto=True).status_code == 200
    assert _participante(participantes[3]).foto_url is None
    assert not (settings.upload_dir / "importada-4.jpg").exists()  # arquivo apagado (LGPD)


# ------------------------------------------------------------------ check-in libera novo cadastro
def _liberar(cliente, cab, event_id, pid, motivo="Esqueceu a senha"):
    return cliente.post(
        f"/api/events/{event_id}/credenciamento/participantes/{pid}/liberar-cadastro",
        json={"motivo": motivo},
        headers=cab,
    )


def test_admin_libera_novo_cadastro_e_derruba_a_sessao_antiga(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    organizador = cabecalho(conta("ORGANIZADOR"))
    with session_scope() as db:
        db.get(Participant, participantes[0]).pulseira = "P-1"
    primeiro = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    antigo = {"Authorization": f"Bearer {primeiro['access_token']}"}

    # Liberar novo cadastro e so do admin.
    motivo = "Cadastro feito por outra pessoa"
    assert _liberar(cliente, organizador, event_id, participantes[0], motivo=motivo).status_code == 403
    assert _liberar(cliente, auth, event_id, participantes[0], motivo="abc").status_code == 422
    liberado = _liberar(cliente, auth, event_id, participantes[0], motivo=motivo)
    assert liberado.status_code == 200
    # A pulseira foi entregue pelo check-in: continua com o participante.
    assert liberado.json()["tem_conta"] is False and liberado.json()["pulseira"] == "P-1"
    assert cliente.get("/api/minha-area", headers=antigo).status_code == 401

    segundo = concluir(cliente, event_id, "00001")
    assert segundo.status_code == 200 and segundo.json()["conta_nova"] is False
    assert cliente.post(
        "/api/auth/login", json={"usuario": "00001", "senha": senha_de(participantes[0])}
    ).status_code == 200
    with session_scope() as db:
        assert db.scalar(select(func.count(User.id)).where(User.papel == "COLABORADOR")) == 1
        registro = db.scalar(select(AuditLog).where(AuditLog.acao == "cadastro_liberado"))
        assert registro.detalhes["motivo"] == "Cadastro feito por outra pessoa"
        assert registro.detalhes["pulseira_anterior"] == "P-1"


def test_liberar_so_vale_para_quem_ja_se_cadastrou(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    assert _liberar(cliente, auth, event_id, participantes[0]).status_code == 409


def test_conta_desativada_nao_e_reativada_pelo_autocadastro(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    resultado = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    with session_scope() as db:
        db.get(User, resultado["usuario"]["id"]).ativo = False
    _liberar(cliente, auth, event_id, participantes[0], motivo="Pedido de recadastro")

    assert identificar(cliente, event_id, "00001").status_code == 403


# ------------------------------------------------------------------ contas e concorrencia
def test_conta_da_equipe_com_a_matricula_recebe_o_cartao_sem_trocar_a_senha(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    # Conta de equipe cujo login e a matricula (ex.: admin que usa a propria matricula).
    equipe = conta("ADMIN", login="00001")
    with session_scope() as db:
        versao = db.get(User, equipe).sessao_versao

    previa = identificar(cliente, event_id, "00001")
    assert previa.status_code == 200 and previa.json()["login"] == "00001"
    assert previa.json()["conta_equipe"] is True

    resultado = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    # Nada de sessao nem dados da conta da equipe para quem so sabe nascimento e CPF.
    assert resultado["access_token"] is None and resultado["usuario"] is None
    assert resultado["login"] == "00001" and resultado["conta_equipe"] is True
    with session_scope() as db:
        assert db.get(Participant, participantes[0]).usuario_id == equipe
        conta_equipe = db.get(User, equipe)
        assert conta_equipe.papel == "ADMIN" and conta_equipe.sessao_versao == versao
        assert db.scalar(select(func.count(User.id)).where(User.papel == "COLABORADOR")) == 0
        assert db.scalar(select(AuditLog).where(AuditLog.acao == "autocadastro_concluido")).detalhes["conta"] == "equipe"

    # A senha continua a da equipe; os 5 digitos do CPF nao entram.
    assert cliente.post(
        "/api/auth/login", json={"usuario": "00001", "senha": senha_de(participantes[0])}
    ).status_code == 401
    entrada = cliente.post("/api/auth/login", json={"usuario": "00001", "senha": "senha-forte1"})
    assert entrada.status_code == 200 and entrada.json()["usuario"]["tem_cartao"] is True
    area = cliente.get("/api/minha-area", headers={"Authorization": f"Bearer {entrada.json()['access_token']}"})
    assert [p["matricula"] for p in area.json()["participacoes"]] == ["00001"]


def test_conta_da_equipe_desativada_nao_recebe_o_cartao(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    equipe = conta("RECEPCAO", login="00001")
    with session_scope() as db:
        db.get(User, equipe).ativo = False
    resultado = autocadastrar(cliente, auth, event_id, participantes[0], "00001")

    assert resultado["login"] == f"00001.e{event_id}" and resultado["conta_equipe"] is False
    assert resultado["usuario"]["id"] != equipe and resultado["access_token"]


def test_mesma_pessoa_em_outro_evento_reaproveita_a_conta(cliente, auth):
    primeiro, p1, _ = montar_evento(participantes=1)
    segundo, p2, _ = montar_evento(participantes=1)
    configurar_evento(primeiro)
    configurar_evento(segundo)
    a = autocadastrar(cliente, auth, primeiro, p1[0], "00001")
    b = autocadastrar(cliente, auth, segundo, p2[0], "00001")
    assert a["usuario"]["id"] == b["usuario"]["id"]
    area = cliente.get("/api/minha-area", headers={"Authorization": f"Bearer {b['access_token']}"})
    assert len(area.json()["participacoes"]) == 2


def test_mesma_matricula_com_nome_escrito_diferente_reaproveita_a_conta(cliente, auth):
    # A matricula e unica por pessoa: o nome diferente na planilha nao gera login ".e".
    primeiro, p1, _ = montar_evento(participantes=1)
    segundo, p2, _ = montar_evento(participantes=1)
    configurar_evento(primeiro)
    configurar_evento(segundo)
    with session_scope() as db:
        db.get(Participant, p1[0]).nome = "Everton Goncalves"
        db.get(Participant, p2[0]).nome = "EVERTON VIEIRA GONCALVES"
    a = autocadastrar(cliente, auth, primeiro, p1[0], "00001")
    b = autocadastrar(cliente, auth, segundo, p2[0], "00001")

    assert b["login"] == "00001" and a["usuario"]["id"] == b["usuario"]["id"]
    with session_scope() as db:
        assert db.get(User, b["usuario"]["id"]).nome == "EVERTON VIEIRA GONCALVES"
        assert db.scalar(select(func.count(User.id)).where(User.papel == "COLABORADOR")) == 1


def test_dois_aparelhos_com_o_mesmo_passe_so_um_conclui():
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    dar_identificacao(participantes[0])

    resultados: list[str] = []
    barreira = threading.Barrier(2)

    def tentar() -> None:
        barreira.wait()
        try:
            with session_scope() as db:
                evento = db.get(Event, event_id)
                participante = servico.participante_do_passe(db, evento, participantes[0])
                servico.concluir(
                    db,
                    evento,
                    participante,
                    ip="10.0.0.1",
                    nascimento=NASCIMENTO,
                    cinco_digitos=senha_de(participantes[0]),
                    foto=imagem(),
                )
            resultados.append("ok")
        except RegraDeNegocio:
            resultados.append("recusado")

    threads = [threading.Thread(target=tentar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(resultados) == ["ok", "recusado"]
    with session_scope() as db:
        assert db.scalar(select(func.count(User.id)).where(User.papel == "COLABORADOR")) == 1


def test_matricula_duplicada_no_evento_continua_recusada_com_ou_sem_zeros(cliente, auth):
    event_id, _participantes, _ = montar_evento(participantes=1)
    for matricula in ("00001", "1", "001"):
        resposta = cliente.post(
            f"/api/events/{event_id}/participantes",
            json={"nome": "Outra Pessoa", "matricula": matricula},
            headers=auth,
        )
        assert resposta.status_code == 409, matricula


def test_limpar_demo_libera_o_login_das_contas_de_demonstracao(cliente, auth):
    from app.seed import limpar_demo

    demo, participantes_demo, _ = montar_evento(participantes=1)
    real, participantes_reais, _ = montar_evento(participantes=1)
    configurar_evento(demo, demo=True)
    configurar_evento(real)
    conta_demo = autocadastrar(cliente, auth, demo, participantes_demo[0], "00001")["usuario"]["id"]

    assert limpar_demo() == 1
    with session_scope() as db:
        removida = db.get(User, conta_demo)
        assert removida.ativo is False and removida.usuario != "00001"
        assert db.get(Event, real) is not None
    # O participante real com a mesma matricula fica com o login "00001".
    assert autocadastrar(cliente, auth, real, participantes_reais[0], "00001")["login"] == "00001"
