"""Portal do Colaborador: importacao com CPF/nascimento, QR Code, foto e push."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from openpyxl import Workbook
from PIL import Image
from sqlalchemy import func, select, update

from app.config import settings
from app.database import session_scope
from app.models import AuditLog, InscricaoPush, Notificacao, Participant, utcnow
from app.services import identificacao, push
from app.texto import normalizar_matricula
from apoio import (
    autocadastrar,
    cabecalho,
    configurar_evento,
    conta,
    cpf_valido,
    imagem,
)
from conftest import montar_evento

CPF_A = "52998224725"
CPF_B = "11144477735"


# ------------------------------------------------------------------ normalizacao
@pytest.mark.parametrize(
    ("bruta", "normalizada"),
    [("00026", "26"), ("026", "26"), ("26", "26"), (" 0 0026 ", "26"), ("000", "0"), ("a-0042", "A-0042")],
)
def test_normalizacao_da_matricula(bruta, normalizada):
    assert normalizar_matricula(bruta) == normalizada


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("529.982.247-25", CPF_A),
        ("52998224725", CPF_A),
        (52998224725, CPF_A),
        # Excel guardou como numero e perdeu o zero a esquerda.
        (int(cpf_valido(12_345_678)), cpf_valido(12_345_678)),
        ("01234567891", None),
        ("111.111.111-11", None),
        ("529.982.247-24", None),
        ("", None),
    ],
)
def test_cpf_valida_digitos_verificadores(valor, esperado):
    assert identificacao.normalizar_cpf(valor) == esperado


@pytest.mark.parametrize(
    ("valor", "valido"),
    [("15/03/1990", True), ("1990-03-15", True), ("1990-03-15 00:00:00", True), ("32947", True),
     ("15/03/90", False), ("31/02/1990", False), ("01/01/1890", False), ("01/01/2999", False), ("abc", False)],
)
def test_data_de_nascimento(valor, valido):
    assert (identificacao.normalizar_nascimento(valor) is not None) is valido


# ------------------------------------------------------------------ importacao
def _csv(linhas: list[list[str]]) -> bytes:
    corpo = ["nome;matricula;setor;data_nascimento;cpf"] + [";".join(map(str, l)) for l in linhas]
    return ("\r\n".join(corpo) + "\r\n").encode("utf-8")


def _previa(cliente, auth, event_id: int, conteudo: bytes, nome: str = "lista.csv") -> dict:
    resposta = cliente.post(
        f"/api/events/{event_id}/participantes/importar/previa",
        files={"arquivo": (nome, conteudo, "application/octet-stream")},
        headers=auth,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _confirmar(cliente, auth, event_id: int, linhas: list[dict], **opcoes):
    return cliente.post(
        f"/api/events/{event_id}/participantes/importar/confirmar",
        json={"linhas": linhas, **opcoes},
        headers=auth,
    )


def test_importacao_valida_cpf_nascimento_e_duplicidades(cliente, auth):
    event_id, _p, _ = montar_evento(participantes=1)  # ja existe a matricula 00001
    previa = _previa(cliente, auth, event_id, _csv([
        ["Ana Souza", "000200", "TI", "15/03/1990", "529.982.247-25"],
        ["Bia Lima", "200", "TI", "02/11/1985", CPF_B],            # mesma matricula (sem zeros)
        ["Caio Reis", "000201", "TI", "02/11/1985", "52998224725"],  # CPF repetido na planilha
        ["Davi Melo", "000202", "TI", "31/02/1990", cpf_valido(1)],  # data invalida
        ["Eva Dias", "000203", "TI", "01/01/1990", "123.456.789-00"],  # CPF invalido
        ["Fabi Luz", "000204", "TI", "", ""],                        # sem identificacao: aceito
        ["Gil Rosa", "000205", "TI", "01/01/1990", ""],              # so um dos dois
        ["Participante 1", "1", "Geral", "01/01/1980", cpf_valido(2)],  # ja existe (00001)
    ]))
    linhas = {l["matricula"]: l for l in previa["linhas"]}
    assert linhas["000200"]["erros"] == [] and linhas["000200"]["tem_identificacao"] is True
    assert any("Matricula repetida" in e for e in linhas["200"]["erros"])
    assert any("CPF repetido na planilha" in e for e in linhas["000201"]["erros"])
    assert any("nascimento inválida" in e for e in linhas["000202"]["erros"])
    assert any("CPF inválido" in e for e in linhas["000203"]["erros"])
    assert linhas["000204"]["erros"] == [] and linhas["000204"]["tem_identificacao"] is False
    assert linhas["000205"]["erros"] and linhas["000205"]["codigo_identificacao"] is None
    assert linhas["1"]["ja_existe_no_evento"] is True
    assert previa["com_identificacao"] == 2  # 000200 e "1"
    # O CPF e a data nunca voltam ao navegador.
    texto = str(previa)
    assert "52998224725" not in texto and "529.982" not in texto and "1990" not in texto


def test_importacao_grava_so_codigos_e_nao_substitui_sem_autorizacao(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=1)
    previa = _previa(cliente, auth, event_id, _csv([
        ["Ana Souza", "000200", "TI", "15/03/1990", CPF_A],
        ["Nome Novo", "1", "Novo Setor", "02/11/1985", CPF_B],  # ja existe como 00001
    ]))
    validas = [l for l in previa["linhas"] if not l["erros"]]

    resultado = _confirmar(cliente, auth, event_id, validas).json()
    assert resultado == {"criados": 1, "atualizados": 0, "identificacoes_atualizadas": 0, "ignorados": 1}
    with session_scope() as db:
        existente = db.get(Participant, participantes[0])
        assert existente.nome == "Participante 1" and existente.identificacao_hash is None
        nova = db.scalar(select(Participant).where(Participant.matricula == "000200"))
        assert nova.identificacao_hash and nova.cpf_hash and CPF_A not in nova.cpf_hash
        assert nova.matricula_normalizada == "200"
        auditoria = db.scalar(select(AuditLog).where(AuditLog.acao == "participantes_importados"))
        assert CPF_A not in str(auditoria.detalhes) and nova.cpf_hash not in str(auditoria.detalhes)

    # Com autorizacao: completa so a identificacao, sem mexer no nome.
    resultado = _confirmar(cliente, auth, event_id, validas, atualizar_identificacao=True).json()
    assert resultado["identificacoes_atualizadas"] == 2
    with session_scope() as db:
        existente = db.get(Participant, participantes[0])
        assert existente.nome == "Participante 1" and existente.identificacao_hash is not None


def test_cpf_de_outra_matricula_no_evento_e_recusado(cliente, auth):
    event_id, _p, _ = montar_evento(participantes=0)
    primeira = _previa(cliente, auth, event_id, _csv([["Ana Souza", "000200", "TI", "15/03/1990", CPF_A]]))
    _confirmar(cliente, auth, event_id, primeira["linhas"])
    segunda = _previa(cliente, auth, event_id, _csv([["Outra Pessoa", "000300", "TI", "15/03/1990", CPF_A]]))
    assert "CPF já cadastrado para outra matrícula neste evento" in segunda["linhas"][0]["erros"]
    # Mesmo enviando os codigos a mao, o banco recusa CPF repetido.
    forjada = {**segunda["linhas"][0], "erros": []}
    forjada["codigo_identificacao"] = "a" * 64
    forjada["codigo_cpf"] = identificacao.codigo_cpf(CPF_A)
    resposta = _confirmar(cliente, auth, event_id, [forjada])
    assert resposta.status_code == 409 and "CPF" in resposta.json()["detail"]


def test_importacao_xlsx_com_datas_e_cpf_numericos(cliente, auth):
    from datetime import datetime

    event_id, _p, _ = montar_evento(participantes=0)
    wb = Workbook()
    ws = wb.active
    ws.append(["Nome completo", "Matrícula", "Data de nascimento", "CPF"])
    ws.append(["Ana Souza", "00026", datetime(1990, 3, 15), 52998224725])
    ws.append(["Bia Lima", "00027", 32947, "011.444.777-35"])  # serial do Excel; DV invalido
    buffer = io.BytesIO()
    wb.save(buffer)
    previa = _previa(cliente, auth, event_id, buffer.getvalue(), "lista.xlsx")
    ana, bia = previa["linhas"]
    assert ana["erros"] == [] and ana["tem_identificacao"] is True
    assert ana["codigo_identificacao"] == identificacao.codigo_identificacao(
        identificacao.normalizar_nascimento("15/03/1990"), "52998"
    )
    assert "CPF inválido" in bia["erros"]


def test_cabecalho_com_pontuacao_e_codigo_no_lugar_da_matricula(cliente, auth):
    """Formato real da planilha do RH: Código | Nome | CPF: | Data de Nascimento (sem setor)."""
    from datetime import datetime

    event_id, _p, _ = montar_evento(participantes=0)
    wb = Workbook()
    ws = wb.active
    ws.append(["Código", "Nome", "CPF:", "Data de Nascimento"])
    ws.append(["004581", "Ana Souza", "52998224725", datetime(1990, 3, 15)])
    for _ in range(1500):  # linhas "formatadas" vazias no fim
        ws.append([None, None, None, None])
    ws.append(["009999", "Depois do Vazio", CPF_B, datetime(1990, 1, 1)])
    buffer = io.BytesIO()
    wb.save(buffer)
    previa = _previa(cliente, auth, event_id, buffer.getvalue(), "rh.xlsx")
    assert previa["total_linhas"] == 1  # parou depois de 1000 linhas vazias seguidas
    [linha] = previa["linhas"]
    assert linha["matricula"] == "004581" and linha["setor"] == ""
    assert linha["erros"] == [] and linha["tem_identificacao"] is True


def test_planilha_com_so_uma_coluna_de_identificacao_explica_o_que_falta(cliente, auth):
    event_id, _p, _ = montar_evento(participantes=0)
    resposta = cliente.post(
        f"/api/events/{event_id}/participantes/importar/previa",
        files={"arquivo": ("x.csv", "Código;Nome;Nascimento\r\n1;Ana Souza;15/03/1990\r\n".encode(), "text/csv")},
        headers=auth,
    )
    assert resposta.status_code == 422
    assert "falta a coluna de CPF" in resposta.json()["detail"]


def test_modelo_da_planilha_tem_as_novas_colunas(cliente, auth):
    texto = cliente.get("/api/participantes/modelo.csv", headers=auth).content.decode("utf-8-sig")
    assert texto.splitlines()[0] == "nome;matricula;setor;data_nascimento;cpf"


# ------------------------------------------------------------------ QR Code
def test_qrcode_aponta_para_o_cadastro_do_evento(cliente, auth, monkeypatch):
    event_id, participantes, _ = montar_evento(participantes=2)
    configurar_evento(event_id)
    monkeypatch.setattr(settings, "url_publica", "https://sorteio.exemplo.com.br/")
    situacao = cliente.get(f"/api/events/{event_id}/portal", headers=auth).json()
    assert situacao["url_cadastro"] == f"https://sorteio.exemplo.com.br/evento/{event_id}/cadastro"
    assert situacao["fonte_endereco"] == "configurada" and situacao["aberto"] is True
    assert situacao["participantes"] == 2 and situacao["com_identificacao"] == 0

    png = cliente.get(f"/api/events/{event_id}/portal/qrcode.png", headers=auth)
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(png.content)).size[0] > 200

    # Sem URL_PUBLICA: o endereco vem do navegador (localhost vira o IP da rede).
    monkeypatch.setattr(settings, "url_publica", "")
    situacao = cliente.get(
        f"/api/events/{event_id}/portal", params={"origem": "http://192.168.0.50:8000"}, headers=auth
    ).json()
    assert situacao["url_cadastro"] == f"http://192.168.0.50:8000/evento/{event_id}/cadastro"
    invalida = cliente.get(
        f"/api/events/{event_id}/portal", params={"origem": "javascript:alert(1)"}, headers=auth
    ).json()
    assert invalida["url_cadastro"].startswith("http") and "javascript" not in invalida["url_cadastro"]


# ------------------------------------------------------------------ Meu Perfil: foto
def test_colaborador_troca_e_remove_a_propria_foto(cliente, auth):
    event_id, participantes, _ = montar_evento(participantes=2)
    configurar_evento(event_id)
    a = autocadastrar(cliente, auth, event_id, participantes[0], "00001")
    b = autocadastrar(cliente, auth, event_id, participantes[1], "00002", enviar_foto=False)
    cab_a = {"Authorization": f"Bearer {a['access_token']}"}
    cab_b = {"Authorization": f"Bearer {b['access_token']}"}
    with session_scope() as db:
        antiga = db.get(Participant, participantes[0]).foto_url

    nova = cliente.post(
        f"/api/minha-area/{event_id}/foto", files={"foto": ("n.png", imagem("PNG"), "image/png")}, headers=cab_a
    )
    assert nova.status_code == 200 and nova.json()["foto_url"].endswith(".png")
    assert not (settings.upload_dir / antiga.rsplit("/", 1)[1]).exists()  # antiga apagada
    falsa = cliente.post(
        f"/api/minha-area/{event_id}/foto", files={"foto": ("x.jpg", b"nao sou imagem", "image/jpeg")}, headers=cab_a
    )
    assert falsa.status_code == 422

    removida = cliente.delete(f"/api/minha-area/{event_id}/foto", headers=cab_a)
    assert removida.status_code == 200 and removida.json()["foto_url"] is None

    # B nao tem como mexer na foto de A: so existe a rota da propria participacao.
    outro_evento, _p, _ = montar_evento(participantes=1)
    assert cliente.delete(f"/api/minha-area/{outro_evento}/foto", headers=cab_b).status_code == 404
    with session_scope() as db:
        acoes = db.scalars(select(AuditLog.acao).where(AuditLog.acao == "foto_alterada")).all()
    assert len(acoes) == 2


# ------------------------------------------------------------------ push
@pytest.fixture
def push_ativo(monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "mailto:responsavel@exemplo.com.br")


class Enviador:
    def __init__(self, status: int = 201) -> None:
        self.status = status
        self.envios: list[tuple[str, dict]] = []

    def __call__(self, inscricao, carga) -> int:
        self.envios.append((inscricao.endpoint, carga))
        return self.status


def _inscrever(cliente, cab, sufixo: str = "a"):
    return cliente.post(
        "/api/minha-area/push/inscricao",
        json={"endpoint": f"https://push.exemplo.com/{sufixo}", "p256dh": "B" * 87, "auth": "A" * 22},
        headers=cab,
    )


def _sortear(cliente, auth, event_id: int, unidade: int, chave: str = "k1") -> dict:
    resposta = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidade, "idempotency_key": f"chave-portal-{chave}"},
        headers=auth,
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _revelar() -> None:
    with session_scope() as db:
        db.execute(update(Notificacao).values(disponivel_em=utcnow() - timedelta(seconds=1)))


def test_sem_https_o_push_fica_indisponivel_e_o_portal_funciona(cliente, auth, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "")
    monkeypatch.setattr(settings, "url_publica", "http://192.168.0.10:8000")
    event_id, participantes, _ = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[0], '00001')['access_token']}"}
    situacao = cliente.get("/api/minha-area/push", headers=cab).json()
    assert situacao["disponivel"] is False and "HTTPS" in situacao["motivo"]
    assert _inscrever(cliente, cab).status_code == 409
    assert push.enviar_pendentes(Enviador()) == 0


def test_push_so_depois_da_revelacao_uma_vez_e_so_para_o_ganhador(cliente, auth, push_ativo):
    event_id, participantes, unidades = montar_evento(participantes=2, presentes=1)
    configurar_evento(event_id)
    ganhador = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[0], '00001')['access_token']}"}
    outro = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[1], '00002')['access_token']}"}
    situacao = cliente.get("/api/minha-area/push", headers=ganhador).json()
    assert situacao["disponivel"] is True and len(situacao["chave_publica"]) > 80
    assert _inscrever(cliente, ganhador, "ganhador").status_code == 200
    assert _inscrever(cliente, outro, "outro").status_code == 200

    sorteio = _sortear(cliente, auth, event_id, unidades[0])  # so o participante 1 esta presente
    enviador = Enviador()
    # Resultado provisorio (telao ainda animando): nada sai.
    assert push.enviar_pendentes(enviador) == 0 and enviador.envios == []

    _revelar()
    assert push.enviar_pendentes(enviador) == 1
    [(endpoint, carga)] = enviador.envios
    assert endpoint == "https://push.exemplo.com/ganhador"
    assert carga["titulo"] == "🎉 Parabéns! Você foi sorteado!"
    assert carga["mensagem"] == (
        "Seu número da sorte foi contemplado no Sorteio Empresa Teste. "
        "Acesse seu cartão para conferir o prêmio."
    )
    # Nada de nome de premio ou dado pessoal na tela bloqueada.
    assert "Premio Teste" not in str(carga) and "00001" not in str(carga)

    # Telao reapresenta o resultado / servidor reinicia: nao reenvia.
    reapresentar = cliente.post(
        f"/api/events/{event_id}/telao",
        json={"estado": "resultado", "prize_unit_id": unidades[0]},
        headers=auth,
    )
    assert reapresentar.status_code == 200, reapresentar.text
    assert push.enviar_pendentes(enviador) == 0 and len(enviador.envios) == 1
    with session_scope() as db:
        assert db.scalar(select(func.count(Notificacao.id))) == 1
        assert db.scalar(select(Notificacao.push_enviado_em)) is not None
    assert sorteio["id"]


def test_resultado_anulado_antes_da_revelacao_nao_gera_push(cliente, auth, push_ativo):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[0], '00001')['access_token']}"}
    _inscrever(cliente, cab)
    sorteio = _sortear(cliente, auth, event_id, unidades[0])
    anulado = cliente.post(
        f"/api/events/{event_id}/sorteios/{sorteio['id']}/anular",
        json={"motivo": "Erro do operador no palco", "tipo": "erro_operacional"},
        headers=auth,
    )
    assert anulado.status_code == 200, anulado.text
    _revelar()
    enviador = Enviador()
    assert push.enviar_pendentes(enviador) == 0 and enviador.envios == []


def test_inscricao_expirada_e_removida_e_desativar_funciona(cliente, auth, push_ativo):
    event_id, participantes, unidades = montar_evento(participantes=1)
    configurar_evento(event_id)
    cab = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[0], '00001')['access_token']}"}
    _inscrever(cliente, cab, "velha")
    _inscrever(cliente, cab, "nova")
    assert cliente.get("/api/minha-area/push", headers=cab).json()["aparelhos"] == 2

    _sortear(cliente, auth, event_id, unidades[0])
    _revelar()
    assert push.enviar_pendentes(Enviador(status=410)) == 0
    with session_scope() as db:
        assert db.scalar(select(func.count(InscricaoPush.id))) == 0  # 410 = inscricao vencida

    _inscrever(cliente, cab, "nova")
    desativado = cliente.post(
        "/api/minha-area/push/cancelar", json={"endpoint": "https://push.exemplo.com/nova"}, headers=cab
    )
    assert desativado.status_code == 200 and desativado.json()["aparelhos"] == 0


def test_inscricao_de_outra_conta_nao_e_cancelada_por_terceiros(cliente, auth, push_ativo):
    event_id, participantes, _ = montar_evento(participantes=2)
    configurar_evento(event_id)
    a = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[0], '00001')['access_token']}"}
    b = {"Authorization": f"Bearer {autocadastrar(cliente, auth, event_id, participantes[1], '00002')['access_token']}"}
    _inscrever(cliente, a, "aparelho-a")
    cliente.post("/api/minha-area/push/cancelar", json={"endpoint": "https://push.exemplo.com/aparelho-a"}, headers=b)
    assert cliente.get("/api/minha-area/push", headers=a).json()["aparelhos"] == 1
    # Endpoint que nao e https e recusado.
    ruim = cliente.post(
        "/api/minha-area/push/inscricao",
        json={"endpoint": "http://inseguro.exemplo/x", "p256dh": "B" * 87, "auth": "A" * 22},
        headers=a,
    )
    assert ruim.status_code == 422


def test_equipe_sem_cadastro_ve_area_pessoal_vazia(cliente):
    """A equipe tambem pode ser participante; sem cadastro, a area vem vazia."""
    cab = cabecalho(conta("RECEPCAO"))
    area = cliente.get("/api/minha-area", headers=cab)
    assert area.status_code == 200 and area.json()["participacoes"] == []
    assert cliente.get("/api/auth/me", headers=cab).json()["tem_cartao"] is False
