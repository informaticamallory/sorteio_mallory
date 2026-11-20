from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer
from ..permissoes import Permissao
from ..models import (
    AuditLog,
    Draw,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    StatusSorteio,
    StatusUnidade,
    User,
)
from ..schemas import PremioIn, PremioOut, PremioUpdate, ReordenarIn, UnidadeOut

router = APIRouter(prefix="/api/events/{event_id}/premios", tags=["premios"])

CADASTRAR = exigir_permissao(Permissao.CADASTRAR_PREMIOS)
# O operador le os premios (a tela de sorteio lista as unidades), mas nao altera.
LER = requer(Permissao.CADASTRAR_PREMIOS, Permissao.CONTROLAR_SORTEIO, alguma=True)


def _buscar(db: Session, evento: Event, prize_id: int) -> Prize:
    premio = db.get(Prize, prize_id)
    if premio is None or premio.event_id != evento.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prêmio não encontrado")
    return premio


def _saida(db: Session, premio: Prize) -> PremioOut:
    vencedores = {
        sorteio.prize_unit_id: sorteio
        for sorteio in db.scalars(
            select(Draw).where(
                Draw.prize_unit_id.in_([u.id for u in premio.unidades] or [0]),
                Draw.status == StatusSorteio.VALIDO.value,
            )
        ).all()
    }
    unidades = []
    for unidade in premio.unidades:
        sorteio = vencedores.get(unidade.id)
        ganhador = db.get(Participant, sorteio.participant_id) if sorteio else None
        unidades.append(
            UnidadeOut(
                id=unidade.id,
                numero=unidade.numero,
                status=unidade.status,
                ganhador_nome=ganhador.nome if ganhador else None,
                ganhador_setor=ganhador.setor if ganhador else None,
                draw_id=sorteio.id if sorteio else None,
                bloco_id=unidade.bloco_id,
                ordem_bloco=unidade.ordem_bloco,
            )
        )
    saida = PremioOut.model_validate(premio)
    saida.unidades = unidades
    saida.disponiveis = sum(1 for u in unidades if u.status == StatusUnidade.DISPONIVEL.value)
    return saida


def _sincronizar_unidades(db: Session, premio: Prize, quantidade: int) -> None:
    atuais = sorted(premio.unidades, key=lambda u: u.numero)
    if quantidade > len(atuais):
        proximo = (atuais[-1].numero if atuais else 0) + 1
        for numero in range(proximo, proximo + (quantidade - len(atuais))):
            db.add(PrizeUnit(prize_id=premio.id, numero=numero))
    elif quantidade < len(atuais):
        remover = len(atuais) - quantidade
        candidatas = [u for u in reversed(atuais) if u.status == StatusUnidade.DISPONIVEL.value]
        if len(candidatas) < remover:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Não é possível reduzir a quantidade: há unidades já sorteadas ou entregues.",
            )
        for unidade in candidatas[:remover]:
            db.delete(unidade)


@router.get("", response_model=list[PremioOut], dependencies=LER)
def listar(evento: Event = Depends(evento_atual), db: Session = Depends(get_db)) -> list[PremioOut]:
    premios = db.scalars(
        select(Prize).where(Prize.event_id == evento.id).order_by(Prize.ordem, Prize.id)
    ).all()
    return [_saida(db, premio) for premio in premios]


@router.post("", response_model=PremioOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: PremioIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CADASTRAR),
) -> PremioOut:
    ultima_ordem = (
        db.scalar(
            select(Prize.ordem).where(Prize.event_id == evento.id).order_by(Prize.ordem.desc()).limit(1)
        )
        or 0
    )
    premio = Prize(
        event_id=evento.id,
        nome=dados.nome.strip(),
        descricao=(dados.descricao or "").strip() or None,
        imagem_url=dados.imagem_url,
        quantidade=dados.quantidade,
        ordem=dados.ordem or ultima_ordem + 1,
    )
    db.add(premio)
    db.flush()
    for numero in range(1, dados.quantidade + 1):
        db.add(PrizeUnit(prize_id=premio.id, numero=numero))
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="premio_criado",
            detalhes={"premio": premio.nome, "quantidade": premio.quantidade},
        )
    )
    db.commit()
    db.refresh(premio)
    return _saida(db, premio)


@router.patch(
    "/{prize_id}", response_model=PremioOut, dependencies=requer(Permissao.CADASTRAR_PREMIOS)
)
def atualizar(
    prize_id: int,
    dados: PremioUpdate,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> PremioOut:
    premio = _buscar(db, evento, prize_id)
    alterado = dados.model_dump(exclude_unset=True)
    if "quantidade" in alterado and alterado["quantidade"] is not None:
        _sincronizar_unidades(db, premio, alterado["quantidade"])
    for campo, valor in alterado.items():
        setattr(premio, campo, valor.strip() if isinstance(valor, str) else valor)
    db.commit()
    db.refresh(premio)
    return _saida(db, premio)


@router.post(
    "/reordenar", response_model=list[PremioOut], dependencies=requer(Permissao.CADASTRAR_PREMIOS)
)
def reordenar(
    dados: ReordenarIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> list[PremioOut]:
    premios = {
        premio.id: premio
        for premio in db.scalars(select(Prize).where(Prize.event_id == evento.id)).all()
    }
    for posicao, prize_id in enumerate(dados.ordem, start=1):
        premio = premios.get(prize_id)
        if premio is not None:
            premio.ordem = posicao
    db.commit()
    return listar(evento=evento, db=db)


@router.delete("/{prize_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(
    prize_id: int,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CADASTRAR),
) -> Response:
    premio = _buscar(db, evento, prize_id)
    tem_sorteio = db.scalar(
        select(Draw.id)
        .where(Draw.prize_unit_id.in_([u.id for u in premio.unidades] or [0]))
        .limit(1)
    )
    if tem_sorteio is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este prêmio já possui resultados registrados e não pode ser excluído.",
        )
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="premio_removido",
            detalhes={"premio": premio.nome},
        )
    )
    db.delete(premio)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
