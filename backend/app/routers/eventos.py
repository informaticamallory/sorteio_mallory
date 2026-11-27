from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import evento_atual, exigir_permissao, requer, usuario_interno, ve_evento_de_teste
from ..permissoes import Permissao, tem_permissao
from ..models import (
    AuditLog,
    DisplayState,
    Draw,
    Event,
    ModoSorteio,
    Notificacao,
    Participant,
    Prize,
    PrizeUnit,
    RuleChange,
    StatusSorteio,
    StatusUnidade,
    User,
    utcnow,
)
from ..schemas import (
    EventoConfigIn,
    EventoIn,
    EventoOut,
    ExcluirEventoIn,
    FaixaMatriculaOut,
    MudancaRegraOut,
    RegrasIn,
    RegrasOut,
    ResumoOut,
)
from ..security import novo_token_telao
from ..services.elegibilidade import participantes_elegiveis, resumo_regras
from ..services import ambiente_teste, fotos_entrega
from ..services.erros import RegraDeNegocio
from ..services.telao import notificar_atualizacao

router = APIRouter(prefix="/api/events", tags=["eventos"])

GERENCIAR = exigir_permissao(Permissao.GERENCIAR_EVENTOS)  # criar eventos (admin)
CONFIGURAR = exigir_permissao(Permissao.CONFIGURAR_EVENTO)  # configurar o evento (admin e RH)
DEFINIR_REGRAS = exigir_permissao(Permissao.DEFINIR_REGRAS)
VISUALIZAR = requer(Permissao.VISUALIZAR_EVENTO)
# Previa da faixa de matriculas: so quem define as regras (admin e RH).
PREVIA_REGRAS = requer(Permissao.DEFINIR_REGRAS)

COR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
CAMPOS_COR_CLARO = ("claro_cor_fundo", "claro_cor_painel", "claro_cor_destaque", "claro_cor_texto")
CAMPOS_COR = ("cor_fundo", "cor_primaria", "cor_texto", "cor_destaque", *CAMPOS_COR_CLARO)


@router.get("", response_model=list[EventoOut], dependencies=VISUALIZAR)
def listar(db: Session = Depends(get_db), user: User = Depends(usuario_interno)) -> list[Event]:
    consulta = select(Event).order_by(Event.criado_em.desc())
    if not ve_evento_de_teste(user):
        # Evento de teste (e o ambiente de teste) so aparece para o admin.
        consulta = consulta.where(Event.evento_teste.is_(False))
    return list(db.scalars(consulta).all())


@router.post("", response_model=EventoOut, status_code=status.HTTP_201_CREATED)
def criar(dados: EventoIn, db: Session = Depends(get_db), user: User = Depends(GERENCIAR)) -> Event:
    evento = Event(
        nome=dados.nome.strip(),
        empresa_nome=dados.empresa_nome.strip(),
        demo=dados.demo,
        telao_token=novo_token_telao(),
    )
    db.add(evento)
    db.flush()
    db.add(DisplayState(event_id=evento.id, versao=1))
    db.add(AuditLog(event_id=evento.id, usuario_id=user.id, acao="evento_criado", detalhes={}))
    db.commit()
    db.refresh(evento)
    return evento


@router.get("/{event_id}", response_model=EventoOut, dependencies=VISUALIZAR)
def obter(evento: Event = Depends(evento_atual)) -> Event:
    return evento


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(
    dados: ExcluirEventoIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> Response:
    """Apaga o evento e tudo dele (so o admin), com o nome digitado como confirmacao.

    Evento SEM sorteio: apaga direto. Evento COM sorteios: so se estiver marcado
    como evento de teste e com `apagar_sorteios` -- os resultados de um evento
    real nunca sao apagados. Os sorteios, entregas e notificacoes vao junto.

    A auditoria e preservada: os registros do evento ficam (sem o vinculo com
    o evento apagado) e entra um registro geral com o que foi apagado.
    """
    if dados.nome_confirmacao.strip().lower() != evento.nome.strip().lower():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Digite o nome do evento exatamente como aparece para confirmar."
        )
    sorteios = db.scalar(select(func.count(Draw.id)).where(Draw.event_id == evento.id)) or 0
    if sorteios and not evento.evento_teste:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Este evento já tem {sorteios} sorteio(s) registrado(s) e não pode ser apagado: "
            "os resultados ficam guardados. Se é um evento de teste, marque-o como \"Evento de teste\" "
            "em Editar e exclua de novo.",
        )
    if sorteios and not dados.apagar_sorteios:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Este evento de teste tem {sorteios} sorteio(s). Confirme que os sorteios, entregas e "
            "notificações dele também serão apagados.",
        )
    contagem = {
        "participantes": db.scalar(select(func.count(Participant.id)).where(Participant.event_id == evento.id)) or 0,
        "premios": db.scalar(select(func.count(Prize.id)).where(Prize.event_id == evento.id)) or 0,
        "sorteios": sorteios,
        "notificacoes": db.scalar(select(func.count(Notificacao.id)).where(Notificacao.event_id == evento.id)) or 0,
    }
    # Fotos das entregas (mostram a pessoa): os arquivos saem junto com o evento.
    fotos = fotos_entrega.urls_do_evento(db, evento.id)
    # Auditoria preservada: os registros do evento perdem so o vinculo.
    db.execute(update(AuditLog).where(AuditLog.event_id == evento.id).values(event_id=None))
    if sorteios:
        # Ordem que o banco exige: os sorteios apontam para participantes
        # (RESTRICT), para blocos e para o sorteio anterior (resorteio).
        db.execute(delete(Notificacao).where(Notificacao.event_id == evento.id))
        db.execute(update(Draw).where(Draw.event_id == evento.id).values(draw_anterior_id=None))
        db.execute(delete(Draw).where(Draw.event_id == evento.id))
    db.add(
        AuditLog(
            event_id=None,
            usuario_id=user.id,
            acao="evento_excluido",
            detalhes={
                "evento_id": evento.id,
                "nome": evento.nome,
                "empresa": evento.empresa_nome,
                "evento_teste": evento.evento_teste,
                **contagem,
            },
        )
    )
    db.flush()
    db.delete(evento)
    db.commit()
    fotos_entrega.apagar_arquivos(fotos)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{event_id}/ambiente-teste", response_model=EventoOut, status_code=status.HTTP_201_CREATED)
def criar_ambiente_teste(
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> Event:
    """Cria uma copia de teste deste evento (so o admin). O evento real nao muda.

    Ver services/ambiente_teste.py: nomes trocados, presenca confirmada, sem
    sorteios, contas nem dados de identificacao; marcada como evento de teste.
    """
    try:
        copia = ambiente_teste.criar_copia(db, evento, user)
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    db.commit()
    db.refresh(copia)
    return copia


@router.post("/{event_id}/recomecar-teste")
def recomecar_teste(
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(GERENCIAR),
) -> dict:
    """Zera os sorteios de um EVENTO DE TESTE (so o admin) para ensaiar de novo."""
    try:
        # Fotos das entregas do teste saem junto com os sorteios (mostram a pessoa).
        fotos = fotos_entrega.urls_do_evento(db, evento.id) if evento.evento_teste else set()
        resultado = ambiente_teste.recomecar(db, evento, user)
    except RegraDeNegocio as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.mensagem) from exc
    db.commit()
    fotos_entrega.apagar_arquivos(fotos)
    notificar_atualizacao(db, evento)
    return resultado


@router.patch("/{event_id}", response_model=EventoOut)
def atualizar_config(
    dados: EventoConfigIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> Event:
    alterado = dados.model_dump(exclude_unset=True)
    # Tema, som, cores do claro e marca de teste sao obrigatorios: null nao muda nada.
    for campo in ("tema_telao", "som_sorteio", "evento_teste", *CAMPOS_COR_CLARO):
        if campo in alterado and alterado[campo] is None:
            del alterado[campo]
    # Marcar/desmarcar evento de teste (some do portal do colaborador): so o admin.
    if "evento_teste" in alterado and not tem_permissao(user, Permissao.GERENCIAR_EVENTOS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só o administrador marca um evento como teste.")
    for campo in CAMPOS_COR:
        valor = alterado.get(campo)
        if valor is not None and not COR_RE.match(valor):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"Cor inválida em {campo}: use formato #RRGGBB"
            )
    for campo, valor in alterado.items():
        setattr(evento, campo, valor)
    if (
        evento.autocadastro_inicio is not None
        and evento.autocadastro_fim is not None
        and evento.autocadastro_inicio >= evento.autocadastro_fim
    ):
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "O fim do período de cadastro precisa ser depois do início",
        )
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=user.id,
            acao="evento_configurado",
            detalhes={
                "campos": list(alterado.keys()),
                **({"evento_teste": alterado["evento_teste"]} if "evento_teste" in alterado else {}),
            },
        )
    )
    db.commit()
    db.refresh(evento)
    notificar_atualizacao(db, evento)
    return evento


@router.post("/{event_id}/telao/novo-token", response_model=EventoOut)
def regerar_token(
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(CONFIGURAR),
) -> Event:
    evento.telao_token = novo_token_telao()
    db.add(AuditLog(event_id=evento.id, usuario_id=user.id, acao="telao_token_regerado", detalhes={}))
    db.commit()
    db.refresh(evento)
    return evento


# ------------------------------------------------------------------ regras
@router.get("/{event_id}/regras", response_model=RegrasOut, dependencies=VISUALIZAR)
def obter_regras(evento: Event = Depends(evento_atual)) -> Event:
    return evento


@router.get("/{event_id}/regras/resumo", dependencies=VISUALIZAR)
def resumo_das_regras(
    evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> dict:
    total_sorteios = db.scalar(
        select(func.count(Draw.id)).where(Draw.event_id == evento.id)
    ) or 0
    return {
        "itens": resumo_regras(evento),
        "regras_participacao": evento.regras_participacao,
        "confirmadas_em": evento.regras_confirmadas_em,
        "primeiro_sorteio_realizado": total_sorteios > 0,
        "elegiveis_agora": len(participantes_elegiveis(db, evento)),
    }


@router.patch("/{event_id}/regras", response_model=RegrasOut)
def atualizar_regras(
    dados: RegrasIn,
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(DEFINIR_REGRAS),
) -> Event:
    houve_sorteio = (
        db.scalar(select(func.count(Draw.id)).where(Draw.event_id == evento.id)) or 0
    ) > 0
    alterado = dados.model_dump(exclude_unset=True)
    # Modo faixa de matriculas: a faixa resultante precisa existir e ser valida.
    modo = alterado.get("modo_sorteio", evento.modo_sorteio)
    inicio = alterado.get("matricula_faixa_inicio", evento.matricula_faixa_inicio)
    fim = alterado.get("matricula_faixa_fim", evento.matricula_faixa_fim)
    if modo == ModoSorteio.FAIXA_MATRICULA.value and (inicio is None or fim is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Informe a matrícula inicial e a final para sortear por faixa de matrículas.",
        )
    if inicio is not None and fim is not None and inicio > fim:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A matrícula inicial da faixa precisa ser menor ou igual à final.",
        )
    for campo, valor in alterado.items():
        anterior = getattr(evento, campo)
        if anterior == valor:
            continue
        setattr(evento, campo, valor)
        db.add(
            RuleChange(
                event_id=evento.id,
                campo=campo,
                valor_anterior=str(anterior),
                valor_novo=str(valor),
                apos_primeiro_sorteio=houve_sorteio,
                usuario_id=user.id,
            )
        )
    db.commit()
    db.refresh(evento)
    if {"modo_sorteio", "matricula_faixa_inicio", "matricula_faixa_fim"} & alterado.keys():
        # O telao mostra o numero da sorte ou a matricula conforme o modo: quem
        # ja esta na tela (ex.: apresentacao dos ganhadores) troca na hora.
        notificar_atualizacao(db, evento)
    return evento


@router.get("/{event_id}/regras/faixa-matricula", response_model=FaixaMatriculaOut, dependencies=PREVIA_REGRAS)
def previa_faixa_matricula(
    inicio: int | None = Query(None, ge=0, le=999_999_999),
    fim: int | None = Query(None, ge=0, le=999_999_999),
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
) -> FaixaMatriculaOut:
    """Quantos participantes ativos ficam dentro e fora da faixa (sem aplicar presenca)."""
    ativos = db.scalars(
        select(Participant.matricula_normalizada).where(
            Participant.event_id == evento.id, Participant.participando.is_(True)
        )
    ).all()
    numeros = [int(m) for m in ativos if (m or "").isdigit()]
    dentro = (
        sum(1 for n in numeros if inicio <= n <= fim)
        if inicio is not None and fim is not None and inicio <= fim
        else 0
    )
    return FaixaMatriculaOut(
        inicio=inicio,
        fim=fim,
        participantes_ativos=len(ativos),
        dentro_da_faixa=dentro,
        fora_da_faixa=len(numeros) - dentro,
        matricula_nao_numerica=len(ativos) - len(numeros),
        menor_matricula=min(numeros) if numeros else None,
        maior_matricula=max(numeros) if numeros else None,
    )


@router.post("/{event_id}/regras/confirmar", response_model=RegrasOut)
def confirmar_regras(
    evento: Event = Depends(evento_atual),
    db: Session = Depends(get_db),
    user: User = Depends(DEFINIR_REGRAS),
) -> Event:
    evento.regras_confirmadas_em = utcnow()
    db.add(AuditLog(event_id=evento.id, usuario_id=user.id, acao="regras_confirmadas", detalhes={}))
    db.commit()
    db.refresh(evento)
    return evento


@router.get(
    "/{event_id}/regras/historico", response_model=list[MudancaRegraOut], dependencies=VISUALIZAR
)
def historico_regras(
    evento: Event = Depends(evento_atual), db: Session = Depends(get_db)
) -> list[MudancaRegraOut]:
    linhas = db.scalars(
        select(RuleChange)
        .where(RuleChange.event_id == evento.id)
        .order_by(RuleChange.criado_em.desc())
    ).all()
    return [
        MudancaRegraOut(
            id=linha.id,
            campo=linha.campo,
            valor_anterior=linha.valor_anterior,
            valor_novo=linha.valor_novo,
            apos_primeiro_sorteio=linha.apos_primeiro_sorteio,
            usuario_nome=linha.usuario.nome if linha.usuario else "",
            criado_em=linha.criado_em,
        )
        for linha in linhas
    ]


# ------------------------------------------------------------------ resumo
@router.get("/{event_id}/resumo", response_model=ResumoOut, dependencies=VISUALIZAR)
def resumo(evento: Event = Depends(evento_atual), db: Session = Depends(get_db)) -> ResumoOut:
    total = db.scalar(
        select(func.count(Participant.id)).where(Participant.event_id == evento.id)
    ) or 0
    presentes = db.scalar(
        select(func.count(Participant.id)).where(
            Participant.event_id == evento.id, Participant.presente.is_(True)
        )
    ) or 0
    premios_total = db.scalar(
        select(func.count(Prize.id)).where(Prize.event_id == evento.id, Prize.excluido_em.is_(None))
    ) or 0

    # Unidades de premio excluido: so contam as que tem resultado valido.
    unidades = db.execute(
        select(PrizeUnit.status, func.count(PrizeUnit.id))
        .join(Prize, PrizeUnit.prize_id == Prize.id)
        .where(Prize.event_id == evento.id, PrizeUnit.status != StatusUnidade.REMOVIDO.value)
        .group_by(PrizeUnit.status)
    ).all()
    por_status = {status_: quantidade for status_, quantidade in unidades}

    anulados = db.scalar(
        select(func.count(Draw.id)).where(
            Draw.event_id == evento.id, Draw.status == StatusSorteio.ANULADO.value
        )
    ) or 0

    return ResumoOut(
        participantes_total=total,
        participantes_presentes=presentes,
        participantes_elegiveis=len(participantes_elegiveis(db, evento)),
        premios_total=premios_total,
        unidades_total=sum(por_status.values()),
        unidades_disponiveis=por_status.get(StatusUnidade.DISPONIVEL.value, 0),
        unidades_sorteadas=por_status.get(StatusUnidade.SORTEADO.value, 0),
        unidades_entregues=por_status.get(StatusUnidade.ENTREGUE.value, 0),
        sorteios_anulados=anulados,
    )
