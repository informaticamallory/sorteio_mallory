"""Notificacao push no celular (Web Push com VAPID) para o Portal do Colaborador.

Regras:
  * so o aviso de PREMIO_GANHO vira push, e so depois que o telao revelou o
    ganhador (Notificacao.disponivel_em) e enquanto o resultado continua valido;
  * cada notificacao gera no maximo um push: a marca push_enviado_em e gravada
    com UPDATE condicional ANTES do envio. Reapresentar o resultado no telao,
    reconectar ou reiniciar o servidor nao reenvia;
  * o conteudo do push nao traz nome de premio nem dado pessoal (aparece na
    tela bloqueada): so convida a abrir o cartao;
  * entrega nao e garantida (depende do navegador, do sistema e da internet).
    O aviso sempre fica no portal, que e a fonte oficial.

Requisitos: endereco HTTPS (sem ele o navegador nem cria a inscricao) e um
contato VAPID (VAPID_SUBJECT, ou URL_PUBLICA https). As chaves VAPID sao
criadas uma vez em DATA_DIR/vapid.json.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import delete, or_, select, update  # noqa: F401

from ..config import DATA_DIR, settings
from ..database import session_scope
from ..models import Draw, Event, InscricaoPush, Notificacao, StatusSorteio, TipoNotificacao, utcnow

log = logging.getLogger("sorteio.push")

ARQUIVO_CHAVES = DATA_DIR / "vapid.json"
TITULO = "🎉 Parabéns! Você foi sorteado!"
# Push mais antigo que isso nao e mais enviado (ex.: servidor ficou desligado).
JANELA_HORAS = 12
TTL_SEGUNDOS = 12 * 3600
MAX_FALHAS = 5


def mensagem(empresa: str) -> str:
    return (
        f"Seu número da sorte foi contemplado no Sorteio {empresa or 'Mallory'}. "
        "Acesse seu cartão para conferir o prêmio."
    )


# ------------------------------------------------------------------ configuracao
@lru_cache(maxsize=1)
def _chaves() -> tuple[str, str]:
    """(PEM da chave privada, chave publica base64url) - criadas uma unica vez."""
    if ARQUIVO_CHAVES.exists():
        dados = json.loads(ARQUIVO_CHAVES.read_text(encoding="utf-8"))
        return dados["privada_pem"], dados["publica"]
    privada = ec.generate_private_key(ec.SECP256R1())
    pem = privada.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")
    ponto = privada.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    publica = base64.urlsafe_b64encode(ponto).rstrip(b"=").decode("ascii")
    ARQUIVO_CHAVES.write_text(json.dumps({"privada_pem": pem, "publica": publica}), encoding="utf-8")
    return pem, publica


def contato_vapid() -> str | None:
    if settings.vapid_subject.strip():
        return settings.vapid_subject.strip()
    if settings.url_publica.strip().lower().startswith("https://"):
        return settings.url_publica.strip().rstrip("/")
    return None


@dataclass
class Configuracao:
    disponivel: bool
    chave_publica: str | None
    motivo: str | None


def configuracao() -> Configuracao:
    contato = contato_vapid()
    if contato is None:
        return Configuracao(
            False,
            None,
            "Notificações no celular exigem endereço HTTPS. Defina URL_PUBLICA (https) "
            "ou VAPID_SUBJECT no servidor.",
        )
    _pem, publica = _chaves()
    return Configuracao(True, publica, None)


# ------------------------------------------------------------------ envio
Enviador = Callable[[InscricaoPush, dict], int]
"""Envia um push e devolve o status HTTP do servico de push (201 = aceito)."""


def _enviador_webpush() -> Enviador:
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush

    pem, _publica = _chaves()
    vapid = Vapid.from_pem(pem.encode("ascii"))
    contato = contato_vapid()

    def enviar(inscricao: InscricaoPush, carga: dict) -> int:
        try:
            resposta = webpush(
                subscription_info={
                    "endpoint": inscricao.endpoint,
                    "keys": {"p256dh": inscricao.p256dh, "auth": inscricao.auth},
                },
                data=json.dumps(carga, ensure_ascii=False),
                vapid_private_key=vapid,
                vapid_claims={"sub": contato},
                ttl=TTL_SEGUNDOS,
                headers={"Urgency": "high"},
                timeout=10,
            )
            return getattr(resposta, "status_code", 201)
        except WebPushException as exc:
            return exc.response.status_code if exc.response is not None else 0

    return enviar


def _candidatas() -> list[tuple[int, int, int | None, int]]:
    agora = utcnow()
    with session_scope() as db:
        return [
            tuple(linha)
            for linha in db.execute(
                select(Notificacao.id, Notificacao.usuario_id, Notificacao.draw_id, Notificacao.event_id).where(
                    Notificacao.tipo == TipoNotificacao.PREMIO_GANHO.value,
                    Notificacao.push_enviado_em.is_(None),
                    Notificacao.usuario_id.is_not(None),
                    or_(Notificacao.disponivel_em.is_(None), Notificacao.disponivel_em <= agora),
                    Notificacao.criada_em >= agora - timedelta(hours=JANELA_HORAS),
                    # Evento de teste nao manda push ao celular.
                    Notificacao.event_id.in_(select(Event.id).where(Event.evento_teste.is_(False))),
                )
            ).all()
        ]


def enviar_pendentes(enviar: Enviador | None = None) -> int:
    """Envia os pushes liberados e ainda nao enviados. Devolve quantos foram aceitos."""
    if not configuracao().disponivel:
        return 0
    aceitos = 0
    envio: Enviador | None = enviar
    for notificacao_id, usuario_id, draw_id, event_id in _candidatas():
        # 1) Reserva (transacao curta): so uma rodada envia esta notificacao.
        with session_scope() as db:
            reservada = db.execute(
                update(Notificacao)
                .where(Notificacao.id == notificacao_id, Notificacao.push_enviado_em.is_(None))
                .values(push_enviado_em=utcnow())
            ).rowcount
            if reservada != 1:
                continue
            sorteio = db.get(Draw, draw_id) if draw_id else None
            if sorteio is None or sorteio.status != StatusSorteio.VALIDO.value:
                continue  # resultado anulado antes da revelacao: nada a anunciar
            evento = db.get(Event, event_id)
            inscricoes = [
                InscricaoPush(id=i.id, endpoint=i.endpoint, p256dh=i.p256dh, auth=i.auth)
                for i in db.scalars(select(InscricaoPush).where(InscricaoPush.usuario_id == usuario_id))
            ]
            empresa = evento.empresa_nome if evento else ""
        if not inscricoes:
            continue

        # 2) Envio FORA da transacao: a rede nao segura o banco (sorteios continuam).
        carga = {
            "titulo": TITULO,
            "mensagem": mensagem(empresa),
            "url": "/minha-area?aba=premios",
            "tag": f"premio-{draw_id}",
        }
        envio = envio or _enviador_webpush()
        resultados = [(inscricao.id, envio(inscricao, carga)) for inscricao in inscricoes]

        # 3) Resultado de cada aparelho.
        with session_scope() as db:
            for inscricao_id, status in resultados:
                inscricao = db.get(InscricaoPush, inscricao_id)
                if inscricao is None:
                    continue
                if 200 <= status < 300:
                    inscricao.ultimo_envio_em = utcnow()
                    inscricao.falhas = 0
                    aceitos += 1
                elif status in (404, 410):
                    db.delete(inscricao)  # inscricao expirada ou cancelada no aparelho
                else:
                    inscricao.falhas += 1
                    if inscricao.falhas >= MAX_FALHAS:
                        db.delete(inscricao)
                    log.warning("push nao aceito (status %s) para a inscricao %s", status, inscricao_id)
    return aceitos


# ------------------------------------------------------------------ inscricoes
def inscrever(db, usuario_id: int, endpoint: str, p256dh: str, auth: str) -> InscricaoPush:  # noqa: ANN001
    existente = db.scalar(select(InscricaoPush).where(InscricaoPush.endpoint == endpoint))
    if existente is None:
        existente = InscricaoPush(usuario_id=usuario_id, endpoint=endpoint, p256dh=p256dh, auth=auth)
        db.add(existente)
    else:
        # Mesmo aparelho: chaves renovadas ou outra conta usando o aparelho.
        existente.usuario_id = usuario_id
        existente.p256dh = p256dh
        existente.auth = auth
        existente.falhas = 0
    return existente


def cancelar(db, usuario_id: int, endpoint: str) -> int:  # noqa: ANN001
    return db.execute(
        delete(InscricaoPush).where(
            InscricaoPush.endpoint == endpoint, InscricaoPush.usuario_id == usuario_id
        )
    ).rowcount
