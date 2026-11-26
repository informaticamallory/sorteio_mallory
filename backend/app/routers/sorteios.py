from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer
from ..permissoes import Permissao, tem_permissao
from ..models import (
    BlocoSorteio,
    Draw,
    EstadoTelao,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    StatusSorteio,
    StatusUnidade,
    User,
)
from ..schemas import (
    AnularIn,
    CarrosselComandoIn,
    ElegiveisOut,
    EntregaIn,
    SorteioOut,
    SortearIn,
    TelaoComandoIn,
)
from ..services.blocos import bloqueio_do_bloco, proxima_do_bloco
from ..services.elegibilidade import participantes_elegiveis
from ..services.notificacoes import avisar_ganhador
from ..services.sorteio import (
    RegraDeNegocio,
    anular_sorteio,
    realizar_sorteio,
    registrar_entrega,
    serializar_sorteio,
)
from ..services import carrossel
from ..services.telao import (
    definir_estado,
    nomes_para_animacao,
    obter_estado,
    preparar_revelacao,
    publicar_estado,
)

router = APIRouter(prefix="/api/events/{event_id}", tags=["sorteio"])

SORTEAR = exigir_permissao(Permissao.CONTROLAR_SORTEIO)
ENTREGAR = exigir_permissao(Permissao.CONFIRMAR_ENTREGA)
ANULAR = exigir_permissao(Permissao.ANULAR_RESULTADO)
TELAO = requer(Permissao.CONTROLAR_TELAO)


def _buscar_sorteio(db: Session, evento: Event, draw_id: int) -> Draw:
    sorteio = db.get(Draw, draw_id)
    if sorteio is None or sorteio.event_id != evento.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resultado não encontrado")
    return sorteio


@router.get("/sorteio/elegiveis", response_model=ElegiveisOut)
def conferir_elegiveis(
    prize_unit_id: int | None = Query(default=None),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(SORTEAR),
) -> ElegiveisOut:
    elegiveis = participantes_elegiveis(db, evento)
    bloqueios: list[str] = []
    fora_da_ordem = False
    proxima_unidade_id = None

    if not elegiveis:
        bloqueios.append("Nenhum participante elegível conforme as regras configuradas.")

    if prize_unit_id is not None:
        unidade = db.get(PrizeUnit, prize_unit_id)
        premio = db.get(Prize, unidade.prize_id) if unidade else None
        if unidade is None or premio is None or premio.event_id != evento.id:
            bloqueios.append("Unidade de prêmio inválida para este evento.")
        elif unidade.status != StatusUnidade.DISPONIVEL.value:
            bloqueios.append("Esta unidade do prêmio já foi sorteada.")
        else:
            motivo = bloqueio_do_bloco(db, evento, unidade)
            if motivo:
                bloqueios.append(motivo)
            elif unidade.bloco_id is not None:
                proxima = proxima_do_bloco(db, unidade.bloco_id)
                if proxima is not None and proxima[0].id != unidade.id:
                    fora_da_ordem = True
                    proxima_unidade_id = proxima[0].id
                    if not tem_permissao(user, Permissao.PULAR_ORDEM_DO_BLOCO):
                        bloqueios.append(
                            f"Siga a sequência do bloco: o próximo prêmio é {proxima[1].nome} "
                            f"(unidade {proxima[0].numero})."
                        )
    else:
        bloqueios.append("Selecione uma unidade de prêmio disponível.")

    return ElegiveisOut(
        total=len(elegiveis),
        bloqueios=bloqueios,
        pode_sortear=not bloqueios,
        fora_da_ordem=fora_da_ordem,
        proxima_unidade_id=proxima_unidade_id,
    )


def _agendar_carrossel_no_fim_do_bloco(db: Session, evento: Event, sorteio, user: User) -> None:
    """Ultimo premio do bloco sorteado: o telao passa sozinho ao carrossel dos
    ganhadores, alguns segundos depois da revelacao (a animacao nao e cortada).

    So agenda a apresentacao: nao finaliza o bloco (isso continua com o operador,
    que confere os ausentes) e nao inicia o proximo. Na mesma transacao do
    sorteio, sem commit. Bloco sem ganhador para mostrar: nada acontece.
    """
    if sorteio.bloco_id is None or proxima_do_bloco(db, sorteio.bloco_id) is not None:
        return
    bloco = db.get(BlocoSorteio, sorteio.bloco_id)
    if bloco is None:
        return
    try:
        carrossel.iniciar(db, evento, bloco, user, automatico=True)
    except RegraDeNegocio:
        pass  # sem slides: o sorteio segue normal, sem apresentacao


@router.post("/sorteio", response_model=SorteioOut)
def sortear(
    dados: SortearIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(SORTEAR),
) -> SorteioOut:
    """Sorteia e PERSISTE o resultado antes de qualquer comunicacao ao telao."""
    display = None
    try:
        sorteio, reaproveitado = realizar_sorteio(
            db, evento, dados.prize_unit_id, dados.idempotency_key, user, dados.motivo_fora_da_ordem
        )
        if not reaproveitado:
            # O telao recebe apenas nomes para a animacao -- nunca a lista
            # completa de participantes nem matriculas. O estado "sorteando" e
            # gravado na mesma transacao do resultado (ver preparar_revelacao).
            elegiveis = list(
                db.scalars(
                    select(Participant).where(Participant.id.in_(sorteio.elegiveis_ids or [0]))
                ).all()
            )
            display = preparar_revelacao(
                db,
                evento,
                sorteio,
                nomes_para_animacao(elegiveis, sorteio.participant_id),
                evento.duracao_animacao_ms,
            )
            _agendar_carrossel_no_fim_do_bloco(db, evento, sorteio, user)
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc

    db.refresh(sorteio)
    saida = serializar_sorteio(db, sorteio)
    saida["reaproveitado"] = reaproveitado

    if display is not None:
        # So depois do commit o telao e avisado.
        telao = publicar_estado(db, evento, display)
        # O celular do ganhador e avisado no instante da revelacao, pelo canal privado.
        avisar_ganhador(db, sorteio, "notificacao", quando=telao.get("revelar_em"))

    return SorteioOut(**saida)


@router.post("/sorteios/{draw_id}/entrega", response_model=SorteioOut)
def entrega(
    draw_id: int,
    dados: EntregaIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(ENTREGAR),
) -> SorteioOut:
    sorteio = _buscar_sorteio(db, evento, draw_id)
    # Desfazer e de quem tem DESFAZER_ENTREGA (admin e Organizador - RH).
    if not dados.entregue and not tem_permissao(user, Permissao.DESFAZER_ENTREGA):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Seu perfil não pode desfazer entregas. Procure o RH ou um administrador."
        )
    try:
        registrar_entrega(db, sorteio, dados.entregue, user, dados.pulseira_conferida, dados.motivo)
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    db.refresh(sorteio)
    # A area pessoal do ganhador atualiza a situacao da retirada na hora.
    avisar_ganhador(db, sorteio, "atualizacao")
    return SorteioOut(**serializar_sorteio(db, sorteio))


@router.post("/sorteios/{draw_id}/anular", response_model=SorteioOut)
def anular(
    draw_id: int,
    dados: AnularIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(ANULAR),
) -> SorteioOut:
    sorteio = _buscar_sorteio(db, evento, draw_id)
    try:
        anular_sorteio(db, sorteio, dados.motivo, dados.tipo, dados.confirmar_estorno, user)
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    db.refresh(sorteio)
    avisar_ganhador(db, sorteio, "notificacao")

    # Se o telao estava mostrando este resultado, volta para a apresentacao do premio.
    estado = obter_estado(db, evento)
    if estado.get("estado") in {EstadoTelao.RESULTADO.value, EstadoTelao.SORTEANDO.value}:
        unidade = db.get(PrizeUnit, sorteio.prize_unit_id)
        if unidade is not None and unidade.status == StatusUnidade.REMOVIDO.value:
            # Premio excluido: nao ha o que sortear de novo.
            definir_estado(db, evento, EstadoTelao.AGUARDANDO.value)
        else:
            definir_estado(
                db, evento, EstadoTelao.PREMIO.value, prize_unit_id=sorteio.prize_unit_id
            )

    return SorteioOut(**serializar_sorteio(db, sorteio))


@router.get(
    "/historico",
    response_model=list[SorteioOut],
    dependencies=requer(Permissao.CONSULTAR_RESULTADOS),
)
def historico(
    apenas: str = Query("todos", pattern="^(todos|validos|anulados|entregues|pendentes)$"),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> list[SorteioOut]:
    condicoes = [Draw.event_id == evento.id]
    if apenas == "validos":
        condicoes.append(Draw.status == StatusSorteio.VALIDO.value)
    elif apenas == "anulados":
        condicoes.append(Draw.status == StatusSorteio.ANULADO.value)
    elif apenas == "entregues":
        condicoes += [Draw.status == StatusSorteio.VALIDO.value, Draw.entregue.is_(True)]
    elif apenas == "pendentes":
        condicoes += [Draw.status == StatusSorteio.VALIDO.value, Draw.entregue.is_(False)]

    linhas = db.scalars(
        select(Draw).where(*condicoes).order_by(Draw.rodada.desc(), Draw.id.desc())
    ).all()
    return [SorteioOut(**serializar_sorteio(db, linha)) for linha in linhas]


# ------------------------------------------------------------------ telao
@router.get("/telao/estado", dependencies=TELAO)
def estado_telao_autenticado(
    evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> dict:
    return obter_estado(db, evento)


@router.post("/telao", dependencies=TELAO)
def comandar_telao(
    dados: TelaoComandoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> dict:
    """Muda o estado do telao. Nao realiza sorteio nem revela ganhador por si so."""
    if dados.estado == EstadoTelao.SORTEANDO.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "O estado 'sorteando' só é definido pelo backend ao realizar um sorteio.",
        )

    draw_id = None
    if dados.estado == EstadoTelao.RESULTADO.value:
        if dados.prize_unit_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Informe a unidade do prêmio")
        sorteio = db.scalar(
            select(Draw).where(
                Draw.prize_unit_id == dados.prize_unit_id,
                Draw.status == StatusSorteio.VALIDO.value,
            )
        )
        if sorteio is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Não há resultado válido para esta unidade"
            )
        draw_id = sorteio.id

    if dados.prize_unit_id is not None:
        unidade = db.get(PrizeUnit, dados.prize_unit_id)
        premio = db.get(Prize, unidade.prize_id) if unidade else None
        if premio is None or premio.event_id != evento.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unidade inválida para este evento")

    return definir_estado(
        db, evento, dados.estado, prize_unit_id=dados.prize_unit_id, draw_id=draw_id
    )


@router.post("/telao/carrossel")
def comandar_carrossel(
    dados: CarrosselComandoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(exigir_permissao(Permissao.CONTROLAR_TELAO)),
) -> dict:
    """Controla a apresentacao dos ganhadores. So le resultados: nunca sorteia."""
    try:
        if dados.acao == "iniciar":
            bloco = db.get(BlocoSorteio, dados.bloco_id) if dados.bloco_id else None
            if bloco is None or bloco.event_id != evento.id:
                raise RegraDeNegocio("Informe um bloco deste evento.", 422)
            ds = carrossel.iniciar(db, evento, bloco, user)
        else:
            ds = carrossel.comandar(db, evento, dados.acao, user)
        return publicar_estado(db, evento, ds)
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
