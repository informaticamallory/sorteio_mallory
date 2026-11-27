"""Central de Entregas: localizar ganhadores, conferir e registrar a entrega.

A entrega de uma unidade usa POST /api/events/{id}/sorteios/{draw}/entrega
(CONFIRMAR_ENTREGA; desfazer exige DESFAZER_ENTREGA e justificativa). Aqui
ficam a busca, os indicadores, a lista filtrada, a entrega em lote e o
historico. Tudo e do evento da URL: nada mistura participantes de eventos.
Somente resultados VALIDOS contam; anulados nunca viram pendencia.
"""

from __future__ import annotations

import csv
import io
import math
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer
from ..models import AuditLog, BlocoSorteio, Draw, Event, Participant, Prize, PrizeUnit, StatusSorteio, User
from ..permissoes import Permissao
from ..schemas import (
    AtendimentoOut,
    ColaboradorRecepcaoOut,
    ContagemSituacoesOut,
    EntregaLoteIn,
    EntregasResumoOut,
    FiltrosEntregasOut,
    FotoEntregaIn,
    FotoEntregaOut,
    HistoricoEntregaOut,
    OpcaoFiltroOut,
    PaginaHistoricoEntregasOut,
    PaginaPremiadosOut,
    PremiadoOut,
    PremioGanhoOut,
)
from ..services.consultas import condicao_busca_participante, premios_ganhos
from ..services import fotos_entrega
from ..services.erros import RegraDeNegocio
from ..services.notificacoes import avisar_ganhador
from ..services.sorteio import registrar_entrega
from ..texto import contem, normalizar_busca, normalizar_matricula

router = APIRouter(prefix="/api/events/{event_id}/recepcao", tags=["recepcao"])

LIMITE_BUSCA = 30
ACOES_ENTREGA = ("entrega_registrada", "entrega_revertida")
# Conteudo do QR Code do Cartao da Sorte: so evento e numero (nada pessoal).
QR_SORTE = re.compile(r"^MALLORY-SORTE:(\d+):(\d+)$")

VER = requer(Permissao.PESQUISAR_COLABORADORES)
HISTORICO = requer(Permissao.CONSULTAR_ATENDIMENTOS)
ENTREGAR = exigir_permissao(Permissao.CONFIRMAR_ENTREGA)


def _numero_do_qr(evento: Event, termo: str) -> int | None:
    lido = QR_SORTE.match(termo.strip())
    if lido is None:
        return None
    if int(lido.group(1)) != evento.id:
        # Cartao de outro evento: nao mistura eventos.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este Cartão da Sorte é de outro evento.")
    return int(lido.group(2))


# ------------------------------------------------------------------ busca
@router.get("/busca", response_model=list[ColaboradorRecepcaoOut], dependencies=VER)
def buscar(
    q: str = Query(..., min_length=2, max_length=120, description="Nome, matricula, pulseira, numero da sorte ou QR"),
    somente_ganhadores: bool = Query(False),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> list[ColaboradorRecepcaoOut]:
    termo = q.strip()
    numero_qr = _numero_do_qr(evento, termo)
    if numero_qr is not None:
        condicoes = [Participant.numero_sorteio == numero_qr]
    else:
        # Cada palavra no nome (sem acento), matricula (com ou sem zeros) ou
        # pulseira; ou o numero da sorte exato.
        condicoes = [
            or_(
                and_(*condicao_busca_participante(termo)),
                Participant.numero_sorteio == (int(termo) if termo.isdigit() and len(termo) <= 9 else -1),
            )
        ]
    participantes = db.scalars(
        select(Participant)
        .where(Participant.event_id == evento.id, *condicoes)
        .order_by(Participant.nome_busca)
        .limit(LIMITE_BUSCA)
    ).all()
    premios = premios_ganhos(db, [p.id for p in participantes])
    _com_fotos(db, evento, premios)
    saida = [
        ColaboradorRecepcaoOut(
            id=p.id,
            nome=p.nome,
            matricula=p.matricula,
            setor=p.setor,
            foto_url=p.foto_url,
            pulseira=p.pulseira,
            numero_sorteio=p.numero_sorteio,
            presente=p.presente,
            participando=p.participando,
            premios=[PremioGanhoOut(**item) for item in premios.get(p.id, [])],
        )
        for p in participantes
    ]
    # Ganhadores primeiro; quem tem pendencia antes de quem ja retirou tudo.
    saida.sort(key=lambda c: (not c.premios, all(x.entregue for x in c.premios) if c.premios else True))
    return [c for c in saida if c.premios] if somente_ganhadores else saida


def _com_fotos(db: Session, evento: Event, premios: dict[int, list[dict]]) -> None:
    """Acrescenta a foto atual da entrega a cada premio (so para a equipe)."""
    ids = [item["sorteio_id"] for itens in premios.values() for item in itens if item["entregue"]]
    if not ids:
        return
    sorteios = db.scalars(select(Draw).where(Draw.id.in_(ids))).all()
    fotos = fotos_entrega.fotos_atuais(db, evento.id, list(sorteios))
    for itens in premios.values():
        for item in itens:
            foto = fotos.get(item["sorteio_id"])
            if foto:
                item.update(foto_entrega_url=foto["url"], foto_entrega_em=foto["em"], foto_entrega_por=foto["por"])


@router.post("/entregas/{draw_id}/foto", response_model=FotoEntregaOut)
def foto_da_entrega(
    draw_id: int,
    dados: FotoEntregaIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(ENTREGAR),
) -> FotoEntregaOut:
    """Foto tirada depois da entrega (ou troca). A anterior fica na auditoria."""
    sorteio = db.get(Draw, draw_id)
    if sorteio is None or sorteio.event_id != evento.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resultado não encontrado neste evento")
    try:
        foto = fotos_entrega.registrar_foto(db, sorteio, dados.foto_url, user)
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    return FotoEntregaOut(sorteio_id=sorteio.id, foto_url=foto["url"], foto_em=foto["em"], foto_por=foto["por"])


# ------------------------------------------------------------------ indicadores
@router.get("/resumo", response_model=EntregasResumoOut, dependencies=VER)
def resumo(evento: Event = Depends(evento_atual), db: Session = Depends(get_db)) -> EntregasResumoOut:
    sorteados, entregues = db.execute(
        select(func.count(Draw.id), func.coalesce(func.sum(case((Draw.entregue.is_(True), 1), else_=0)), 0)).where(
            Draw.event_id == evento.id, Draw.status == StatusSorteio.VALIDO.value
        )
    ).one()
    entregues = int(entregues or 0)
    return EntregasResumoOut(
        sorteados=sorteados,
        entregues=entregues,
        pendentes=sorteados - entregues,
        percentual=round(100 * entregues / sorteados) if sorteados else 0,
    )


# ------------------------------------------------------------------ filtros
def _limites(evento: Event, de: date | None, ate: date | None) -> tuple[datetime | None, datetime | None]:
    """Datas no fuso do evento -> instantes UTC (o banco guarda UTC)."""
    fuso = ZoneInfo(evento.fuso_horario or "America/Sao_Paulo")

    def utc(d: date) -> datetime:
        return datetime.combine(d, time.min, fuso).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    return (utc(de) if de else None, utc(ate + timedelta(days=1)) if ate else None)


def _rotulo_bloco(b: BlocoSorteio) -> str:
    """Rotulo do bloco no filtro, sem repetir o numero quando o nome ja e "Bloco 03"."""
    numero = f"Bloco {b.numero_exibicao:02d}"
    if b.nome.strip().casefold() in {numero.casefold(), f"bloco {b.numero_exibicao}"}:
        return f"{numero} (excluído)" if b.excluido_em is not None else numero
    return f"{numero} — {b.nome_exibicao}"


@router.get("/filtros", response_model=FiltrosEntregasOut, dependencies=VER)
def filtros(evento: Event = Depends(evento_atual), db: Session = Depends(get_db)) -> FiltrosEntregasOut:
    """Opcoes dos filtros (blocos, premios e operadores que ja entregaram)."""
    blocos = db.scalars(
        select(BlocoSorteio).where(BlocoSorteio.event_id == evento.id).order_by(BlocoSorteio.ordem)
    ).all()
    premios = db.scalars(select(Prize).where(Prize.event_id == evento.id).order_by(Prize.ordem, Prize.id)).all()
    operadores = db.execute(
        select(User.id, User.nome)
        .join(AuditLog, AuditLog.usuario_id == User.id)
        .where(AuditLog.event_id == evento.id, AuditLog.acao.in_(ACOES_ENTREGA))
        .distinct()
        .order_by(User.nome)
    ).all()
    return FiltrosEntregasOut(
        blocos=[OpcaoFiltroOut(id=b.id, nome=_rotulo_bloco(b)) for b in blocos],
        premios=[OpcaoFiltroOut(id=p.id, nome=p.nome) for p in premios],
        operadores=[OpcaoFiltroOut(id=i, nome=n) for i, n in operadores],
    )


# ------------------------------------------------------------------ lista de premiados
@router.get("/premiados", response_model=PaginaPremiadosOut, dependencies=VER)
def premiados(
    situacao: str = Query("pendentes", pattern="^(todos|pendentes|entregues)$"),
    bloco_id: int | None = Query(None),
    premio_id: int | None = Query(None),
    de: date | None = Query(None),
    ate: date | None = Query(None),
    operador_id: int | None = Query(None),
    q: str = Query("", max_length=120),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> PaginaPremiadosOut:
    """Unidades com ganhador valido. O periodo vale sobre a data da ENTREGA
    quando a situacao e "entregues" e sobre a data do SORTEIO nos demais casos."""
    entregador = aliased(User)
    condicoes = [Draw.event_id == evento.id, Draw.status == StatusSorteio.VALIDO.value]
    if bloco_id is not None:
        condicoes.append(Draw.bloco_id == bloco_id)
    if premio_id is not None:
        condicoes.append(Prize.id == premio_id)
    if operador_id is not None:
        condicoes.append(Draw.entregue_por_id == operador_id)
    inicio, fim = _limites(evento, de, ate)

    def da_situacao(s: str) -> list:
        """Situacao + periodo (a coluna da data depende da situacao)."""
        extra: list = []
        if s == "pendentes":
            extra.append(Draw.entregue.is_(False))
        elif s == "entregues":
            extra.append(Draw.entregue.is_(True))
        coluna_data = Draw.entregue_em if s == "entregues" else Draw.criado_em
        if inicio is not None:
            extra.append(coluna_data >= inicio)
        if fim is not None:
            extra.append(coluna_data < fim)
        return extra

    termo = q.strip()
    if termo:
        numero_qr = _numero_do_qr(evento, termo)
        if numero_qr is not None:
            condicoes.append(Participant.numero_sorteio == numero_qr)
        else:
            for parte in termo.split():
                condicoes.append(
                    or_(
                        contem(Participant.nome_busca, normalizar_busca(parte)),
                        contem(Participant.matricula, parte),
                        Participant.matricula_normalizada == normalizar_matricula(parte),
                        contem(Participant.pulseira, parte.upper()),
                        contem(Prize.nome_busca, normalizar_busca(parte)),
                        Participant.numero_sorteio == (int(parte) if parte.isdigit() and len(parte) <= 9 else -1),
                    )
                )

    def consulta(s: str):
        return (
            select(Draw, Participant, PrizeUnit, Prize, BlocoSorteio, entregador)
            .join(Participant, Draw.participant_id == Participant.id)
            .join(PrizeUnit, Draw.prize_unit_id == PrizeUnit.id)
            .join(Prize, PrizeUnit.prize_id == Prize.id)
            .outerjoin(BlocoSorteio, Draw.bloco_id == BlocoSorteio.id)
            .outerjoin(entregador, Draw.entregue_por_id == entregador.id)
            .where(*condicoes, *da_situacao(s))
        )

    def contar(s: str) -> int:
        return db.scalar(select(func.count()).select_from(consulta(s).subquery())) or 0

    contagem = {s: contar(s) for s in ("pendentes", "entregues", "todos")}
    base = consulta(situacao)
    total = contagem[situacao]
    ordem = (Draw.entregue_em.desc(),) if situacao == "entregues" else (Participant.nome_busca, Draw.rodada)
    linhas = db.execute(base.order_by(*ordem).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    com_foto = fotos_entrega.fotos_atuais(db, evento.id, [linha[0] for linha in linhas])
    return PaginaPremiadosOut(
        itens=[
            PremiadoOut(
                sorteio_id=d.id,
                participante_id=p.id,
                nome=p.nome,
                matricula=p.matricula,
                pulseira=p.pulseira,
                numero_sorteio=p.numero_sorteio,
                foto_url=p.foto_url,
                setor=p.setor,
                premio_id=pr.id,
                premio_nome=pr.nome,
                premio_imagem_url=pr.imagem_url,
                unidade_numero=u.numero,
                quantidade_premio=pr.quantidade,
                bloco_numero=b.numero_exibicao if b else None,
                sorteado_em=d.criado_em,
                entregue=d.entregue,
                entregue_em=d.entregue_em,
                entregue_por=quem.nome if quem else None,
                tem_foto_entrega=d.id in com_foto,
            )
            for d, p, u, pr, b, quem in linhas
        ],
        total=total,
        pagina=pagina,
        paginas=max(1, math.ceil(total / por_pagina)),
        contagem=ContagemSituacoesOut(**contagem),
    )


# ------------------------------------------------------------------ entrega em lote
@router.post("/entregar", response_model=EntregasResumoOut)
def entregar_lote(
    dados: EntregaLoteIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(ENTREGAR),
) -> EntregasResumoOut:
    """Confirma varias unidades do MESMO ganhador numa transacao: ou todas, ou nenhuma.

    Cada unidade ganha o proprio registro (auditoria e estado de entrega).
    Unidade anulada, ja entregue ou de outro evento recusa o lote inteiro.
    """
    ids = list(dict.fromkeys(dados.sorteios))
    sorteios = db.scalars(select(Draw).where(Draw.id.in_(ids))).all()
    if len(sorteios) != len(ids) or any(s.event_id != evento.id for s in sorteios):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resultado não encontrado neste evento")
    if len({s.participant_id for s in sorteios}) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Confirme em lote só prêmios do mesmo ganhador (um atendimento por vez).",
        )
    try:
        for sorteio in sorted(sorteios, key=lambda s: ids.index(s.id)):
            registrar_entrega(db, sorteio, True, user, dados.pulseira_conferida, foto_url=dados.foto_url)
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    for sorteio in sorteios:
        db.refresh(sorteio)
    # Portal do Colaborador: "Meus Premios" atualiza na hora.
    avisar_ganhador(db, sorteios[0], "atualizacao")
    return resumo(evento, db)


# ------------------------------------------------------------------ historico
@router.get("/atendimentos", response_model=list[AtendimentoOut], dependencies=HISTORICO)
def atendimentos(
    evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> list[AtendimentoOut]:
    """Entregas confirmadas e desfeitas no evento, mais recentes primeiro (ultimas 200)."""
    linhas = db.scalars(
        select(AuditLog)
        .where(AuditLog.event_id == evento.id, AuditLog.acao.in_(ACOES_ENTREGA))
        .order_by(AuditLog.criado_em.desc(), AuditLog.id.desc())
        .limit(200)
    ).all()
    return [_atendimento(db, linha) for linha in linhas]


def _consulta_historico(
    evento: Event,
    acao: str,
    de: date | None,
    ate: date | None,
    operador_id: int | None,
    bloco_id: int | None,
    premio_id: int | None,
):
    sorteio_id = AuditLog.detalhes["sorteio_id"].as_integer()
    consulta = (
        select(AuditLog, Draw)
        # So vale o resultado que ja existia no registro: depois da limpeza dos
        # dados de demonstracao, o SQLite reaproveita ids de resultados apagados.
        .outerjoin(Draw, and_(Draw.id == sorteio_id, Draw.criado_em <= AuditLog.criado_em))
        .where(AuditLog.event_id == evento.id, AuditLog.acao.in_(ACOES_ENTREGA))
    )
    if acao == "confirmadas":
        consulta = consulta.where(AuditLog.acao == "entrega_registrada")
    elif acao == "desfeitas":
        consulta = consulta.where(AuditLog.acao == "entrega_revertida")
    inicio, fim = _limites(evento, de, ate)
    if inicio is not None:
        consulta = consulta.where(AuditLog.criado_em >= inicio)
    if fim is not None:
        consulta = consulta.where(AuditLog.criado_em < fim)
    if operador_id is not None:
        consulta = consulta.where(AuditLog.usuario_id == operador_id)
    if bloco_id is not None:
        consulta = consulta.where(Draw.bloco_id == bloco_id)
    if premio_id is not None:
        consulta = consulta.join(PrizeUnit, Draw.prize_unit_id == PrizeUnit.id).where(PrizeUnit.prize_id == premio_id)
    return consulta


def _historico_item(db: Session, linha: AuditLog, sorteio: Draw | None) -> HistoricoEntregaOut:
    base = _atendimento(db, linha)
    detalhes = linha.detalhes or {}
    matricula = detalhes.get("matricula")
    bloco_numero = None
    situacao = None
    if sorteio is not None:
        if matricula is None:
            ganhador = db.get(Participant, sorteio.participant_id)
            matricula = ganhador.matricula if ganhador else None
        bloco = db.get(BlocoSorteio, sorteio.bloco_id) if sorteio.bloco_id else None
        bloco_numero = bloco.numero_exibicao if bloco else None
        situacao = (
            "anulado"
            if sorteio.status != StatusSorteio.VALIDO.value
            else ("entregue" if sorteio.entregue else "pendente")
        )
    return HistoricoEntregaOut(
        id=linha.id,
        acao=linha.acao,
        criado_em=linha.criado_em,
        atendente=base.atendente,
        sorteio_id=detalhes.get("sorteio_id"),
        participante=base.participante,
        matricula=matricula,
        premio=base.premio,
        unidade=base.unidade,
        bloco_numero=bloco_numero,
        pulseira_conferida=base.pulseira_conferida,
        motivo=detalhes.get("motivo"),
        situacao_atual=situacao,
        foto_url=detalhes.get("foto_url"),
    )


@router.get("/historico", response_model=PaginaHistoricoEntregasOut, dependencies=HISTORICO)
def historico(
    acao: str = Query("todas", pattern="^(todas|confirmadas|desfeitas)$"),
    de: date | None = Query(None),
    ate: date | None = Query(None),
    operador_id: int | None = Query(None),
    bloco_id: int | None = Query(None),
    premio_id: int | None = Query(None),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(15, ge=1, le=100),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> PaginaHistoricoEntregasOut:
    """Historico de atendimentos (confirmacoes e desfazimentos), paginado e filtravel."""
    consulta = _consulta_historico(evento, acao, de, ate, operador_id, bloco_id, premio_id)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    linhas = db.execute(
        consulta.order_by(AuditLog.criado_em.desc(), AuditLog.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return PaginaHistoricoEntregasOut(
        itens=[_historico_item(db, linha, sorteio) for linha, sorteio in linhas],
        total=total,
        pagina=pagina,
        paginas=max(1, math.ceil(total / por_pagina)),
    )


@router.get(
    "/historico/export.csv",
    dependencies=requer(Permissao.CONSULTAR_ATENDIMENTOS, Permissao.EXPORTAR_RESULTADOS),
)
def exportar_historico(
    acao: str = Query("todas", pattern="^(todas|confirmadas|desfeitas)$"),
    de: date | None = Query(None),
    ate: date | None = Query(None),
    operador_id: int | None = Query(None),
    bloco_id: int | None = Query(None),
    premio_id: int | None = Query(None),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> Response:
    """CSV do historico de entregas (so perfis com permissao de exportar)."""
    consulta = _consulta_historico(evento, acao, de, ate, operador_id, bloco_id, premio_id)
    linhas = db.execute(consulta.order_by(AuditLog.criado_em.desc(), AuditLog.id.desc())).all()
    fuso = ZoneInfo(evento.fuso_horario or "America/Sao_Paulo")
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        ["data_hora", "acao", "colaborador", "matricula", "premio", "unidade", "bloco", "operador", "pulseira_conferida", "motivo", "situacao_atual"]
    )
    for linha, sorteio in linhas:
        item = _historico_item(db, linha, sorteio)
        quando = item.criado_em.replace(tzinfo=ZoneInfo("UTC")).astimezone(fuso).strftime("%d/%m/%Y %H:%M:%S")
        escritor.writerow(
            [
                quando,
                "Entrega confirmada" if item.acao == "entrega_registrada" else "Entrega desfeita",
                item.participante or "",
                item.matricula or "",
                item.premio or "",
                item.unidade or "",
                f"{item.bloco_numero:02d}" if item.bloco_numero else "",
                item.atendente,
                item.pulseira_conferida or "",
                item.motivo or "",
                item.situacao_atual or "",
            ]
        )
    return Response(
        content=("﻿" + buffer.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="entregas-evento-{evento.id}.csv"'},
    )


def _atendimento(db: Session, linha: AuditLog) -> AtendimentoOut:
    detalhes = dict(linha.detalhes or {})
    # Registros anteriores a Fase 4 guardavam so o sorteio_id: completa a
    # partir do resultado, que nunca e apagado.
    if "participante" not in detalhes and detalhes.get("sorteio_id"):
        sorteio = db.get(Draw, detalhes["sorteio_id"])
        # Resultado criado DEPOIS do registro: o original foi apagado (dados de
        # demonstracao) e o id foi reaproveitado. Nao "empresta" o nome de outro.
        if sorteio is not None and sorteio.criado_em <= linha.criado_em:
            ganhador = db.get(Participant, sorteio.participant_id)
            unidade = db.get(PrizeUnit, sorteio.prize_unit_id)
            premio = db.get(Prize, unidade.prize_id) if unidade else None
            detalhes.update(
                participante=ganhador.nome if ganhador else None,
                premio=premio.nome if premio else None,
                unidade=unidade.numero if unidade else None,
            )
    return AtendimentoOut(
        id=linha.id,
        acao=linha.acao,
        criado_em=linha.criado_em,
        atendente=linha.usuario.nome if linha.usuario else "",
        participante=detalhes.get("participante"),
        premio=detalhes.get("premio"),
        unidade=detalhes.get("unidade"),
        pulseira_conferida=detalhes.get("pulseira_conferida"),
    )
