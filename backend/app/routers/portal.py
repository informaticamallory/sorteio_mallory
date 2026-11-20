"""Painel: link e QR Code do cadastro pelo celular (Portal do Colaborador).

O QR Code leva somente ao endereco publico do evento
(<URL_PUBLICA>/evento/<id>/cadastro). Nenhum dado pessoal vai nele.
"""

from __future__ import annotations

import io
import re
import socket
from urllib.parse import urlsplit, urlunsplit

import segno
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import evento_atual, requer
from ..models import Event, Participant
from ..permissoes import Permissao
from ..services import push
from ..services.autocadastro import cadastro_aberto

router = APIRouter(prefix="/api/events/{event_id}/portal", tags=["portal"])

GERENCIAR = requer(Permissao.CONFIGURAR_EVENTO)
ORIGEM_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?$")
LOCAIS = {"localhost", "127.0.0.1", "::1"}


def ip_rede_local() -> str | None:
    """IP deste computador na rede local (nenhum pacote e enviado)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def endereco_base(origem: str | None, request: Request) -> tuple[str, str, str | None]:
    """(endereco, fonte, aviso). Fonte: configurada | rede_local | navegador."""
    configurada = settings.url_publica.strip().rstrip("/")
    if configurada:
        aviso = None
        if not configurada.lower().startswith("https://"):
            aviso = "Endereço sem HTTPS: o cadastro funciona, mas as notificações no celular não."
        return configurada, "configurada", aviso

    base = origem.strip().rstrip("/") if origem and ORIGEM_RE.match(origem.strip()) else ""
    if not base:
        base = str(request.base_url).rstrip("/")
    partes = urlsplit(base)
    if (partes.hostname or "") in LOCAIS:
        ip = ip_rede_local()
        if ip:
            porta = f":{partes.port}" if partes.port else ""
            base = urlunsplit((partes.scheme, f"{ip}{porta}", "", "", ""))
            return (
                base,
                "rede_local",
                "Endereço da rede local deste computador: os celulares precisam estar no mesmo "
                "Wi-Fi. Para outro endereço (ex.: HTTPS), defina URL_PUBLICA no servidor.",
            )
        return base, "navegador", "Este endereço só abre neste computador. Defina URL_PUBLICA no servidor."
    return base, "navegador", None


def link_cadastro(evento: Event, base: str) -> str:
    return f"{base}/evento/{evento.id}/cadastro"


@router.get("", dependencies=GERENCIAR)
def situacao(
    request: Request,
    origem: str | None = Query(None, max_length=200),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> dict:
    base, fonte, aviso = endereco_base(origem, request)

    def contar(*condicoes) -> int:  # noqa: ANN002
        return db.scalar(
            select(func.count(Participant.id)).where(Participant.event_id == evento.id, *condicoes)
        ) or 0

    situacao_push = push.configuracao()
    return {
        "url_cadastro": link_cadastro(evento, base),
        "fonte_endereco": fonte,
        "aviso_endereco": aviso,
        "ativo": evento.autocadastro_ativo,
        "aberto": cadastro_aberto(evento),
        "inicio": evento.autocadastro_inicio,
        "fim": evento.autocadastro_fim,
        "participantes": contar(),
        "com_identificacao": contar(Participant.identificacao_hash.is_not(None)),
        "cadastrados": contar(Participant.usuario_id.is_not(None)),
        "push_disponivel": situacao_push.disponivel,
        "push_motivo": situacao_push.motivo,
    }


@router.get("/qrcode.png", dependencies=GERENCIAR)
def qrcode_png(
    request: Request,
    origem: str | None = Query(None, max_length=200),
    escala: int = Query(12, ge=4, le=40),
    evento: Event = Depends(evento_atual),
) -> Response:
    base, _fonte, _aviso = endereco_base(origem, request)
    codigo = segno.make(link_cadastro(evento, base), error="m")
    buffer = io.BytesIO()
    codigo.save(buffer, kind="png", scale=escala, border=4, dark="#111111", light="#FFFFFF")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="qrcode-cadastro-evento-{evento.id}.png"',
            "Cache-Control": "no-store",
        },
    )
