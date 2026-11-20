"""Zerar a lista de participantes para reimportar a planilha."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from app.config import arquivo_sqlite, settings
from app.database import session_scope
from app.models import AuditLog, Draw, Notificacao, Participant, User
from conftest import montar_evento


def _zerar(cliente, auth, event_id, confirmacao="ZERAR"):
    return cliente.post(
        f"/api/events/{event_id}/participantes/zerar", json={"confirmacao": confirmacao}, headers=auth
    )


def _montar_com_sorteio_e_conta(cliente, auth):
    event_id, ids, unidades = montar_evento(participantes=6)
    # Participante 1 so concorre sozinho: vira o ganhador.
    with session_scope() as db:
        for pid in ids[1:]:
            db.get(Participant, pid).presente = False
    r = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "zerar-0001"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    with session_scope() as db:
        conta = db.scalars(select(User)).first()
        db.get(Participant, ids[1]).usuario_id = conta.id  # fez autocadastro
        db.add(Notificacao(event_id=event_id, participant_id=ids[2], tipo="aviso", titulo="t", mensagem="m"))
    return event_id, ids


def test_confirmacao_errada_nao_apaga_nada(cliente, auth):
    event_id, _, _ = montar_evento(participantes=3)
    for frase in ("", "zera", "apagar"):
        r = _zerar(cliente, auth, event_id, frase)
        assert r.status_code == 422
    with session_scope() as db:
        assert db.scalar(select(func.count(Participant.id))) == 3


def test_zera_e_mantem_quem_tem_sorteio_ou_autocadastro(cliente, auth):
    event_id, ids = _montar_com_sorteio_e_conta(cliente, auth)

    r = _zerar(cliente, auth, event_id, " zerar ")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["removidos"] == 4
    motivos = {m["matricula"]: m["motivo"] for m in corpo["mantidos"]}
    assert motivos == {"00001": "tem resultado no histórico", "00002": "já fez o autocadastro"}

    with session_scope() as db:
        restantes = set(db.scalars(select(Participant.id)).all())
        assert restantes == {ids[0], ids[1]}
        assert db.scalar(select(func.count(Draw.id))) == 1  # historico intacto
        assert db.scalar(select(func.count(Notificacao.id)).where(Notificacao.participant_id == ids[2])) == 0
        log = db.scalars(select(AuditLog).where(AuditLog.acao == "participantes_zerados")).one()
        assert log.detalhes["removidos"] == 4
        assert log.detalhes["mantidos"] == ["00001", "00002"]

    # Backup feito antes de apagar, com os 6 participantes.
    assert corpo["backup"]
    copia = arquivo_sqlite(settings.database_url).parent / "backups" / corpo["backup"]
    assert copia.exists()
    import sqlite3

    con = sqlite3.connect(copia)
    try:
        assert con.execute("select count(*) from participants").fetchone()[0] == 6
    finally:
        con.close()
    copia.unlink()


def test_reimportar_depois_de_zerar(cliente, auth):
    event_id, ids = _montar_com_sorteio_e_conta(cliente, auth)
    assert _zerar(cliente, auth, event_id).status_code == 200

    linhas = [
        {"nome": "Nome Corrigido", "matricula": "00002", "setor": "RH"},  # ja existe (autocadastro)
        {"nome": "Pessoa Nova", "matricula": "00007", "setor": "TI"},
        {"nome": "Participante 3", "matricula": "00003", "setor": "Geral"},  # tinha sido apagada
    ]
    r = cliente.post(
        f"/api/events/{event_id}/participantes/importar/confirmar",
        json={"linhas": linhas, "atualizar_existentes": True},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    assert (r.json()["criados"], r.json()["atualizados"]) == (2, 1)
    with session_scope() as db:
        mantido = db.get(Participant, ids[1])
        assert (mantido.nome, mantido.usuario_id is not None) == ("Nome Corrigido", True)
        assert db.scalar(select(func.count(Participant.id))) == 4


def test_lista_vazia_nao_faz_backup(cliente, auth):
    pasta = Path(arquivo_sqlite(settings.database_url)).parent / "backups"
    antes = set(pasta.glob("*zerar*"))
    event_id, _, _ = montar_evento(participantes=0)
    r = _zerar(cliente, auth, event_id)
    assert r.status_code == 200
    assert r.json() == {"removidos": 0, "mantidos": [], "backup": None}
    assert set(pasta.glob("*zerar*")) == antes
