"""Foto da entrega: tirada no balcao (junto com a entrega) ou depois.

Nao ha coluna propria: a foto fica na auditoria, que e o registro oficial.
  * entrega_registrada: pode trazer a foto tirada na hora (detalhes.foto_url);
  * entrega_foto: foto tirada depois da entrega (ou trocada). A anterior
    continua na auditoria; vale a mais recente;
  * entrega_revertida: a entrega desfeita deixa de ter foto atual (o
    historico continua com ela).

Fica so para a equipe: nao vai ao telao nem ao portal do colaborador.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, Draw, Participant, Prize, PrizeUnit, StatusSorteio, User
from .autocadastro import apagar_foto
from .erros import RegraDeNegocio

ACOES_FOTO = ("entrega_registrada", "entrega_revertida", "entrega_foto")


def fotos_atuais(db: Session, event_id: int, sorteios: list[Draw]) -> dict[int, dict]:
    """Foto atual de cada sorteio entregue: {sorteio_id: {url, em, por}}."""
    entregues = {s.id: s for s in sorteios if s.entregue}
    if not entregues:
        return {}
    sorteio_id = AuditLog.detalhes["sorteio_id"].as_integer()
    linhas = db.execute(
        select(AuditLog, User.nome)
        .outerjoin(User, AuditLog.usuario_id == User.id)
        .where(
            AuditLog.event_id == event_id,
            AuditLog.acao.in_(ACOES_FOTO),
            sorteio_id.in_(list(entregues)),
        )
        .order_by(AuditLog.criado_em, AuditLog.id)
    ).all()
    atuais: dict[int, dict] = {}
    for registro, quem in linhas:
        detalhes = registro.detalhes or {}
        sid = detalhes.get("sorteio_id")
        sorteio = entregues.get(sid)
        # O SQLite reaproveita ids de sorteios apagados (Recomecar teste): so
        # vale o registro feito depois deste sorteio.
        if sorteio is None or registro.criado_em < sorteio.criado_em:
            continue
        if registro.acao == "entrega_revertida":
            atuais.pop(sid, None)
            continue
        if registro.acao == "entrega_registrada":
            atuais.pop(sid, None)
        url = detalhes.get("foto_url")
        if url:
            atuais[sid] = {"url": url, "em": registro.criado_em, "por": quem}
    return atuais


def registrar_foto(db: Session, sorteio: Draw, foto_url: str, usuario: User) -> dict:
    """Foto tirada depois da entrega (ou troca da atual). Nao faz commit."""
    if sorteio.status != StatusSorteio.VALIDO.value:
        raise RegraDeNegocio("Este resultado foi anulado: não há entrega para fotografar.", 409)
    if not sorteio.entregue:
        raise RegraDeNegocio("Confirme a entrega antes de registrar a foto.", 409)
    anterior = fotos_atuais(db, sorteio.event_id, [sorteio]).get(sorteio.id)
    ganhador = db.get(Participant, sorteio.participant_id)
    unidade = db.get(PrizeUnit, sorteio.prize_unit_id)
    premio = db.get(Prize, unidade.prize_id) if unidade else None
    registro = AuditLog(
        event_id=sorteio.event_id,
        usuario_id=usuario.id,
        acao="entrega_foto",
        detalhes={
            "sorteio_id": sorteio.id,
            "participante_id": sorteio.participant_id,
            "participante": ganhador.nome if ganhador else None,
            "premio": premio.nome if premio else None,
            "unidade": unidade.numero if unidade else None,
            "foto_url": foto_url,
            "foto_anterior": anterior["url"] if anterior else None,
        },
    )
    db.add(registro)
    db.flush()
    return {"url": foto_url, "em": registro.criado_em, "por": usuario.nome}


def urls_do_evento(db: Session, event_id: int) -> set[str]:
    """Todas as fotos de entrega registradas no evento (para apagar com ele)."""
    registros = db.scalars(
        select(AuditLog).where(AuditLog.event_id == event_id, AuditLog.acao.in_(ACOES_FOTO))
    ).all()
    return {r.detalhes["foto_url"] for r in registros if (r.detalhes or {}).get("foto_url")}


def apagar_arquivos(urls: set[str]) -> None:
    """Apaga os arquivos depois do commit (LGPD: a foto mostra a pessoa)."""
    for url in urls:
        apagar_foto(url)
