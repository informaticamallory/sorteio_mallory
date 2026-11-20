"""Restricoes e relacionamentos criados na Fase 1, verificados no banco migrado."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal, engine, session_scope
from app.models import (
    BlocoSorteio,
    Draw,
    Event,
    Notificacao,
    Papel,
    Participant,
    PrizeUnit,
    StatusSorteio,
    TipoNotificacao,
    User,
)
from app.security import hash_senha, novo_token_telao
from app.services.sorteio import anular_sorteio, realizar_sorteio
from conftest import montar_evento


def _novo_evento(db, nome: str = "Outro evento") -> Event:
    evento = Event(nome=nome, telao_token=novo_token_telao())
    db.add(evento)
    db.flush()
    return evento


def _novo_usuario(db, login: str, papel: Papel = Papel.COLABORADOR) -> User:
    user = User(usuario=login, nome=login, senha_hash=hash_senha("x"), papel=papel.value)
    db.add(user)
    db.flush()
    return user


def _commit_falha(db) -> None:
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------- pulseira
def test_pulseira_e_unica_dentro_do_evento():
    event_id, ids, _ = montar_evento(participantes=2)
    db = SessionLocal()
    try:
        db.get(Participant, ids[0]).pulseira = "00042"
        db.commit()
        db.get(Participant, ids[1]).pulseira = "00042"
        _commit_falha(db)
    finally:
        db.close()


def test_mesma_pulseira_em_eventos_diferentes_e_permitida():
    event_id, ids, _ = montar_evento(participantes=1)
    with session_scope() as db:
        db.get(Participant, ids[0]).pulseira = "777"
        outro = _novo_evento(db)
        db.add(Participant(event_id=outro.id, nome="X", matricula="1", pulseira="777"))


def test_varios_participantes_sem_pulseira_sao_permitidos():
    event_id, ids, _ = montar_evento(participantes=5)
    with session_scope() as db:
        sem = db.scalars(select(Participant).where(Participant.pulseira.is_(None))).all()
        assert len(sem) == 5


def test_matricula_continua_unica_dentro_do_evento():
    event_id, _, _ = montar_evento(participantes=1)
    db = SessionLocal()
    try:
        db.add(Participant(event_id=event_id, nome="Duplicado", matricula="00001"))
        _commit_falha(db)
    finally:
        db.close()


# ---------------------------------------------------------------- conta x participante
def test_conta_vincula_a_um_unico_participante_por_evento():
    event_id, ids, _ = montar_evento(participantes=2)
    db = SessionLocal()
    try:
        user = _novo_usuario(db, "colab1")
        db.get(Participant, ids[0]).usuario_id = user.id
        db.commit()
        db.get(Participant, ids[1]).usuario_id = user.id
        _commit_falha(db)
    finally:
        db.close()


def test_mesma_conta_pode_participar_de_eventos_diferentes():
    """Ex.: o colaborador participa da festa de 2026 e da de 2027."""
    event_id, ids, _ = montar_evento(participantes=1)
    with session_scope() as db:
        user = _novo_usuario(db, "colab2")
        db.get(Participant, ids[0]).usuario_id = user.id
        outro = _novo_evento(db)
        db.add(Participant(event_id=outro.id, nome="X", matricula="00001", usuario_id=user.id))


def test_apagar_conta_nao_apaga_o_participante():
    event_id, ids, _ = montar_evento(participantes=1)
    with session_scope() as db:
        user = _novo_usuario(db, "colab3")
        db.get(Participant, ids[0]).usuario_id = user.id
    with engine.begin() as conexao:
        conexao.execute(text("DELETE FROM users WHERE usuario = 'colab3'"))
    with session_scope() as db:
        participante = db.get(Participant, ids[0])
        assert participante is not None
        assert participante.usuario_id is None


# ---------------------------------------------------------------- papeis
def test_conta_nova_nasce_colaborador():
    with session_scope() as db:
        user = User(usuario="semPapel", nome="X", senha_hash="h")
        db.add(user)
        db.flush()
        assert user.papel == Papel.COLABORADOR.value
    # Tambem pelo valor padrao do banco (insercao fora do ORM).
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO users (usuario, nome, senha_hash, ativo, criado_em) "
                "VALUES ('cru', 'Cru', 'h', 1, '2026-11-13')"
            )
        )
        papel = conexao.execute(text("SELECT papel FROM users WHERE usuario = 'cru'")).scalar()
    assert papel == "COLABORADOR"


def test_banco_rejeita_papel_invalido():
    with pytest.raises(IntegrityError):
        with engine.begin() as conexao:
            conexao.execute(text("UPDATE users SET papel = 'SUPERUSUARIO'"))


def test_organizador_padrao_e_admin():
    with session_scope() as db:
        assert db.scalar(select(User.papel).where(User.usuario == "organizador")) == "ADMIN"


# ---------------------------------------------------------------- blocos
def test_numero_do_bloco_e_unico_no_evento():
    event_id, _, _ = montar_evento()
    db = SessionLocal()
    try:
        db.add(BlocoSorteio(event_id=event_id, numero=1, nome="Bloco 01"))
        db.commit()
        db.add(BlocoSorteio(event_id=event_id, numero=1, nome="Repetido"))
        _commit_falha(db)
    finally:
        db.close()


@pytest.mark.parametrize("campo,valor", [("capacidade", 0), ("status", "CANCELADO")])
def test_bloco_rejeita_valores_invalidos(campo, valor):
    event_id, _, _ = montar_evento()
    db = SessionLocal()
    try:
        db.add(BlocoSorteio(event_id=event_id, numero=1, nome="B", **{campo: valor}))
        _commit_falha(db)
    finally:
        db.close()


def test_bloco_novo_tem_valores_padrao():
    event_id, _, _ = montar_evento()
    with session_scope() as db:
        bloco = BlocoSorteio(event_id=event_id, numero=1, nome="Bloco 01")
        db.add(bloco)
        db.flush()
        assert bloco.capacidade == 25
        assert bloco.status == "PLANEJADO"


def test_cada_unidade_do_premio_se_vincula_a_um_bloco():
    """Premio com 3 unidades = 3 vinculos independentes."""
    event_id, _, unidades = montar_evento(quantidade_premio=3)
    with session_scope() as db:
        b1 = BlocoSorteio(event_id=event_id, numero=1, nome="Bloco 01")
        b2 = BlocoSorteio(event_id=event_id, numero=2, nome="Bloco 02")
        db.add_all([b1, b2])
        db.flush()
        db.get(PrizeUnit, unidades[0]).bloco_id = b1.id
        db.get(PrizeUnit, unidades[1]).bloco_id = b1.id
        db.get(PrizeUnit, unidades[2]).bloco_id = b2.id
    with session_scope() as db:
        b1 = db.scalar(select(BlocoSorteio).where(BlocoSorteio.numero == 1))
        assert sorted(u.id for u in b1.unidades) == unidades[:2]


def test_apagar_bloco_sem_resultados_libera_as_unidades():
    event_id, _, unidades = montar_evento()
    with session_scope() as db:
        bloco = BlocoSorteio(event_id=event_id, numero=1, nome="B")
        db.add(bloco)
        db.flush()
        db.get(PrizeUnit, unidades[0]).bloco_id = bloco.id
    with engine.begin() as conexao:
        conexao.execute(text("DELETE FROM blocos_sorteio"))
    with session_scope() as db:
        assert db.get(PrizeUnit, unidades[0]).bloco_id is None


# ---------------------------------------------------------------- sorteio x bloco
def _sortear(event_id: int, unidade_id: int, chave: str) -> int:
    with session_scope() as db:
        evento = db.get(Event, event_id)
        usuario = db.scalar(select(User))
        sorteio, _ = realizar_sorteio(db, evento, unidade_id, chave, usuario)
        db.flush()
        return sorteio.id


def test_sorteio_grava_o_bloco_da_unidade():
    event_id, _, unidades = montar_evento(participantes=3)
    with session_scope() as db:
        bloco = BlocoSorteio(event_id=event_id, numero=1, nome="Bloco 01", status="EM_ANDAMENTO")
        db.add(bloco)
        db.flush()
        bloco_id = bloco.id
        db.get(PrizeUnit, unidades[0]).bloco_id = bloco_id
    draw_id = _sortear(event_id, unidades[0], "bloco-snapshot-1")
    with session_scope() as db:
        assert db.get(Draw, draw_id).bloco_id == bloco_id


def test_historico_nao_muda_de_bloco_quando_a_unidade_e_redistribuida():
    event_id, _, unidades = montar_evento(participantes=3)
    with session_scope() as db:
        b1 = BlocoSorteio(event_id=event_id, numero=1, nome="Bloco 01", status="EM_ANDAMENTO")
        b5 = BlocoSorteio(event_id=event_id, numero=5, nome="Remanescentes")
        db.add_all([b1, b5])
        db.flush()
        b1_id, b5_id = b1.id, b5.id
        db.get(PrizeUnit, unidades[0]).bloco_id = b1_id
    draw_id = _sortear(event_id, unidades[0], "redistribui-1")
    with session_scope() as db:
        sorteio = db.get(Draw, draw_id)
        anular_sorteio(
            db, sorteio, "Ganhador ausente", "ausencia", False, db.scalar(select(User))
        )
        db.get(PrizeUnit, unidades[0]).bloco_id = b5_id  # vai para remanescentes
    with session_scope() as db:
        anulado = db.get(Draw, draw_id)
        assert anulado.status == StatusSorteio.ANULADO.value
        assert anulado.bloco_id == b1_id


def test_bloco_com_resultado_registrado_nao_pode_ser_apagado():
    event_id, _, unidades = montar_evento(participantes=2)
    with session_scope() as db:
        bloco = BlocoSorteio(event_id=event_id, numero=1, nome="B", status="EM_ANDAMENTO")
        db.add(bloco)
        db.flush()
        db.get(PrizeUnit, unidades[0]).bloco_id = bloco.id
    _sortear(event_id, unidades[0], "protege-bloco-1")
    with pytest.raises(IntegrityError):
        with engine.begin() as conexao:
            conexao.execute(text("DELETE FROM blocos_sorteio"))


# ---------------------------------------------------------------- notificacoes
def _notificacao(event_id, participant_id, draw_id, tipo=TipoNotificacao.PREMIO_GANHO):
    return Notificacao(
        event_id=event_id,
        participant_id=participant_id,
        draw_id=draw_id,
        tipo=tipo.value,
        titulo="Parabens!",
        mensagem="Voce ganhou.",
    )


def test_notificacao_nao_duplica_para_o_mesmo_sorteio_e_tipo():
    event_id, ids, unidades = montar_evento(participantes=2)
    draw_id = _sortear(event_id, unidades[0], "notif-dup-1")
    db = SessionLocal()
    try:
        ganhador = db.get(Draw, draw_id).participant_id
        # Desde a Fase 6 o proprio sorteio cria o aviso PREMIO_GANHO; uma
        # segunda insercao do mesmo tipo e barrada pelo banco.
        assert len(db.scalars(select(Notificacao).where(Notificacao.draw_id == draw_id)).all()) == 1
        db.add(_notificacao(event_id, ganhador, draw_id))
        _commit_falha(db)
        # Um tipo diferente (ex.: aviso de anulacao) para o mesmo sorteio e valido.
        db.add(_notificacao(event_id, ganhador, draw_id, TipoNotificacao.SORTEIO_ANULADO))
        db.commit()
    finally:
        db.close()


def test_notificacao_persiste_sem_conta_vinculada():
    event_id, ids, unidades = montar_evento(participantes=1)
    # O aviso e criado pelo proprio sorteio (Fase 6), mesmo sem conta vinculada.
    _sortear(event_id, unidades[0], "notif-sem-conta")
    with session_scope() as db:
        notificacao = db.scalar(select(Notificacao))
        assert notificacao.usuario_id is None
        assert notificacao.lida is False
        assert notificacao.lida_em is None


def test_indices_de_consulta_existem():
    inspetor = inspect(engine)
    nomes = {indice["name"] for indice in inspetor.get_indexes("notificacoes")}
    assert {
        "ix_notificacoes_usuario_lida_criada",
        "ix_notificacoes_participante_criada",
        "ix_notificacoes_evento_criada",
    } <= nomes
    participantes = {i["name"]: i for i in inspetor.get_indexes("participants")}
    assert participantes["uq_participante_pulseira_evento"]["unique"]
    assert participantes["uq_participante_usuario_evento"]["unique"]
    assert "ix_draws_bloco_id" in {i["name"] for i in inspetor.get_indexes("draws")}
    assert "ix_prize_units_bloco_id" in {i["name"] for i in inspetor.get_indexes("prize_units")}


# ---------------------------------------------------------------- demo
def test_limpar_demo_funciona_com_sorteios_e_preserva_eventos_reais():
    """Regressao: carregar-demo.ps1 quebrava apos o primeiro sorteio."""
    from app.seed import criar_demo, limpar_demo

    real_id, _, unidades_reais = montar_evento(participantes=3)
    _sortear(real_id, unidades_reais[0], "evento-real-1")

    demo_id = criar_demo()
    with session_scope() as db:
        unidade_demo = db.scalar(
            select(PrizeUnit.id)
            .join(PrizeUnit.premio)
            .where(PrizeUnit.premio.has(event_id=demo_id))
            .limit(1)
        )
        db.execute(text("UPDATE participants SET presente = 1 WHERE event_id = :e"), {"e": demo_id})
    _sortear(demo_id, unidade_demo, "evento-demo-1")

    assert limpar_demo() == 1
    with session_scope() as db:
        assert db.get(Event, demo_id) is None
        assert db.get(Event, real_id) is not None
        assert db.scalar(select(Draw).where(Draw.event_id == real_id)) is not None
