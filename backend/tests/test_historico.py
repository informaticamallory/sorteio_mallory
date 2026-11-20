"""Fase 3: pesquisa, filtros, paginacao, detalhe e exportacao do historico."""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.database import session_scope
from app.models import (
    BlocoSorteio,
    DisplayState,
    Draw,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    User,
)
from app.security import hash_senha, novo_token_telao
from conftest import montar_evento

SP = ZoneInfo("America/Sao_Paulo")  # UTC-3
MANAUS = ZoneInfo("America/Manaus")  # UTC-4


def _utc(local: datetime, zona: ZoneInfo = SP) -> datetime:
    """Horario local do evento -> UTC sem tzinfo, como o banco grava."""
    return local.replace(tzinfo=zona).astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def cenario() -> dict:
    """Historico conhecido em dois eventos.

    Rodadas do evento A (Sao Paulo):
      1  Jose da Conceicao  Camera #1  valido, entregue   12/12 22:30  bloco 1  organizador
      2  Maria de Souza     Smart TV   anulado (ausencia) 13/12 10:00  bloco 1  Ana
      3  Pedro Alvares      Smart TV   valido, pendente   13/12 10:05  bloco 1  Ana  (resorteio de 2)
      4  Maria de Souza     Camera #2  anulado c/ estorno 14/12 09:00  sem bloco
      5  Maria de Souza     Kit_...    valido, pendente   14/12 09:30  sem bloco
    Evento B (Manaus): rodada 1, Jose Antonio, Bicicleta, valido, entregue, 10/12/2025 20:00.
    """
    with session_scope() as db:
        organizador = db.scalar(select(User).where(User.usuario == "organizador"))
        ana = User(usuario="ana", nome="Ana Operadora", senha_hash=hash_senha("x"), papel="ADMIN")
        db.add(ana)

        a = Event(nome="Festa 2026", telao_token=novo_token_telao(), fuso_horario="America/Sao_Paulo")
        b = Event(nome="Festa 2025", telao_token=novo_token_telao(), fuso_horario="America/Manaus")
        db.add_all([a, b])
        db.flush()

        jose = Participant(event_id=a.id, nome="José da Conceição", matricula="00042", pulseira="A-0042", setor="TI")
        maria = Participant(event_id=a.id, nome="Maria de Souza", matricula="00123", pulseira="0100", setor="RH")
        pedro = Participant(event_id=a.id, nome="Pedro Álvares", matricula="10042", setor="Vendas")
        jose_b = Participant(event_id=b.id, nome="José Antônio", matricula="00042", setor="TI")
        db.add_all([jose, maria, pedro, jose_b])

        camera = Prize(event_id=a.id, nome="Câmera Fotográfica", quantidade=2, ordem=1)
        tv = Prize(event_id=a.id, nome='Smart TV 50"', quantidade=1, ordem=2)
        kit = Prize(event_id=a.id, nome="Kit_Churrasco 100%", quantidade=1, ordem=3)
        bike = Prize(event_id=b.id, nome="Bicicleta", quantidade=1, ordem=1)
        db.add_all([camera, tv, kit, bike])
        db.flush()

        u_cam1 = PrizeUnit(prize_id=camera.id, numero=1, status="entregue")
        u_cam2 = PrizeUnit(prize_id=camera.id, numero=2, status="disponivel")
        u_tv = PrizeUnit(prize_id=tv.id, numero=1, status="sorteado")
        u_kit = PrizeUnit(prize_id=kit.id, numero=1, status="sorteado")
        u_bike = PrizeUnit(prize_id=bike.id, numero=1, status="entregue")
        db.add_all([u_cam1, u_cam2, u_tv, u_kit, u_bike])
        db.flush()

        bloco = BlocoSorteio(event_id=a.id, numero=1, nome="Bloco 01", status="FINALIZADO")
        db.add(bloco)
        db.flush()

        def sorteio(evento, unidade, ganhador, rodada, quando, operador, **extra):
            d = Draw(
                event_id=evento.id,
                prize_unit_id=unidade.id,
                participant_id=ganhador.id,
                rodada=rodada,
                idempotency_key=f"cenario-{evento.id}-{rodada}",
                elegiveis_ids=[],
                elegiveis_total=4,
                indice_sorteado=0,
                criado_em=quando,
                criado_por_id=operador.id,
                **extra,
            )
            db.add(d)
            db.flush()
            return d

        d1 = sorteio(a, u_cam1, jose, 1, _utc(datetime(2026, 12, 12, 22, 30)), organizador,
                     bloco_id=bloco.id, entregue=True, entregue_em=_utc(datetime(2026, 12, 12, 23, 0)),
                     entregue_por_id=organizador.id)
        d2 = sorteio(a, u_tv, maria, 2, _utc(datetime(2026, 12, 13, 10, 0)), ana, bloco_id=bloco.id,
                     status="anulado", tipo_anulacao="ausencia", motivo_anulacao="Ausente no palco",
                     anulado_em=_utc(datetime(2026, 12, 13, 10, 2)), anulado_por_id=ana.id)
        d3 = sorteio(a, u_tv, pedro, 3, _utc(datetime(2026, 12, 13, 10, 5)), ana, bloco_id=bloco.id,
                     draw_anterior_id=d2.id)
        d4 = sorteio(a, u_cam2, maria, 4, _utc(datetime(2026, 12, 14, 9, 0)), organizador,
                     status="anulado", tipo_anulacao="erro_operacional", motivo_anulacao="Entregue errado",
                     estorno_entrega=True, entregue_em=_utc(datetime(2026, 12, 14, 9, 5)),
                     entregue_por_id=organizador.id, anulado_por_id=organizador.id,
                     anulado_em=_utc(datetime(2026, 12, 14, 9, 10)))
        d5 = sorteio(a, u_kit, maria, 5, _utc(datetime(2026, 12, 14, 9, 30)), organizador)
        d6 = sorteio(b, u_bike, jose_b, 1, _utc(datetime(2025, 12, 10, 20, 0), MANAUS), organizador,
                     entregue=True, entregue_em=_utc(datetime(2025, 12, 10, 21, 0), MANAUS),
                     entregue_por_id=organizador.id)

        return {
            "a": a.id, "b": b.id, "bloco": bloco.id, "ana": ana.id, "org": organizador.id,
            "d": {1: d1.id, 2: d2.id, 3: d3.id, 4: d4.id, 5: d5.id, 6: d6.id},
        }


def _buscar(cliente, auth, **params) -> dict:
    resposta = cliente.get("/api/sorteios", params=params, headers=auth)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _ids(cliente, auth, **params) -> set[int]:
    return {item["id"] for item in _buscar(cliente, auth, por_pagina=100, **params)["itens"]}


def _esperado(cenario, *rodadas) -> set[int]:
    return {cenario["d"][r] for r in rodadas}


# ------------------------------------------------------------------ pesquisa
@pytest.mark.parametrize("termo", ["jose", "JOSÉ", "Conceição", "conceicao", "da concei"])
def test_nome_parcial_sem_acento_e_sem_caixa(cliente, auth, cenario, termo):
    assert _ids(cliente, auth, q=termo, event_id=cenario["a"]) == _esperado(cenario, 1)


def test_varias_palavras_combinam(cliente, auth, cenario):
    assert _ids(cliente, auth, q="maria souza", event_id=cenario["a"]) == _esperado(cenario, 2, 4, 5)
    assert _ids(cliente, auth, q="souza camera", event_id=cenario["a"]) == _esperado(cenario, 4)


def test_busca_sem_evento_percorre_todos_os_eventos(cliente, auth, cenario):
    assert _ids(cliente, auth, q="jose") == _esperado(cenario, 1, 6)


def test_matricula_com_zeros_a_esquerda(cliente, auth, cenario):
    resultado = _buscar(cliente, auth, q="00042", event_id=cenario["a"])
    assert {i["id"] for i in resultado["itens"]} == _esperado(cenario, 1)  # "10042" nao entra
    assert resultado["itens"][0]["ganhador_matricula"] == "00042"


def test_matricula_parcial(cliente, auth, cenario):
    # "42" esta em "00042" (Jose) e em "10042" (Pedro).
    assert _ids(cliente, auth, q="42", event_id=cenario["a"]) == _esperado(cenario, 1, 3)


def test_pulseira(cliente, auth, cenario):
    resultado = _buscar(cliente, auth, q="a-0042")
    assert {i["id"] for i in resultado["itens"]} == _esperado(cenario, 1)
    assert resultado["itens"][0]["ganhador_pulseira"] == "A-0042"
    assert _ids(cliente, auth, q="0100") == _esperado(cenario, 2, 4, 5)


def test_nome_do_premio_sem_acento(cliente, auth, cenario):
    assert _ids(cliente, auth, q="camera fotografica") == _esperado(cenario, 1, 4)


@pytest.mark.parametrize(
    "termo,rodadas",
    [
        # Como curinga, "%" e "_" trariam TODOS os resultados. Literais, so o
        # premio que contem o caractere: "Kit_Churrasco 100%".
        ("%", (5,)),
        ("_", (5,)),
        ("100%", (5,)),
        ("kit_churrasco", (5,)),
        # Sem escape, "1%0" casaria com "100"; literal, nao casa com nada.
        ("1%0", ()),
        ("kit_c_urrasco", ()),
    ],
    ids=["porcento", "sublinhado", "porcento-no-fim", "sublinhado-no-meio", "porcento-no-meio", "sublinhado-como-letra"],
)
def test_curingas_do_like_sao_literais(cliente, auth, cenario, termo, rodadas):
    assert _ids(cliente, auth, q=termo) == _esperado(cenario, *rodadas)


def test_termo_inexistente(cliente, auth, cenario):
    resultado = _buscar(cliente, auth, q="ninguem com esse nome")
    assert resultado["total"] == 0
    assert resultado["itens"] == []


# ------------------------------------------------------------------ filtros
@pytest.mark.parametrize(
    "filtro,rodadas",
    [
        ({"status": "anulado"}, (2, 4)),
        ({"status": "valido"}, (1, 3, 5)),
        ({"entrega": "entregue"}, (1,)),
        ({"entrega": "pendente"}, (3, 5)),
        ({"entrega": "estornado"}, (4,)),
        ({"sem_bloco": "true"}, (4, 5)),
    ],
    ids=["anulados", "validos", "entregues", "pendentes", "estornados", "sem-bloco"],
)
def test_filtros_simples(cliente, auth, cenario, filtro, rodadas):
    assert _ids(cliente, auth, event_id=cenario["a"], **filtro) == _esperado(cenario, *rodadas)


def test_filtro_por_bloco(cliente, auth, cenario):
    resultado = _buscar(cliente, auth, bloco_id=cenario["bloco"])
    assert {i["id"] for i in resultado["itens"]} == _esperado(cenario, 1, 2, 3)
    assert {i["bloco_numero"] for i in resultado["itens"]} == {1}


def test_filtro_por_operador(cliente, auth, cenario):
    assert _ids(cliente, auth, operador_id=cenario["ana"]) == _esperado(cenario, 2, 3)


def test_filtro_por_evento(cliente, auth, cenario):
    assert _ids(cliente, auth, event_id=cenario["b"]) == _esperado(cenario, 6)


@pytest.mark.parametrize(
    "inicio,fim,rodadas",
    [
        # 22:30 de 12/12 em Sao Paulo ja e 13/12 em UTC: a data segue o fuso do evento.
        ("2026-12-12", "2026-12-12", (1,)),
        ("2026-12-13", "2026-12-13", (2, 3)),
        ("2026-12-13", "2026-12-14", (2, 3, 4, 5)),
        ("2026-12-15", None, ()),
        (None, "2026-12-12", (1,)),
    ],
)
def test_filtro_por_data_no_fuso_do_evento(cliente, auth, cenario, inicio, fim, rodadas):
    params = {"event_id": cenario["a"]}
    if inicio:
        params["data_inicio"] = inicio
    if fim:
        params["data_fim"] = fim
    assert _ids(cliente, auth, **params) == _esperado(cenario, *rodadas)


def test_filtros_combinados(cliente, auth, cenario):
    assert _ids(
        cliente, auth, event_id=cenario["a"], q="maria", status="valido", sem_bloco="true"
    ) == _esperado(cenario, 5)
    assert _ids(
        cliente,
        auth,
        event_id=cenario["a"],
        bloco_id=cenario["bloco"],
        operador_id=cenario["ana"],
        entrega="pendente",
        data_inicio="2026-12-13",
        data_fim="2026-12-13",
    ) == _esperado(cenario, 3)


@pytest.mark.parametrize(
    "params",
    [
        {"por_pagina": 101},
        {"pagina": 0},
        {"ordenar": "senha"},
        {"direcao": "lado"},
        {"status": "talvez"},
        {"entrega": "quase"},
        {"data_inicio": "2026-12-14", "data_fim": "2026-12-13"},
        {"data_inicio": "13/12/2026"},
    ],
    ids=["por-pagina", "pagina-zero", "ordenar", "direcao", "status", "entrega", "datas-invertidas", "data-formato"],
)
def test_parametros_invalidos(cliente, auth, cenario, params):
    assert cliente.get("/api/sorteios", params=params, headers=auth).status_code == 422


# ------------------------------------------------------------------ ordenacao e paginacao
def test_ordenacao(cliente, auth, cenario):
    padrao = [i["rodada"] for i in _buscar(cliente, auth, event_id=cenario["a"])["itens"]]
    assert padrao == [5, 4, 3, 2, 1]  # mais recentes primeiro
    por_rodada = _buscar(cliente, auth, event_id=cenario["a"], ordenar="rodada", direcao="asc")
    assert [i["rodada"] for i in por_rodada["itens"]] == [1, 2, 3, 4, 5]
    por_nome = _buscar(cliente, auth, event_id=cenario["a"], ordenar="ganhador", direcao="asc")
    assert [i["ganhador_nome"] for i in por_nome["itens"]][0] == "José da Conceição"
    assert [i["ganhador_nome"] for i in por_nome["itens"]][-1] == "Pedro Álvares"


def test_paginacao_no_servidor(cliente, auth):
    with session_scope() as db:
        organizador = db.scalar(select(User).where(User.usuario == "organizador"))
        evento = Event(nome="Muitos", telao_token=novo_token_telao())
        db.add(evento)
        db.flush()
        premio = Prize(event_id=evento.id, nome="Brinde", quantidade=30, ordem=1)
        db.add(premio)
        db.flush()
        inicio = datetime(2026, 12, 1, 12, 0)
        for i in range(30):
            p = Participant(event_id=evento.id, nome=f"Pessoa {i:02d}", matricula=f"{i:05d}")
            u = PrizeUnit(prize_id=premio.id, numero=i + 1, status="sorteado")
            db.add_all([p, u])
            db.flush()
            db.add(
                Draw(event_id=evento.id, prize_unit_id=u.id, participant_id=p.id, rodada=i + 1,
                     idempotency_key=f"pag-{i:04d}", elegiveis_ids=[], elegiveis_total=30,
                     indice_sorteado=0, criado_em=inicio + timedelta(minutes=i),
                     criado_por_id=organizador.id)
            )
        event_id = evento.id

    paginas = [
        _buscar(cliente, auth, event_id=event_id, pagina=n, por_pagina=10) for n in (1, 2, 3, 4)
    ]
    assert [p["total"] for p in paginas] == [30, 30, 30, 30]
    assert paginas[0]["paginas"] == 3
    assert [len(p["itens"]) for p in paginas] == [10, 10, 10, 0]
    rodadas = [i["rodada"] for p in paginas[:3] for i in p["itens"]]
    assert rodadas == list(range(30, 0, -1))  # sem repetir nem pular


# ------------------------------------------------------------------ conteudo e privacidade
def test_linha_traz_os_campos_da_tabela(cliente, auth, cenario):
    (item,) = _buscar(cliente, auth, q="a-0042")["itens"]
    assert item["ganhador_nome"] == "José da Conceição"
    assert item["ganhador_matricula"] == "00042"
    assert item["ganhador_pulseira"] == "A-0042"
    assert item["premio_nome"] == "Câmera Fotográfica"
    assert (item["bloco_numero"], item["bloco_nome"]) == (1, "Bloco 01")
    assert item["evento_nome"] == "Festa 2026"
    assert item["criado_por"] == "Organizador"
    assert item["entregue"] is True


@pytest.mark.parametrize(
    "papel,consulta,exporta",
    [
        ("SORTEIO", True, False),
        ("ORGANIZADOR", True, True),
        ("RECEPCAO", False, False),
        ("COLABORADOR", False, False),
    ],
)
def test_rotas_do_historico_respeitam_o_perfil(cliente, cenario, papel, consulta, exporta):
    """Sorteador e organizador consultam resultados; so admin e organizador exportam."""
    login = f"u-{papel.lower()}"  # o login e sempre gravado em minusculas
    with session_scope() as db:
        db.add(User(usuario=login, nome=papel, senha_hash=hash_senha("senha-forte1"), papel=papel))
    token = cliente.post(
        "/api/auth/login", json={"usuario": login, "senha": "senha-forte1"}
    ).json()["access_token"]
    cabecalho = {"Authorization": f"Bearer {token}"}
    for url in (
        "/api/sorteios?q=jose",
        f"/api/sorteios/{cenario['d'][1]}",
        "/api/sorteios/operadores",
    ):
        assert (cliente.get(url, headers=cabecalho).status_code == 200) is consulta, url
        if not consulta:
            assert cliente.get(url, headers=cabecalho).status_code == 403, url
    for url in ("/api/sorteios/export.csv", "/api/sorteios/export.xlsx"):
        assert cliente.get(url, headers=cabecalho).status_code == (200 if exporta else 403), url
    assert cliente.get("/api/sorteios").status_code == 401


def test_detalhe_so_mostra_auditoria_para_quem_pode(cliente, auth, cenario):
    with session_scope() as db:
        db.add(User(usuario="op", nome="Op", senha_hash=hash_senha("senha-forte1"), papel="SORTEIO"))
    token = cliente.post("/api/auth/login", json={"usuario": "op", "senha": "senha-forte1"}).json()[
        "access_token"
    ]
    # O cenario e inserido direto no banco (sem auditoria); gera um registro real:
    cliente.post(
        f"/api/events/{cenario['a']}/sorteios/{cenario['d'][5]}/entrega",
        json={"entregue": True},
        headers=auth,
    )
    url = f"/api/sorteios/{cenario['d'][5]}"
    assert cliente.get(url, headers=auth).json()["auditoria"] != []
    assert cliente.get(url, headers={"Authorization": f"Bearer {token}"}).json()["auditoria"] == []


def test_telao_publico_continua_sem_dados_pessoais(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=2)
    with session_scope() as db:
        db.get(Participant, ids[0]).pulseira = "P-0001"
        db.get(Participant, ids[1]).pulseira = "P-0002"
        token = db.get(Event, event_id).telao_token
    cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "privado-0001"},
        headers=auth,
    )
    with session_scope() as db:
        db.get(DisplayState, event_id).revelar_em = datetime(2000, 1, 1)
    bruto = cliente.get(f"/api/public/{token}/estado").text
    assert "P-000" not in bruto and "pulseira" not in bruto and "matricula" not in bruto


# ------------------------------------------------------------------ nome_busca sempre atualizado
def test_renomear_participante_atualiza_a_busca(cliente, auth, cenario):
    with session_scope() as db:
        pedro = db.scalar(select(Participant).where(Participant.matricula == "10042"))
        pedro_id = pedro.id
    resposta = cliente.patch(
        f"/api/events/{cenario['a']}/participantes/{pedro_id}",
        json={"nome": "Ângela Ávila"},
        headers=auth,
    )
    assert resposta.status_code == 200
    assert _ids(cliente, auth, q="angela avila") == _esperado(cenario, 3)
    assert _ids(cliente, auth, q="pedro") == set()


def test_importacao_grava_a_forma_de_busca(cliente, auth):
    event_id, _, _ = montar_evento(participantes=0)
    cliente.post(
        f"/api/events/{event_id}/participantes/importar/confirmar",
        json={"linhas": [{"nome": "Inês  Brandão", "matricula": "00777", "setor": "TI"}]},
        headers=auth,
    )
    with session_scope() as db:
        assert db.scalar(select(Participant.nome_busca).where(Participant.matricula == "00777")) == (
            "ines brandao"
        )


# ------------------------------------------------------------------ detalhe e anulacoes
def test_detalhe_preserva_anulacao_e_resorteio(cliente, auth):
    """Fluxo real: sortear, anular por ausencia e sortear de novo a mesma unidade."""
    event_id, _, unidades = montar_evento(participantes=4)
    primeiro = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "detalhe-0001"},
        headers=auth,
    ).json()
    cliente.post(
        f"/api/events/{event_id}/sorteios/{primeiro['id']}/anular",
        json={"motivo": "Nao compareceu ao palco", "tipo": "ausencia"},
        headers=auth,
    )
    segundo = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "detalhe-0002"},
        headers=auth,
    ).json()

    # A busca encontra os dois: o anulado continua no historico.
    assert _ids(cliente, auth, event_id=event_id) == {primeiro["id"], segundo["id"]}
    assert _ids(cliente, auth, event_id=event_id, status="anulado") == {primeiro["id"]}

    detalhe = cliente.get(f"/api/sorteios/{segundo['id']}", headers=auth).json()
    assert detalhe["sorteio"]["draw_anterior_id"] == primeiro["id"]
    cadeia = [(s["id"], s["status"]) for s in detalhe["historico_da_unidade"]]
    assert cadeia == [(primeiro["id"], "anulado"), (segundo["id"], "valido")]
    assert detalhe["historico_da_unidade"][0]["motivo_anulacao"] == "Nao compareceu ao palco"

    acoes = [a["acao"] for a in cliente.get(f"/api/sorteios/{primeiro['id']}", headers=auth).json()["auditoria"]]
    assert acoes == ["sorteio_realizado", "sorteio_anulado"]


def test_detalhe_inexistente(cliente, auth):
    assert cliente.get("/api/sorteios/999999", headers=auth).status_code == 404


def test_operadores_que_ja_sortearam(cliente, auth, cenario):
    nomes = [o["nome"] for o in cliente.get("/api/sorteios/operadores", headers=auth).json()]
    assert nomes == ["Ana Operadora", "Organizador"]
    so_b = cliente.get("/api/sorteios/operadores", params={"event_id": cenario["b"]}, headers=auth)
    assert [o["nome"] for o in so_b.json()] == ["Organizador"]


# ------------------------------------------------------------------ exportacao
def test_exportacao_csv_respeita_os_filtros(cliente, auth, cenario):
    resposta = cliente.get(
        "/api/sorteios/export.csv", params={"event_id": cenario["a"], "q": "maria"}, headers=auth
    )
    assert resposta.status_code == 200
    assert "attachment" in resposta.headers["content-disposition"]
    linhas = resposta.content.decode("utf-8-sig").strip().splitlines()
    cabecalho = linhas[0].split(";")
    assert cabecalho[-3:] == ["pulseira", "bloco", "evento"]
    assert len(linhas) == 1 + 3  # rodadas 2, 4 e 5
    assert all(";00123;" in linha for linha in linhas[1:])  # zeros preservados


def test_exportacao_xlsx_preserva_zeros_e_pulseira(cliente, auth, cenario):
    resposta = cliente.get(
        "/api/sorteios/export.xlsx", params={"event_id": cenario["a"], "q": "00042"}, headers=auth
    )
    planilha = load_workbook(io.BytesIO(resposta.content))["resultados"]
    cabecalho = [c.value for c in planilha[1]]
    linha = dict(zip(cabecalho, [c.value for c in planilha[2]]))
    assert planilha.max_row == 2
    assert linha["matricula"] == "00042"
    assert linha["pulseira"] == "A-0042"
    assert linha["bloco"] == "01 - Bloco 01"
    assert linha["evento"] == "Festa 2026"


def test_exportacao_de_varios_eventos_usa_o_fuso_de_cada_um(cliente, auth, cenario):
    texto = cliente.get("/api/sorteios/export.csv", params={"q": "jose"}, headers=auth).content.decode(
        "utf-8-sig"
    )
    linha_b = next(l for l in texto.splitlines() if "José Antônio" in l)
    linha_a = next(l for l in texto.splitlines() if "José da Conceição" in l)
    assert "10/12/2025 20:00:00" in linha_b  # Manaus
    assert "12/12/2026 22:30:00" in linha_a  # Sao Paulo


def test_exportacao_fica_na_auditoria_com_os_filtros(cliente, auth, cenario):
    cliente.get(
        "/api/sorteios/export.csv",
        params={"event_id": cenario["a"], "status": "anulado", "q": "maria"},
        headers=auth,
    )
    registros = [
        r for r in cliente.get(f"/api/events/{cenario['a']}/relatorio/auditoria", headers=auth).json()
        if r["acao"] == "historico_exportado"
    ]
    assert len(registros) == 1
    assert registros[0]["detalhes"]["linhas"] == 2
    assert registros[0]["detalhes"]["filtros"]["q"] == "maria"
    assert registros[0]["detalhes"]["filtros"]["status"] == "anulado"


def test_exportacoes_antigas_continuam_funcionando(cliente, auth, cenario):
    csv = cliente.get(f"/api/events/{cenario['a']}/relatorio/export.csv", headers=auth)
    assert csv.status_code == 200
    assert len(csv.content.decode("utf-8-sig").strip().splitlines()) == 1 + 5
