from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer
from ..permissoes import Permissao
from ..models import (
    BlocoSorteio,
    DisplayState,
    Draw,
    EstadoTelao,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    StatusBloco,
    StatusSorteio,
    User,
)
from ..schemas import (
    BlocoComUnidadesOut,
    BlocoDetalheOut,
    BlocoIn,
    BlocoOut,
    BlocosOut,
    BlocoUpdate,
    DistribuicaoIn,
    DistribuicaoOut,
    DistribuirIn,
    DistribuirNosBlocosIn,
    PreviaNosBlocosOut,
    FinalizarBlocoIn,
    GanhadorBlocoOut,
    PreviaDistribuicaoOut,
    RemanescentesIn,
    ReordenarBlocosIn,
    SorteioOut,
    UnidadeBlocoOut,
)
from ..services import blocos as servico
from ..services import carrossel
from ..services.erros import RegraDeNegocio
from ..services.sorteio import serializar_sorteio
from ..services.telao import publicar_estado

router = APIRouter(prefix="/api/events/{event_id}/blocos", tags=["blocos"])

# Distribuir e editar e do admin; o operador ve os blocos e os conduz
# (iniciar, pausar, finalizar).
CONFIGURAR = exigir_permissao(Permissao.CONFIGURAR_BLOCOS)
# Excluir bloco (em qualquer situacao): so o admin.
EXCLUIR = exigir_permissao(Permissao.EXCLUIR_BLOCOS)
CONDUZIR = exigir_permissao(Permissao.CONTROLAR_SORTEIO)
VER = requer(Permissao.VISUALIZAR_BLOCOS)

T = TypeVar("T")


def _executar(db: Session, acao: Callable[[], T]) -> T:
    """Roda a regra de negocio e confirma; em violacao, desfaz e responde HTTP."""
    try:
        resultado = acao()
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    return resultado


def _buscar(db: Session, evento: Event, bloco_id: int) -> BlocoSorteio:
    bloco = db.get(BlocoSorteio, bloco_id)
    if bloco is None or bloco.event_id != evento.id or bloco.excluido_em is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bloco não encontrado")
    return bloco


def _bloco_out(db: Session, bloco: BlocoSorteio, progresso: servico.Progresso) -> BlocoOut:
    finalizado_por = db.get(User, bloco.finalizado_por_id) if bloco.finalizado_por_id else None
    return BlocoOut(
        id=bloco.id,
        numero=bloco.numero,
        nome=bloco.nome,
        descricao=bloco.descricao,
        capacidade=bloco.capacidade,
        status=bloco.status,
        ordem=bloco.ordem,
        criado_em=bloco.criado_em,
        iniciado_em=bloco.iniciado_em,
        finalizado_em=bloco.finalizado_em,
        finalizado_por=finalizado_por.nome if finalizado_por else None,
        total=progresso.total,
        sorteadas=progresso.sorteadas,
        entregues=progresso.entregues,
        restantes=progresso.restantes,
        percentual=progresso.percentual,
    )


def _vencedores(db: Session, evento: Event) -> dict[int, Participant]:
    linhas = db.execute(
        select(Draw.prize_unit_id, Participant)
        .join(Participant, Draw.participant_id == Participant.id)
        .where(Draw.event_id == evento.id, Draw.status == StatusSorteio.VALIDO.value)
    ).all()
    return {unidade_id: participante for unidade_id, participante in linhas}


def _unidade_out(
    unidade: PrizeUnit, premio: Prize, vencedores: dict[int, Participant]
) -> UnidadeBlocoOut:
    ganhador = vencedores.get(unidade.id)
    return UnidadeBlocoOut(
        id=unidade.id,
        prize_id=premio.id,
        premio_nome=premio.nome,
        premio_imagem_url=premio.imagem_url,
        numero=unidade.numero,
        quantidade_premio=premio.quantidade,
        status=unidade.status,
        bloco_id=unidade.bloco_id,
        ordem_bloco=unidade.ordem_bloco,
        ganhador_nome=ganhador.nome if ganhador else None,
        ganhador_setor=ganhador.setor if ganhador else None,
    )


def _listar(db: Session, evento: Event) -> BlocosOut:
    blocos = servico.blocos_do_evento(db, evento.id)
    progresso = servico.progresso_por_bloco(db, evento.id)
    sem_bloco = progresso.get(None, servico.Progresso())
    ativo = next((b for b in blocos if b.status == "EM_ANDAMENTO"), None)
    return BlocosOut(
        blocos=[_bloco_out(db, b, progresso[b.id]) for b in blocos],
        capacidade_padrao=evento.capacidade_bloco_padrao,
        bloco_ativo_id=ativo.id if ativo else None,
        modo_blocos=bool(blocos),
        unidades_total=sum(p.total for p in progresso.values()),
        unidades_sem_bloco=sem_bloco.restantes,
        unidades_remanescentes=servico.contagem_remanescentes(db, evento.id),
        sorteadas_sem_bloco=sem_bloco.sorteadas,
    )


def _distribuicao(db: Session, evento: Event) -> DistribuicaoOut:
    vencedores = _vencedores(db, evento)
    progresso = servico.progresso_por_bloco(db, evento.id)
    blocos = [
        BlocoComUnidadesOut(
            bloco=_bloco_out(db, bloco, progresso[bloco.id]),
            unidades=[
                _unidade_out(u, p, vencedores)
                for u, p in servico.unidades_ordenadas_do_bloco(db, bloco)
            ],
        )
        for bloco in servico.blocos_do_evento(db, evento.id)
    ]
    sem_bloco = [
        (u, p) for u, p in servico.unidades_do_evento(db, evento.id) if u.bloco_id is None
    ]
    return DistribuicaoOut(
        blocos=blocos,
        sem_bloco=[_unidade_out(u, p, vencedores) for u, p in sem_bloco if u.status == "disponivel"],
        sorteadas_sem_bloco=sum(1 for u, _p in sem_bloco if u.status != "disponivel"),
        versao=servico.versao_distribuicao(db, evento.id),
    )


def _bloco_atual(db: Session, evento: Event, bloco: BlocoSorteio) -> BlocoOut:
    db.refresh(bloco)
    return _bloco_out(db, bloco, servico.progresso_por_bloco(db, evento.id)[bloco.id])


# ------------------------------------------------------------------ colecao
@router.get("", response_model=BlocosOut, dependencies=VER)
def listar(evento: Event = Depends(evento_atual), db: Session = Depends(get_db)) -> BlocosOut:
    return _listar(db, evento)


@router.post("", response_model=BlocoOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: BlocoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> BlocoOut:
    bloco = _executar(
        db,
        lambda: servico.criar_bloco(db, evento, user, dados.nome, dados.capacidade, dados.descricao),
    )
    return _bloco_atual(db, evento, bloco)


@router.post("/distribuir/previa", response_model=PreviaDistribuicaoOut, dependencies=requer(Permissao.CONFIGURAR_BLOCOS))
def previa_distribuicao(
    dados: DistribuirIn, evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> PreviaDistribuicaoOut:
    """Simula a distribuicao automatica. Nada e gravado."""
    try:
        return PreviaDistribuicaoOut(**servico.previa_distribuicao(db, evento, dados.capacidade))
    except RegraDeNegocio as exc:
        raise HTTPException(exc.status_code, exc.mensagem) from exc


@router.post("/remanescentes/previa", response_model=PreviaDistribuicaoOut, dependencies=requer(Permissao.CONFIGURAR_BLOCOS))
def previa_remanescentes(
    dados: RemanescentesIn, evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> PreviaDistribuicaoOut:
    """Simula a criacao dos blocos de remanescentes. Nada e gravado."""
    try:
        return PreviaDistribuicaoOut(
            **servico.previa_remanescentes(db, evento, dados.nome, dados.capacidade)
        )
    except RegraDeNegocio as exc:
        raise HTTPException(exc.status_code, exc.mensagem) from exc


@router.post("/reordenar", response_model=BlocosOut)
def reordenar(
    dados: ReordenarBlocosIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> BlocosOut:
    _executar(db, lambda: servico.reordenar_blocos(db, evento, dados.blocos, user))
    return _listar(db, evento)


@router.post("/distribuir", response_model=BlocosOut)
def distribuir(
    dados: DistribuirIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> BlocosOut:
    _executar(
        db,
        lambda: servico.distribuir_automaticamente(db, evento, dados.capacidade, user, dados.misturar),
    )
    return _listar(db, evento)


@router.post(
    "/distribuir-nos-blocos/previa",
    response_model=PreviaNosBlocosOut,
    dependencies=requer(Permissao.CONFIGURAR_BLOCOS),
)
def previa_nos_blocos(evento: Event = Depends(evento_atual), db: Session = Depends(get_db)) -> PreviaNosBlocosOut:
    """Simula o preenchimento dos blocos planejados ja criados. Nada e gravado."""
    try:
        return PreviaNosBlocosOut(**servico.previa_nos_blocos(db, evento))
    except RegraDeNegocio as exc:
        raise HTTPException(exc.status_code, exc.mensagem) from exc


@router.post("/distribuir-nos-blocos", response_model=BlocosOut)
def distribuir_nos_blocos(
    dados: DistribuirNosBlocosIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> BlocosOut:
    _executar(db, lambda: servico.distribuir_nos_blocos(db, evento, user, dados.misturar))
    return _listar(db, evento)


@router.get("/distribuicao", response_model=DistribuicaoOut, dependencies=VER)
def ver_distribuicao(
    evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> DistribuicaoOut:
    return _distribuicao(db, evento)


@router.put("/distribuicao", response_model=DistribuicaoOut)
def salvar_distribuicao(
    dados: DistribuicaoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> DistribuicaoOut:
    itens = [item.model_dump() for item in dados.blocos]
    _executar(db, lambda: servico.salvar_distribuicao(db, evento, itens, user, dados.versao))
    return _distribuicao(db, evento)


@router.post("/remanescentes", response_model=BlocoOut, status_code=status.HTTP_201_CREATED)
def criar_remanescentes(
    dados: RemanescentesIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> BlocoOut:
    """Cria os blocos de remanescentes (respeitando a capacidade). Devolve o primeiro."""
    criados = _executar(
        db,
        lambda: servico.criar_bloco_remanescentes(
            db, evento, user, dados.nome, dados.capacidade, dados.misturar
        ),
    )
    return _bloco_atual(db, evento, criados[0])


# ------------------------------------------------------------------ um bloco
@router.get("/{bloco_id}", response_model=BlocoDetalheOut, dependencies=VER)
def detalhe(
    bloco_id: int, evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> BlocoDetalheOut:
    bloco = _buscar(db, evento, bloco_id)
    vencedores = _vencedores(db, evento)
    resultados = db.scalars(
        select(Draw).where(Draw.bloco_id == bloco.id).order_by(Draw.rodada, Draw.id)
    ).all()
    return BlocoDetalheOut(
        bloco=_bloco_atual(db, evento, bloco),
        unidades=[
            _unidade_out(u, p, vencedores) for u, p in servico.unidades_ordenadas_do_bloco(db, bloco)
        ],
        resultados=[SorteioOut(**serializar_sorteio(db, r)) for r in resultados],
    )


@router.patch("/{bloco_id}", response_model=BlocoOut)
def editar(
    bloco_id: int,
    dados: BlocoUpdate,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> BlocoOut:
    bloco = _buscar(db, evento, bloco_id)
    _executar(
        db,
        lambda: servico.editar_bloco(
            db, evento, bloco, user, dados.nome, dados.capacidade, dados.descricao
        ),
    )
    return _bloco_atual(db, evento, bloco)


@router.delete("/{bloco_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(
    bloco_id: int,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(EXCLUIR),
) -> Response:
    bloco = _buscar(db, evento, bloco_id)
    ds = db.get(DisplayState, evento.id)
    apresentando = ds is not None and ds.carrossel_bloco_id == bloco.id
    _executar(db, lambda: servico.remover_bloco(db, evento, bloco, user))
    if apresentando:
        # O telao saiu da apresentacao dos ganhadores deste bloco.
        publicar_estado(db, evento, ds)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{bloco_id}/iniciar", response_model=BlocoOut)
def iniciar(
    bloco_id: int,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONDUZIR),
) -> BlocoOut:
    """Inicia ou retoma. Chamar de novo com o bloco em andamento nao faz nada."""
    bloco = _buscar(db, evento, bloco_id)
    _executar(db, lambda: servico.iniciar_bloco(db, evento, bloco, user))
    return _bloco_atual(db, evento, bloco)


@router.post("/{bloco_id}/pausar", response_model=BlocoOut)
def pausar(
    bloco_id: int,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONDUZIR),
) -> BlocoOut:
    bloco = _buscar(db, evento, bloco_id)
    _executar(db, lambda: servico.pausar_bloco(db, evento, bloco, user))
    return _bloco_atual(db, evento, bloco)


@router.post("/{bloco_id}/finalizar", response_model=BlocoOut)
def finalizar(
    bloco_id: int,
    dados: FinalizarBlocoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONDUZIR),
) -> BlocoOut:
    bloco = _buscar(db, evento, bloco_id)
    ja_finalizado = bloco.status == StatusBloco.FINALIZADO.value
    _executar(
        db,
        lambda: servico.finalizar_bloco(db, evento, bloco, user, dados.confirmar_pendentes),
    )
    # Ao finalizar, o telao apresenta os ganhadores do bloco automaticamente
    # (se houver algum). O proximo bloco NAO e iniciado. Se a apresentacao deste
    # bloco ja esta no telao (comecou sozinha apos o ultimo sorteio), nao
    # recomeca; se so estava agendada, comeca agora (ou apos a revelacao em curso).
    ds_atual = db.get(DisplayState, evento.id)
    ja_apresentando = (
        ds_atual is not None
        and ds_atual.estado == EstadoTelao.CARROSSEL_GANHADORES.value
        and ds_atual.carrossel_bloco_id == bloco.id
    )
    if not ja_finalizado and not ja_apresentando and carrossel.slides(db, bloco):
        try:
            ds = carrossel.iniciar(db, evento, bloco, user, automatico=True)
            publicar_estado(db, evento, ds)
        except RegraDeNegocio:
            db.rollback()
    return _bloco_atual(db, evento, bloco)


@router.post("/{bloco_id}/reabrir", response_model=BlocoOut)
def reabrir(
    bloco_id: int,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONDUZIR),
) -> BlocoOut:
    """Bloco finalizado com premios sem sorteio volta a pausado (Continuar)."""
    bloco = _buscar(db, evento, bloco_id)
    _executar(db, lambda: servico.reabrir_bloco(db, evento, bloco, user))
    return _bloco_atual(db, evento, bloco)


# "premiados" e nao "ganhadores": o teste original garante que nenhuma rota
# tenha "ganhador" no caminho, para nao existir forma de editar o vencedor.
# Esta rota e somente leitura.
@router.get("/{bloco_id}/premiados", response_model=list[GanhadorBlocoOut], dependencies=VER)
def premiados(
    bloco_id: int, evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> list[GanhadorBlocoOut]:
    bloco = _buscar(db, evento, bloco_id)
    return [GanhadorBlocoOut(**g) for g in servico.ganhadores_do_bloco(db, bloco)]
