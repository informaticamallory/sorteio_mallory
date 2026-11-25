from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer
from ..permissoes import Permissao, tem_permissao
from ..models import (
    AuditLog,
    DisplayState,
    Draw,
    EstadoTelao,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    StatusSorteio,
    StatusUnidade,
    User,
    utcnow,
)
from ..services.blocos import em_revelacao
from ..services.telao import publicar_estado
from ..config import settings
from ..schemas import (
    ImportarPremiosIn,
    ImportarPremiosOut,
    PremioIn,
    PremioOut,
    PremioUpdate,
    PreviaImportPremios,
    ReordenarIn,
    UnidadeOut,
)
from ..services import importacao_premios
from ..texto import normalizar_busca

router = APIRouter(prefix="/api/events/{event_id}/premios", tags=["premios"])
# Modelos da planilha de importacao (nao dependem de evento).
modelos = APIRouter(prefix="/api/premios", tags=["premios"])

CADASTRAR = exigir_permissao(Permissao.CADASTRAR_PREMIOS)
# O operador le os premios (a tela de sorteio lista as unidades), mas nao altera.
LER = requer(Permissao.CADASTRAR_PREMIOS, Permissao.CONTROLAR_SORTEIO, alguma=True)


def _buscar(db: Session, evento: Event, prize_id: int) -> Prize:
    premio = db.get(Prize, prize_id)
    # Premio excluido pelo admin so existe para o historico.
    if premio is None or premio.event_id != evento.id or premio.excluido_em is not None:
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
        select(Prize)
        .where(Prize.event_id == evento.id, Prize.excluido_em.is_(None))
        .order_by(Prize.ordem, Prize.id)
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
        for premio in db.scalars(
            select(Prize).where(Prize.event_id == evento.id, Prize.excluido_em.is_(None))
        ).all()
    }
    for posicao, prize_id in enumerate(dados.ordem, start=1):
        premio = premios.get(prize_id)
        if premio is not None:
            premio.ordem = posicao
    db.commit()
    return listar(evento=evento, db=db)


# ------------------------------------------------------------------ importacao
def _nomes_existentes(db: Session, evento: Event) -> set[str]:
    return {
        normalizar_busca(nome)
        for nome in db.scalars(
            select(Prize.nome).where(Prize.event_id == evento.id, Prize.excluido_em.is_(None))
        ).all()
    }


@router.post(
    "/importar/previa",
    response_model=PreviaImportPremios,
    dependencies=requer(Permissao.CADASTRAR_PREMIOS),
)
def previa_importacao(
    arquivo: UploadFile = File(...),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> PreviaImportPremios:
    """Le a planilha e mostra o que sera importado. Nao grava nada."""
    conteudo = arquivo.file.read()
    if len(conteudo) > settings.max_planilha_bytes:
        limite = settings.max_planilha_bytes // (1024 * 1024)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Planilha maior que {limite} MB")
    try:
        linhas = importacao_premios.previa(conteudo, arquivo.filename or "", _nomes_existentes(db, evento))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return PreviaImportPremios(linhas=linhas)


@router.post("/importar/confirmar", response_model=ImportarPremiosOut)
def confirmar_importacao(
    dados: ImportarPremiosIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CADASTRAR),
) -> ImportarPremiosOut:
    """Cria os premios da planilha, no fim da lista. Quem ja existe fica de fora."""
    existentes = _nomes_existentes(db, evento)
    ordem = (
        db.scalar(select(Prize.ordem).where(Prize.event_id == evento.id).order_by(Prize.ordem.desc()).limit(1))
        or 0
    )
    criados: list[str] = []
    ignorados = 0
    for item in dados.linhas:
        nome = item.nome.strip()
        chave = normalizar_busca(nome)
        if not nome or chave in existentes:
            ignorados += 1
            continue
        existentes.add(chave)
        ordem += 1
        premio = Prize(
            event_id=evento.id,
            nome=nome,
            descricao=(item.descricao or "").strip() or None,
            quantidade=item.quantidade,
            ordem=ordem,
        )
        db.add(premio)
        db.flush()
        for numero in range(1, item.quantidade + 1):
            db.add(PrizeUnit(prize_id=premio.id, numero=numero))
        criados.append(nome)
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="premios_importados",
            detalhes={"criados": len(criados), "ignorados": ignorados, "premios": criados[:200]},
        )
    )
    db.commit()
    return ImportarPremiosOut(criados=len(criados), ignorados=ignorados)


@modelos.get("/modelo.csv")
def baixar_modelo_csv(_: User = Depends(CADASTRAR)) -> Response:
    return Response(
        content=importacao_premios.modelo_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo-premios.csv"'},
    )


@modelos.get("/modelo.xlsx")
def baixar_modelo_xlsx(_: User = Depends(CADASTRAR)) -> Response:
    return Response(
        content=importacao_premios.modelo_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo-premios.xlsx"'},
    )


@router.delete("/{prize_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(
    prize_id: int,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CADASTRAR),
) -> Response:
    premio = _buscar(db, evento, prize_id)
    sorteios = db.scalars(
        select(Draw).where(Draw.prize_unit_id.in_([u.id for u in premio.unidades] or [0]))
    ).all()
    if sorteios:
        # Apagar de verdade levaria junto os sorteios (cascata): o premio so
        # sai da tela de Premios e os resultados ficam no historico.
        if not tem_permissao(user, Permissao.EXCLUIR_PREMIOS):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Este prêmio já teve sorteio. Só o administrador pode excluí-lo.",
            )
        if em_revelacao(db, evento):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Aguarde o telão terminar de revelar o resultado antes de excluir o prêmio.",
            )
        ds = _excluir_com_resultados(db, evento, premio, sorteios, user)
        if ds is not None:
            publicar_estado(db, evento, ds)  # grava tudo e avisa o telao
        else:
            db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
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


def _excluir_com_resultados(
    db: Session, evento: Event, premio: Prize, sorteios: list[Draw], user: User
) -> DisplayState | None:
    """Exclusao logica: nada do historico e apagado.

    * Unidades sorteadas/entregues: o resultado valido continua (historico,
      Central de Entregas, relatorio), com o nome do premio.
    * Disponiveis que ja tiveram sorteio (anulado): ficam como REMOVIDO, fora
      dos blocos e nunca mais sorteadas.
    * Disponiveis sem sorteio nenhum: apagadas.

    Devolve o estado do telao quando ele estava mostrando uma unidade que saiu
    (o chamador grava e publica); senao None.
    """
    com_sorteio = {s.prize_unit_id for s in sorteios}
    validos = sum(1 for s in sorteios if s.status == StatusSorteio.VALIDO.value)
    ds = db.get(DisplayState, evento.id)
    telao_mudou = False
    apagadas = removidas = 0
    for unidade in list(premio.unidades):
        if unidade.status != StatusUnidade.DISPONIVEL.value:
            continue
        if ds is not None and ds.prize_unit_id == unidade.id and ds.estado == EstadoTelao.PREMIO.value:
            ds.estado = EstadoTelao.AGUARDANDO.value
            ds.prize_unit_id = None
            ds.draw_id = None
            ds.nomes_animacao = []
            ds.revelar_em = None
            ds.versao += 1
            telao_mudou = True
        if unidade.id in com_sorteio:
            unidade.status = StatusUnidade.REMOVIDO.value
            unidade.bloco_id = None
            unidade.ordem_bloco = None
            removidas += 1
        else:
            premio.unidades.remove(unidade)  # delete-orphan apaga a unidade
            apagadas += 1
    premio.excluido_em = utcnow()
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="premio_removido",
            detalhes={
                "premio_id": premio.id,
                "premio": premio.nome,
                "com_resultados": True,
                "resultados_validos": validos,
                "sorteios_no_historico": len(sorteios),
                "unidades_apagadas": apagadas,
                "unidades_retiradas": removidas,
            },
        )
    )
    db.flush()
    return ds if telao_mudou else None
