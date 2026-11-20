"""Utilitarios compartilhados pelos testes das Fases 5 a 8."""

from __future__ import annotations

import io
from datetime import date

from PIL import Image

from app.database import session_scope
from app.models import Event, User
from app.security import criar_token, hash_senha

SENHA_COLABORADOR = "festa2026ok"


def imagem(formato: str = "JPEG", tamanho: tuple[int, int] = (64, 48)) -> bytes:
    """Imagem real (o backend reabre e regrava toda foto recebida)."""
    buffer = io.BytesIO()
    modo = "RGBA" if formato == "PNG" else "RGB"
    Image.new(modo, tamanho, (200, 30, 60, 255) if modo == "RGBA" else (200, 30, 60)).save(
        buffer, format=formato
    )
    return buffer.getvalue()


def configurar_evento(event_id: int, **campos) -> None:
    padrao = {"autocadastro_ativo": True}
    padrao.update(campos)
    with session_scope() as db:
        evento = db.get(Event, event_id)
        for campo, valor in padrao.items():
            setattr(evento, campo, valor)


def conta(papel: str, login: str | None = None, senha: str = "senha-forte1", **extra) -> int:
    with session_scope() as db:
        user = User(
            usuario=login or f"conta_{papel.lower()}",
            nome=extra.pop("nome", f"Conta {papel.title()}"),
            senha_hash=hash_senha(senha),
            papel=papel,
            **extra,
        )
        db.add(user)
        db.flush()
        return user.id


def cabecalho(user_id: int) -> dict:
    with session_scope() as db:
        versao = db.get(User, user_id).sessao_versao
    return {"Authorization": f"Bearer {criar_token(user_id, versao)}"}


def nome_do(participant_id: int) -> str:
    from app.models import Participant

    with session_scope() as db:
        return db.get(Participant, participant_id).nome


NASCIMENTO = date(1990, 3, 15)


def cpf_valido(base: int) -> str:
    """CPF ficticio com digitos verificadores validos a partir de 9 digitos."""
    numeros = [int(c) for c in f"{base % 10**9:09d}"]
    if len(set(numeros)) == 1:
        numeros[-1] = (numeros[-1] + 1) % 10
    for tamanho in (9, 10):
        soma = sum(numeros[i] * (tamanho + 1 - i) for i in range(tamanho))
        numeros.append((soma * 10) % 11 % 10)
    return "".join(map(str, numeros))


def cpf_do(participant_id: int) -> str:
    return cpf_valido(123_450_000 + participant_id)


def dar_identificacao(participant_id: int, nascimento: date = NASCIMENTO, cpf: str | None = None) -> str:
    """Simula a importacao com CPF e nascimento (grava so os codigos). Devolve o CPF."""
    from app.models import Participant
    from app.services import identificacao

    cpf = cpf or cpf_do(participant_id)
    with session_scope() as db:
        p = db.get(Participant, participant_id)
        p.identificacao_hash = identificacao.codigo_identificacao(nascimento, cpf[:5])
        p.cpf_hash = identificacao.codigo_cpf(cpf)
    return cpf


def _participante_por_matricula(event_id: int, matricula: str):
    from sqlalchemy import select

    from app.models import Participant
    from app.texto import normalizar_matricula

    with session_scope() as db:
        return db.scalar(
            select(Participant.id).where(
                Participant.event_id == event_id,
                Participant.matricula_normalizada == normalizar_matricula(matricula),
            )
        )


def identificar(cliente, event_id: int, matricula: str, *, nascimento: str | None = None, cpf5: str | None = None):
    """Passo 1 do cadastro. Sem cpf5, usa os dados de dar_identificacao (criados se faltarem)."""
    if cpf5 is None:
        pid = _participante_por_matricula(event_id, matricula)
        if pid is not None:
            from app.models import Participant

            with session_scope() as db:
                tem = db.get(Participant, pid).identificacao_hash is not None
            cpf = cpf_do(pid)
            if not tem:
                dar_identificacao(pid, cpf=cpf)
            cpf5 = cpf[:5]
        else:
            cpf5 = "00000"
    return cliente.post(
        f"/api/autocadastro/{event_id}/identificar",
        json={
            "matricula": matricula,
            "nascimento": nascimento or NASCIMENTO.isoformat(),
            "cpf5": cpf5,
        },
    )


def concluir(
    cliente,
    event_id: int,
    matricula: str,
    nome: str | None = None,
    *,
    pulseira: str | None = None,  # ignorado: o portal nao registra pulseira
    nascimento: str | None = None,
    cpf5: str | None = None,
    foto: bytes | None = None,
    nome_foto: str = "foto.jpg",
    enviar_foto: bool = True,
    remover_foto: bool = False,
    passe: str | None = None,
):
    """Identifica (se nao houver passe) e conclui. Devolve a resposta HTTP da etapa que parou.

    Sem nascimento/cpf5, usa os dados de dar_identificacao do participante
    (a senha da conta fica sendo esses 5 digitos: ver senha_de()).
    """
    if passe is None:
        resposta = identificar(cliente, event_id, matricula)
        if resposta.status_code != 200:
            return resposta
        passe = resposta.json()["passe"]
    if cpf5 is None:
        pid = _participante_por_matricula(event_id, matricula)
        cpf5 = cpf_do(pid)[:5] if pid is not None else "00000"
    arquivos = None
    if enviar_foto:
        arquivos = {"foto": (nome_foto, foto if foto is not None else imagem(), "image/jpeg")}
    return cliente.post(
        f"/api/autocadastro/{event_id}/concluir",
        data={
            "passe": passe,
            "nascimento": nascimento or NASCIMENTO.isoformat(),
            "cpf5": cpf5,
            "remover_foto": "true" if remover_foto else "false",
        },
        files=arquivos,
    )


def senha_de(participant_id: int) -> str:
    """Senha do colaborador depois do cadastro: 5 primeiros digitos do CPF."""
    return cpf_do(participant_id)[:5]


def autocadastrar(cliente, auth: dict, event_id: int, participant_id: int, matricula: str, **kw) -> dict:
    """Autocadastro completo pelo colaborador; devolve o JSON da conclusao (com token).

    `auth` fica na assinatura por compatibilidade: o autocadastro nao usa sessao.
    """
    resposta = concluir(cliente, event_id, matricula, nome_do(participant_id), **kw)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()
