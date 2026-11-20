"""Exclusao de usuario: so contas sem historico operacional."""
from __future__ import annotations

from sqlalchemy import select

from app.database import session_scope
from app.models import AuditLog, Notificacao, Participant, User
from conftest import montar_evento


def _criar(cliente, auth, usuario: str, papel: str = "RECEPCAO") -> tuple[int, str]:
    r = cliente.post("/api/usuarios", json={"usuario": usuario, "nome": "Pessoa Teste", "papel": papel}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()["usuario"]["id"], r.json()["senha_temporaria"]


def _excluir(cliente, auth, user_id):
    return cliente.delete(f"/api/usuarios/{user_id}", headers=auth)


def _meu_id() -> int:
    with session_scope() as db:
        return db.scalar(select(User.id).where(User.usuario == "organizador"))


def test_exclui_conta_sem_historico_e_preserva_registros_pessoais(cliente, auth):
    event_id, ids, _ = montar_evento(participantes=2)
    user_id, senha = _criar(cliente, auth, "conta.errada")
    assert cliente.post("/api/auth/login", json={"usuario": "conta.errada", "senha": senha}).status_code == 200
    with session_scope() as db:
        db.get(Participant, ids[0]).usuario_id = user_id  # como se tivesse feito o autocadastro
        db.add(Notificacao(event_id=event_id, participant_id=ids[0], usuario_id=user_id, tipo="aviso", titulo="t", mensagem="m"))

    r = _excluir(cliente, auth, user_id)
    assert r.status_code == 204, r.text

    meu_id = _meu_id()
    with session_scope() as db:
        assert db.get(User, user_id) is None
        participante = db.get(Participant, ids[0])
        assert participante is not None and participante.usuario_id is None  # continua na lista, sem conta
        assert db.scalars(select(Notificacao)).one().usuario_id is None
        login = db.scalars(select(AuditLog).where(AuditLog.acao == "login")).all()
        assert any(l.usuario_id is None and l.detalhes.get("usuario_excluido") == "conta.errada" for l in login)
        registro = db.scalars(select(AuditLog).where(AuditLog.acao == "usuario_excluido")).one()
        assert registro.usuario_id == meu_id
        assert registro.detalhes["usuario_alvo"] == "conta.errada"
        assert registro.detalhes["participantes_desvinculados"] == ["00001"]

    assert cliente.post("/api/auth/login", json={"usuario": "conta.errada", "senha": senha}).status_code == 401
    # O mesmo usuario pode ser criado de novo.
    _criar(cliente, auth, "conta.errada")


def test_conta_com_sorteio_nao_pode_ser_excluida(cliente, auth):
    # O admin logado realizou o sorteio: um segundo admin tenta excluir.
    event_id, _, unidades = montar_evento(participantes=1)
    r = cliente.post(
        f"/api/events/{event_id}/sorteio",
        json={"prize_unit_id": unidades[0], "idempotency_key": "excluir-usuario-1"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    outro_id, senha = _criar(cliente, auth, "admin.dois", "ADMIN")
    token = cliente.post("/api/auth/login", json={"usuario": "admin.dois", "senha": senha}).json()["access_token"]
    novo = cliente.post(
        "/api/auth/trocar-senha",
        json={"senha_atual": senha, "senha_nova": "Segunda2026x"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["access_token"]

    r = _excluir(cliente, {"Authorization": f"Bearer {novo}"}, _meu_id())
    assert r.status_code == 409
    assert "sorteios" in r.json()["detail"] and "Desative" in r.json()["detail"]
    meu_id = _meu_id()
    with session_scope() as db:
        assert db.get(User, meu_id) is not None


def test_conta_com_acao_de_gestao_nao_pode_ser_excluida(cliente, auth):
    user_id, _ = _criar(cliente, auth, "gestor.rh", "ORGANIZADOR")
    with session_scope() as db:
        db.add(AuditLog(usuario_id=user_id, acao="premio_criado", detalhes={}))
    r = _excluir(cliente, auth, user_id)
    assert r.status_code == 409
    assert "auditoria" in r.json()["detail"]


def test_nao_exclui_a_propria_conta_nem_inexistente(cliente, auth):
    assert _excluir(cliente, auth, _meu_id()).status_code == 409
    assert _excluir(cliente, auth, 999_999).status_code == 404
