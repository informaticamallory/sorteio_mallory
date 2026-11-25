"""Carrossel dos ganhadores no telao (Fase 7).

O estado oficial fica em DisplayState (servidor): bloco, posicao base,
instante em que a reproducao comecou nessa posicao (NULL = pausado) e duracao
de cada slide. Telao e painel calculam o slide atual a partir disso com o
relogio do servidor, entao F5, reconexao ou dois teloes mostram o mesmo slide.

Posicoes: 0..total-1 sao os ganhadores; `total` e o slide-resumo final.

A apresentacao so le resultados: nao sorteia, nao altera resultado e nao
inicia o proximo bloco.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import AuditLog, BlocoSorteio, DisplayState, EstadoTelao, Event, User, utcnow
from .blocos import em_revelacao, ganhadores_do_bloco
from .erros import RegraDeNegocio

# Tempo minimo de cada ganhador na tela (migracao 0016: era 5 s).
DURACAO_MINIMA_S = 1
# Depois que o telao revela o ultimo sorteio do bloco, o ganhador fica na tela
# por este tempo antes de o carrossel comecar sozinho.
PAUSA_APOS_REVELACAO_S = 5


def slides(db: Session, bloco: BlocoSorteio) -> list[dict]:
    """Ganhadores validos do bloco, sem pulseira (vai ao telao).

    Matricula so no modo faixa de matriculas, como numero da sorte.
    """
    saida = []
    for g in ganhadores_do_bloco(db, bloco):
        slide = {
            "premio_nome": g["premio_nome"],
            "premio_imagem_url": g["premio_imagem_url"],
            "premio_descricao": g["premio_descricao"],
            "unidade_numero": g["unidade_numero"],
            "ganhador_nome": g["ganhador_nome"],
            "ganhador_setor": g["ganhador_setor"],
            "ganhador_foto_url": g["ganhador_foto_url"],
            "ganhador_numero": g["ganhador_numero"],
        }
        # No modo padrao a chave nem aparece (telao sem matricula).
        if g["ganhador_matricula_da_sorte"] is not None:
            slide["ganhador_matricula_da_sorte"] = g["ganhador_matricula_da_sorte"]
        saida.append(slide)
    return saida


def posicao(ds: DisplayState, total: int, agora: datetime | None = None) -> int:
    if ds.carrossel_desde is None:
        return min(max(ds.carrossel_indice, 0), total)
    agora = agora or utcnow()
    decorrido = max(0.0, (agora - ds.carrossel_desde).total_seconds())
    duracao = max(DURACAO_MINIMA_S, ds.carrossel_duracao_s)
    return min(total, ds.carrossel_indice + int(decorrido // duracao))


def limpar(ds: DisplayState) -> None:
    ds.carrossel_bloco_id = None
    ds.carrossel_indice = 0
    ds.carrossel_desde = None


def _auditar(db: Session, evento: Event, usuario: User | None, acao: str, detalhes: dict) -> None:
    db.add(
        AuditLog(
            event_id=evento.id,
            usuario_id=usuario.id if usuario else None,
            acao=acao,
            detalhes=detalhes,
        )
    )


def iniciar(
    db: Session, evento: Event, bloco: BlocoSorteio, usuario: User | None, automatico: bool = False
) -> DisplayState:
    """Comeca (ou recomeca) a apresentacao do bloco. Nao faz commit."""
    if bloco.event_id != evento.id:
        raise RegraDeNegocio("Bloco não pertence a este evento.", 404)
    total = len(slides(db, bloco))
    if total == 0:
        raise RegraDeNegocio(f"O {bloco.nome} ainda não tem ganhadores para apresentar.", 409)

    ds = db.get(DisplayState, evento.id)
    if ds is None:
        ds = DisplayState(event_id=evento.id, estado=EstadoTelao.AGUARDANDO.value, versao=1)
        db.add(ds)
    agora = utcnow()
    duracao = max(DURACAO_MINIMA_S, evento.carrossel_segundos)

    if em_revelacao(db, evento):
        if not automatico:
            raise RegraDeNegocio(
                "Aguarde o telão revelar o sorteio em andamento antes de apresentar os ganhadores.",
                409,
            )
        # Fim de bloco durante a animacao do ultimo sorteio: a revelacao nao e
        # interrompida; o carrossel fica agendado e o telao muda sozinho
        # (transicao preguicosa em telao.obter_estado).
        inicio = ds.revelar_em + timedelta(seconds=PAUSA_APOS_REVELACAO_S)
    else:
        inicio = agora
        ds.estado = EstadoTelao.CARROSSEL_GANHADORES.value
        ds.prize_unit_id = None
        ds.draw_id = None
        ds.nomes_animacao = []
        ds.revelar_em = None

    ds.carrossel_bloco_id = bloco.id
    ds.carrossel_indice = 0
    ds.carrossel_desde = inicio
    ds.carrossel_duracao_s = duracao
    ds.versao += 1
    _auditar(
        db,
        evento,
        usuario,
        "carrossel_iniciado",
        {
            "bloco_id": bloco.id,
            "numero": bloco.numero_exibicao,
            "ganhadores": total,
            "segundos_por_ganhador": duracao,
            "automatico": automatico,
        },
    )
    return ds


def comandar(db: Session, evento: Event, acao: str, usuario: User) -> DisplayState:
    """pausar | continuar | repetir | proximo | anterior | encerrar. Nao faz commit."""
    ds = db.get(DisplayState, evento.id)
    if ds is None or ds.estado != EstadoTelao.CARROSSEL_GANHADORES.value or ds.carrossel_bloco_id is None:
        raise RegraDeNegocio("Não há apresentação de ganhadores no telão agora.", 409)
    bloco = db.get(BlocoSorteio, ds.carrossel_bloco_id)
    total = len(slides(db, bloco)) if bloco else 0
    agora = utcnow()
    atual = posicao(ds, total, agora)
    tocando = ds.carrossel_desde is not None

    if acao == "pausar":
        ds.carrossel_indice, ds.carrossel_desde = atual, None
    elif acao == "continuar":
        if not tocando:
            ds.carrossel_indice, ds.carrossel_desde = atual, agora
    elif acao == "repetir":
        ds.carrossel_indice, ds.carrossel_desde = 0, agora
    elif acao in {"proximo", "anterior"}:
        destino = min(total, atual + 1) if acao == "proximo" else max(0, atual - 1)
        ds.carrossel_indice = destino
        ds.carrossel_desde = agora if tocando else None
    elif acao == "encerrar":
        ds.estado = EstadoTelao.AGUARDANDO.value
        limpar(ds)
    else:  # pragma: no cover - validado no schema
        raise RegraDeNegocio("Ação inválida.", 422)

    ds.versao += 1
    _auditar(
        db,
        evento,
        usuario,
        "carrossel_encerrado" if acao == "encerrar" else "carrossel_comando",
        {"acao": acao, "bloco_id": bloco.id if bloco else None, "posicao": atual},
    )
    return ds


def payload(db: Session, ds: DisplayState, agora: datetime) -> tuple[dict | None, BlocoSorteio | None]:
    """Parte do estado do telao que descreve o carrossel."""
    bloco = db.get(BlocoSorteio, ds.carrossel_bloco_id) if ds.carrossel_bloco_id else None
    if bloco is None:
        return None, None
    lista = slides(db, bloco)
    return (
        {
            "bloco_id": bloco.id,
            "slides": lista,
            "total": len(lista),
            "duracao_s": max(DURACAO_MINIMA_S, ds.carrossel_duracao_s),
            "indice": ds.carrossel_indice,
            "rodando_desde": ds.carrossel_desde,
            "pausado": ds.carrossel_desde is None,
            "posicao": posicao(ds, len(lista), agora),
        },
        bloco,
    )
