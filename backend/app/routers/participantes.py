from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import evento_atual, exigir_alguma_permissao, exigir_permissao, requer
from ..migracoes import fazer_backup
from ..permissoes import Permissao
from ..models import AuditLog, Draw, Event, Notificacao, Participant, User
from ..schemas import (
    FRASE_ZERAR_PARTICIPANTES,
    ConfirmarImportacaoIn,
    ParticipacaoIn,
    ParticipanteIn,
    ParticipanteMantidoOut,
    ParticipanteOut,
    ParticipanteUpdate,
    PresencaIn,
    PreviaImportacao,
    ZerarParticipantesIn,
    ZerarParticipantesOut,
)
from ..services.elegibilidade import ids_ja_ganharam
from ..texto import normalizar_matricula
from ..services.importacao import (
    ler_planilha,
    modelo_csv,
    modelo_xlsx,
    validar_linhas,
)

router = APIRouter(prefix="/api/events/{event_id}/participantes", tags=["participantes"])
modelos = APIRouter(prefix="/api/participantes", tags=["participantes"])

GERENCIAR = exigir_permissao(Permissao.GERENCIAR_PARTICIPANTES)
# Presenca tambem e marcada pela equipe de credenciamento (check-in).
MARCAR_PRESENCA = exigir_alguma_permissao(
    Permissao.GERENCIAR_PARTICIPANTES, Permissao.AUXILIAR_CREDENCIAMENTO
)


def _saida(p: Participant, ganhadores: set[int]) -> ParticipanteOut:
    dados = ParticipanteOut.model_validate(p)
    dados.ja_ganhou = p.id in ganhadores
    dados.tem_conta = p.usuario_id is not None
    return dados


def _exigir_pulseira_livre(
    db: Session, evento: Event, pulseira: str | None, ignorar_id: int | None = None
) -> None:
    if pulseira is None:
        return
    dono = db.scalar(
        select(Participant).where(
            Participant.event_id == evento.id, Participant.pulseira == pulseira
        )
    )
    if dono is not None and dono.id != ignorar_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A pulseira {pulseira} já está atribuída a outro participante neste evento",
        )


def _mensagem_de_conflito(exc: IntegrityError) -> str:
    """Traduz a violacao de unicidade do banco (backstop da checagem previa)."""
    texto = str(exc.orig).lower()
    if "pulseira" in texto:
        return "Pulseira já atribuída a outro participante neste evento"
    return "Matricula duplicada neste evento"


def _buscar(db: Session, evento: Event, participant_id: int) -> Participant:
    p = db.get(Participant, participant_id)
    if p is None or p.event_id != evento.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Participante não encontrado")
    return p


@router.get(
    "", response_model=list[ParticipanteOut], dependencies=requer(Permissao.GERENCIAR_PARTICIPANTES)
)
def listar(
    busca: str = Query("", max_length=120),
    setor: str = Query("", max_length=160),
    presenca: str = Query("todos", pattern="^(todos|presentes|ausentes)$"),
    participacao: str = Query("todos", pattern="^(todos|ativos|excluidos)$"),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> list[ParticipanteOut]:
    condicoes = [Participant.event_id == evento.id]
    termo = busca.strip()
    if termo:
        padrao = f"%{termo.lower()}%"
        condicoes.append(
            (Participant.nome.ilike(padrao))
            | (Participant.matricula.ilike(padrao))
            # "26" encontra "00026".
            | (Participant.matricula_normalizada == normalizar_matricula(termo))
        )
    if setor.strip():
        condicoes.append(Participant.setor == setor.strip())
    if presenca == "presentes":
        condicoes.append(Participant.presente.is_(True))
    elif presenca == "ausentes":
        condicoes.append(Participant.presente.is_(False))
    if participacao == "ativos":
        condicoes.append(Participant.participando.is_(True))
    elif participacao == "excluidos":
        condicoes.append(Participant.participando.is_(False))

    linhas = db.scalars(
        select(Participant).where(*condicoes).order_by(Participant.nome)
    ).all()
    ganhadores = ids_ja_ganharam(db, evento)
    return [_saida(p, ganhadores) for p in linhas]


@router.get(
    "/setores", response_model=list[str], dependencies=requer(Permissao.GERENCIAR_PARTICIPANTES)
)
def setores(evento: Event = Depends(evento_atual), db: Session = Depends(get_db)) -> list[str]:
    linhas = db.scalars(
        select(Participant.setor)
        .where(Participant.event_id == evento.id, Participant.setor != "")
        .distinct()
        .order_by(Participant.setor)
    ).all()
    return list(linhas)


@router.post("", response_model=ParticipanteOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: ParticipanteIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> ParticipanteOut:
    # "026" e "26" sao a mesma matricula.
    existente = db.scalar(
        select(Participant).where(
            Participant.event_id == evento.id,
            (Participant.matricula == dados.matricula)
            | (Participant.matricula_normalizada == normalizar_matricula(dados.matricula)),
        ).limit(1)
    )
    if existente is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Já existe um participante com a matrícula {existente.matricula} neste evento",
        )
    _exigir_pulseira_livre(db, evento, dados.pulseira)
    p = Participant(event_id=evento.id, **dados.model_dump())
    db.add(p)
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="participante_criado",
            detalhes={"matricula": dados.matricula, "pulseira": dados.pulseira},
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _mensagem_de_conflito(exc)) from exc
    db.refresh(p)
    return _saida(p, ids_ja_ganharam(db, evento))


@router.patch("/{participant_id}", response_model=ParticipanteOut)
def atualizar(
    participant_id: int,
    dados: ParticipanteUpdate,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> ParticipanteOut:
    p = _buscar(db, evento, participant_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    nova_matricula = (alteracoes.get("matricula") or "").strip()
    if nova_matricula and normalizar_matricula(nova_matricula) != p.matricula_normalizada:
        outro = db.scalar(
            select(Participant.matricula).where(
                Participant.event_id == evento.id,
                Participant.id != p.id,
                Participant.matricula_normalizada == normalizar_matricula(nova_matricula),
            ).limit(1)
        )
        if outro is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Já existe um participante com a matrícula {outro} neste evento",
            )
    pulseira_anterior = p.pulseira
    if "pulseira" in alteracoes and alteracoes["pulseira"] != pulseira_anterior:
        _exigir_pulseira_livre(db, evento, alteracoes["pulseira"], ignorar_id=p.id)
        # Troca de pulseira e procedimento controlado: fica na auditoria.
        db.add(
            AuditLog(
                event_id=evento.id,
                usuario_id=user.id,
                acao="pulseira_alterada",
                detalhes={
                    "participante_id": p.id,
                    "anterior": pulseira_anterior,
                    "nova": alteracoes["pulseira"],
                },
            )
        )
    for campo, valor in alteracoes.items():
        setattr(p, campo, valor.strip() if isinstance(valor, str) else valor)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _mensagem_de_conflito(exc)) from exc
    db.refresh(p)
    return _saida(p, ids_ja_ganharam(db, evento))


@router.post("/{participant_id}/presenca", response_model=ParticipanteOut)
def confirmar_presenca(
    participant_id: int,
    dados: PresencaIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(MARCAR_PRESENCA),
) -> ParticipanteOut:
    p = _buscar(db, evento, participant_id)
    p.presente = dados.presente
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="presenca_alterada",
            detalhes={"participante_id": p.id, "presente": dados.presente},
        )
    )
    db.commit()
    db.refresh(p)
    return _saida(p, ids_ja_ganharam(db, evento))


@router.post("/{participant_id}/participacao", response_model=ParticipanteOut)
def alterar_participacao(
    participant_id: int,
    dados: ParticipacaoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> ParticipanteOut:
    """Inclui ou exclui a participacao. O motivo e obrigatorio e fica no historico."""
    p = _buscar(db, evento, participant_id)
    p.participando = dados.participando
    p.motivo_participacao = dados.motivo.strip()
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="participacao_alterada",
            detalhes={
                "participante_id": p.id,
                "participando": dados.participando,
                "motivo": dados.motivo.strip(),
            },
        )
    )
    db.commit()
    db.refresh(p)
    return _saida(p, ids_ja_ganharam(db, evento))


@router.post("/presenca-em-lote", response_model=int)
def presenca_em_lote(
    ids: list[int],
    presente: bool = Query(...),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> int:
    linhas = db.scalars(
        select(Participant).where(
            Participant.event_id == evento.id, Participant.id.in_(ids or [0])
        )
    ).all()
    for p in linhas:
        p.presente = presente
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="presenca_em_lote",
            detalhes={"quantidade": len(linhas), "presente": presente},
        )
    )
    db.commit()
    return len(linhas)


@router.delete("/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(
    participant_id: int,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> Response:
    """Remove definitivamente. Bloqueado se o participante ja tem resultado registrado."""
    from ..models import Draw

    p = _buscar(db, evento, participant_id)
    tem_sorteio = db.scalar(select(Draw.id).where(Draw.participant_id == p.id).limit(1))
    if tem_sorteio is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Participante possui resultado no histórico. Use 'excluir da participação' em vez de apagar.",
        )
    db.delete(p)
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="participante_removido",
            detalhes={"matricula": p.matricula},
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/zerar", response_model=ZerarParticipantesOut)
def zerar_participantes(
    dados: ZerarParticipantesIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> ZerarParticipantesOut:
    """Apaga a lista do evento para reimportar a planilha.

    Mantem quem tem resultado no historico (auditoria; a FK do sorteio e
    RESTRICT) e quem ja fez o autocadastro (conta e foto). Faz um backup do
    banco antes de apagar.
    """
    if dados.confirmacao.strip().upper() != FRASE_ZERAR_PARTICIPANTES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Digite {FRASE_ZERAR_PARTICIPANTES} para confirmar",
        )

    todos = db.scalars(
        select(Participant).where(Participant.event_id == evento.id).order_by(Participant.id)
    ).all()
    com_sorteio = set(
        db.scalars(
            select(Draw.participant_id).where(Draw.event_id == evento.id).distinct()
        ).all()
    )
    mantidos: list[ParticipanteMantidoOut] = []
    remover: list[int] = []
    for p in todos:
        if p.id in com_sorteio:
            motivo = "tem resultado no histórico"
        elif p.usuario_id is not None:
            motivo = "já fez o autocadastro"
        else:
            remover.append(p.id)
            continue
        mantidos.append(ParticipanteMantidoOut(nome=p.nome, matricula=p.matricula, motivo=motivo))

    backup = None
    if remover:
        caminho = fazer_backup(settings.database_url, f"evento{evento.id}", "antes-de-zerar-participantes")
        backup = caminho.name if caminho else None
        for inicio in range(0, len(remover), 500):
            lote = remover[inicio : inicio + 500]
            db.execute(delete(Notificacao).where(Notificacao.participant_id.in_(lote)))
            db.execute(delete(Participant).where(Participant.id.in_(lote)))

    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="participantes_zerados",
            detalhes={
                "removidos": len(remover),
                "mantidos": [m.matricula for m in mantidos],
                "backup": backup,
            },
        )
    )
    db.commit()
    return ZerarParticipantesOut(removidos=len(remover), mantidos=mantidos, backup=backup)


# ------------------------------------------------------------------ importacao
# Sincrono de proposito: ler a planilha e consultar o banco sao operacoes
# bloqueantes e devem rodar no threadpool, nao no event loop.
@router.post(
    "/importar/previa",
    response_model=PreviaImportacao,
    dependencies=requer(Permissao.GERENCIAR_PARTICIPANTES),
)
def previa_importacao(
    arquivo: UploadFile = File(...),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> PreviaImportacao:
    conteudo = arquivo.file.read()
    if len(conteudo) > settings.max_planilha_bytes:
        limite = settings.max_planilha_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Planilha maior que {limite} MB"
        )
    try:
        brutas = ler_planilha(conteudo, arquivo.filename or "")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    registros = db.execute(
        select(Participant.matricula_normalizada, Participant.cpf_hash).where(
            Participant.event_id == evento.id
        )
    ).all()
    existentes = {normalizada for normalizada, _cpf in registros}
    cpfs = {cpf: normalizada for normalizada, cpf in registros if cpf}
    linhas = validar_linhas(brutas, existentes, cpfs)
    com_erro = sum(1 for linha in linhas if linha["erros"])
    duplicadas = sum(
        1 for linha in linhas if linha["duplicada_na_planilha"] or linha["ja_existe_no_evento"]
    )
    return PreviaImportacao(
        total_linhas=len(linhas),
        validas=len(linhas) - com_erro,
        com_erro=com_erro,
        duplicadas=duplicadas,
        com_identificacao=sum(1 for linha in linhas if linha["tem_identificacao"] and not linha["erros"]),
        linhas=linhas,
    )


@router.post("/importar/confirmar")
def confirmar_importacao(
    dados: ConfirmarImportacaoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> dict:
    # Chave: matricula normalizada ("026" e "26" sao a mesma pessoa).
    existentes = {
        p.matricula_normalizada: p
        for p in db.scalars(
            select(Participant).where(Participant.event_id == evento.id)
        ).all()
    }
    criados = atualizados = identificacoes = ignorados = 0
    vistas: set[str] = set()

    for linha in dados.linhas:
        normalizada = normalizar_matricula(linha.matricula)
        if not linha.nome or not linha.matricula or normalizada in vistas:
            ignorados += 1
            continue
        vistas.add(normalizada)
        # Codigos so valem juntos (identificacao exige o CPF para nao duplicar).
        tem_codigos = bool(linha.codigo_identificacao and linha.codigo_cpf)
        atual = existentes.get(normalizada)
        if atual is not None:
            mudou = False
            if dados.atualizar_existentes:
                atual.nome = linha.nome
                atual.setor = linha.setor
                atualizados += 1
                mudou = True
            if dados.atualizar_identificacao and tem_codigos:
                atual.identificacao_hash = linha.codigo_identificacao
                atual.cpf_hash = linha.codigo_cpf
                identificacoes += 1
                mudou = True
            if not mudou:
                ignorados += 1
            continue
        db.add(
            Participant(
                event_id=evento.id,
                nome=linha.nome,
                matricula=linha.matricula,
                setor=linha.setor,
                presente=linha.presente,
                identificacao_hash=linha.codigo_identificacao if tem_codigos else None,
                cpf_hash=linha.codigo_cpf if tem_codigos else None,
            )
        )
        criados += 1

    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="participantes_importados",
            # Sem CPF, nascimento ou codigos: so as contagens.
            detalhes={
                "criados": criados,
                "atualizados": atualizados,
                "identificacoes_atualizadas": identificacoes,
                "ignorados": ignorados,
            },
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        mensagem = (
            "CPF repetido: o mesmo CPF já pertence a outra matrícula neste evento"
            if "cpf" in str(exc.orig).lower()
            else "Conflito de matrículas durante a importação"
        )
        raise HTTPException(status.HTTP_409_CONFLICT, mensagem) from exc
    return {
        "criados": criados,
        "atualizados": atualizados,
        "identificacoes_atualizadas": identificacoes,
        "ignorados": ignorados,
    }


# ------------------------------------------------------------------ modelos
@modelos.get("/modelo.csv")
def baixar_modelo_csv(_: User = Depends(GERENCIAR)) -> Response:
    return Response(
        content=modelo_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo-participantes.csv"'},
    )


@modelos.get("/modelo.xlsx")
def baixar_modelo_xlsx(_: User = Depends(GERENCIAR)) -> Response:
    return Response(
        content=modelo_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo-participantes.xlsx"'},
    )
