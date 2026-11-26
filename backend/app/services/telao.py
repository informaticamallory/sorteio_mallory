from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import bus
from . import carrossel
from .elegibilidade import matricula_da_sorte
from ..models import (
    BlocoSorteio,
    DisplayState,
    Draw,
    EstadoTelao,
    Event,
    Participant,
    Prize,
    PrizeUnit,
    StatusSorteio,
    utcnow,
)

MAX_NOMES_ANIMACAO = 60


def obter_display(db: Session, evento: Event) -> DisplayState:
    ds = db.get(DisplayState, evento.id)
    if ds is None:
        ds = DisplayState(event_id=evento.id, estado=EstadoTelao.AGUARDANDO.value, versao=1)
        db.add(ds)
        db.commit()
    return ds


def nomes_para_animacao(elegiveis: list[Participant], ganhador_id: int) -> list[str]:
    """Amostra de nomes elegiveis para a animacao, sempre incluindo o ganhador.

    O telao nunca recebe matricula nem a lista completa de participantes.
    """
    outros = [p for p in elegiveis if p.id != ganhador_id]
    random.shuffle(outros)
    nomes = [p.nome for p in outros[: MAX_NOMES_ANIMACAO - 1]]
    ganhador = next((p for p in elegiveis if p.id == ganhador_id), None)
    if ganhador is not None:
        nomes.append(ganhador.nome)
    random.shuffle(nomes)
    return nomes


def _com_matricula_da_sorte(dados: dict, chave: str, matricula: str | None) -> dict:
    """Acrescenta a matricula SO no modo faixa de matriculas.

    No modo padrao a chave nem aparece: o telao continua sem matricula.
    """
    if matricula is not None:
        dados[chave] = matricula
    return dados


def _evento_payload(evento: Event) -> dict:
    return {
        "nome": evento.nome,
        "empresa_nome": evento.empresa_nome,
        "logo_url": evento.logo_url,
        "cor_fundo": evento.cor_fundo,
        "cor_primaria": evento.cor_primaria,
        "cor_texto": evento.cor_texto,
        "cor_destaque": evento.cor_destaque,
        "mensagem_boas_vindas": evento.mensagem_boas_vindas,
        "mensagem_encerramento": evento.mensagem_encerramento,
        "som_ativado": evento.som_ativado,
        "reduzir_animacoes": evento.reduzir_animacoes,
        "duracao_animacao_ms": evento.duracao_animacao_ms,
        "fuso_horario": evento.fuso_horario,
        "tema_telao": evento.tema_telao or TEMA_CLASSICO,
        "cores_claro": {
            "fundo": evento.claro_cor_fundo,
            "painel": evento.claro_cor_painel,
            "destaque": evento.claro_cor_destaque,
            "texto": evento.claro_cor_texto,
        },
    }


TEMA_CLASSICO = "classico"
TEMA_CLARO = "mallory_claro"


def numero_exibido(evento: Event, participante: Participant) -> str:
    """Numero que o telao mostra para o ganhador (como no anuncio do ganhador):
    a matricula no modo faixa de matriculas; senao o numero da sorte com 4 digitos."""
    matricula = matricula_da_sorte(evento, participante)
    if matricula is not None:
        return str(matricula)
    return str(participante.numero_sorteio or 0).zfill(4)


def _galeria(db: Session, evento: Event) -> list[dict]:
    linhas = db.execute(
        select(Draw, PrizeUnit, Prize, Participant)
        .join(PrizeUnit, Draw.prize_unit_id == PrizeUnit.id)
        .join(Prize, PrizeUnit.prize_id == Prize.id)
        .join(Participant, Draw.participant_id == Participant.id)
        .where(Draw.event_id == evento.id, Draw.status == StatusSorteio.VALIDO.value)
        .order_by(Draw.rodada)
    ).all()
    return [
        _com_matricula_da_sorte(
            {
                "premio_nome": premio.nome,
                "premio_imagem_url": premio.imagem_url,
                "unidade_numero": unidade.numero,
                "ganhador_nome": participante.nome,
                "ganhador_setor": participante.setor,
                "ganhador_foto_url": participante.foto_url,
                "ganhador_numero": participante.numero_sorteio,
            },
            "ganhador_matricula_da_sorte",
            matricula_da_sorte(evento, participante),
        )
        for _draw, unidade, premio, participante in linhas
    ]


def _serializar(db: Session, evento: Event, ds: DisplayState) -> dict:
    agora = utcnow()
    payload: dict = {
        "versao": ds.versao,
        "estado": ds.estado,
        "evento": _evento_payload(evento),
        "rodada": None,
        "premio": None,
        "ganhador": None,
        "nomes_animacao": [],
        "revelar_em": ds.revelar_em,
        "servidor_agora": agora,
        "galeria": [],
        "bloco": None,
        "carrossel": None,
        # Carrossel agendado para depois da revelacao em curso (fim de bloco).
        "carrossel_agendado_em": None,
        # Tema claro, durante o "sorteando": quantos rolos de numero girar.
        "digitos_animacao": None,
    }

    if ds.estado == EstadoTelao.CARROSSEL_GANHADORES.value:
        dados, bloco = carrossel.payload(db, ds, agora)
        payload["carrossel"] = dados
        if bloco is not None:
            payload["bloco"] = {"numero": bloco.numero_exibicao, "nome": bloco.nome_exibicao}
        return payload
    if ds.carrossel_bloco_id is not None and ds.carrossel_desde is not None:
        payload["carrossel_agendado_em"] = ds.carrossel_desde

    sorteio = db.get(Draw, ds.draw_id) if ds.draw_id else None
    unidade = db.get(PrizeUnit, ds.prize_unit_id) if ds.prize_unit_id else None
    # Bloco do sorteio exibido (gravado no resultado) ou do premio apresentado.
    bloco_id = sorteio.bloco_id if sorteio is not None else (unidade.bloco_id if unidade else None)
    bloco = db.get(BlocoSorteio, bloco_id) if bloco_id else None
    if bloco is not None:
        payload["bloco"] = {"numero": bloco.numero_exibicao, "nome": bloco.nome_exibicao}

    if unidade is not None:
        premio = db.get(Prize, unidade.prize_id)
        if premio is not None:
            payload["premio"] = {
                "nome": premio.nome,
                "descricao": premio.descricao,
                "imagem_url": premio.imagem_url,
                "unidade_numero": unidade.numero,
                "unidade_total": premio.quantidade,
            }

    if ds.estado == EstadoTelao.SORTEANDO.value:
        # Os dois temas giram rolos de numeros aleatorios. O telao recebe so
        # QUANTOS digitos tem o numero (para montar os rolos); nenhum nome de
        # elegivel e nenhum digito do ganhador antes da revelacao.
        # (nomes_animacao continua no payload, sempre vazio, por compatibilidade.)
        participante = db.get(Participant, sorteio.participant_id) if sorteio is not None else None
        payload["digitos_animacao"] = len(numero_exibido(evento, participante)) if participante else 4

    if sorteio is not None:
        payload["rodada"] = sorteio.rodada
        if ds.estado == EstadoTelao.RESULTADO.value:
            ganhador = db.get(Participant, sorteio.participant_id)
            if ganhador is not None:
                # Nunca enviamos pulseira para o telao. A matricula so vai no
                # modo faixa de matriculas, em que ela e o numero da sorte
                # (decisao do evento); no modo padrao vai so o numero aleatorio.
                payload["ganhador"] = _com_matricula_da_sorte(
                    {
                        "nome": ganhador.nome,
                        "setor": ganhador.setor,
                        "foto_url": ganhador.foto_url,
                        "numero_sorteio": ganhador.numero_sorteio,
                    },
                    "matricula_da_sorte",
                    matricula_da_sorte(evento, ganhador),
                )

    if ds.estado == EstadoTelao.ENCERRAMENTO.value:
        payload["galeria"] = _galeria(db, evento)

    return payload


def obter_estado(db: Session, evento: Event) -> dict:
    """Estado atual do telao, aplicando a transicao sorteando -> resultado.

    A transicao e preguicosa (sem timer no servidor): quando o instante de
    revelacao ja passou, qualquer leitura promove o estado. Isso torna F5 e
    reconexao seguros e nunca dispara um novo sorteio.
    """
    ds = obter_display(db, evento)
    agora = utcnow()
    mudou = False
    if (
        ds.estado == EstadoTelao.SORTEANDO.value
        and ds.revelar_em is not None
        and agora >= ds.revelar_em
    ):
        ds.estado = EstadoTelao.RESULTADO.value
        mudou = True
    # Carrossel agendado no fim do bloco: comeca sozinho apos a revelacao.
    if (
        ds.estado == EstadoTelao.RESULTADO.value
        and ds.carrossel_bloco_id is not None
        and ds.carrossel_desde is not None
        and agora >= ds.carrossel_desde
    ):
        ds.estado = EstadoTelao.CARROSSEL_GANHADORES.value
        ds.prize_unit_id = None
        ds.draw_id = None
        ds.revelar_em = None
        mudou = True
    if mudou:
        ds.versao += 1
        db.commit()
        db.refresh(ds)
        bus.publicar(evento.id, {"tipo": "estado", **_serializar(db, evento, ds)})
    return _serializar(db, evento, ds)


def publicar_estado(db: Session, evento: Event, ds: DisplayState) -> dict:
    """Grava a versao ja incrementada e transmite o estado ao telao."""
    db.commit()
    db.refresh(ds)
    payload = _serializar(db, evento, ds)
    bus.publicar(evento.id, {"tipo": "estado", **payload})
    return payload


def definir_estado(
    db: Session,
    evento: Event,
    estado: str,
    *,
    prize_unit_id: int | None = None,
    draw_id: int | None = None,
    nomes_animacao: list[str] | None = None,
    duracao_ms: int | None = None,
) -> dict:
    ds = obter_display(db, evento)
    _aplicar(ds, estado, prize_unit_id, draw_id, nomes_animacao, duracao_ms)
    return publicar_estado(db, evento, ds)


def _aplicar(
    ds: DisplayState,
    estado: str,
    prize_unit_id: int | None,
    draw_id: int | None,
    nomes_animacao: list[str] | None,
    duracao_ms: int | None,
) -> None:
    ds.estado = estado
    ds.prize_unit_id = prize_unit_id
    ds.draw_id = draw_id
    ds.nomes_animacao = nomes_animacao or []
    ds.revelar_em = (
        utcnow() + timedelta(milliseconds=duracao_ms)
        if estado == EstadoTelao.SORTEANDO.value and duracao_ms
        else None
    )
    # Qualquer outro comando de tela substitui a apresentacao dos ganhadores.
    carrossel.limpar(ds)
    ds.versao += 1


def preparar_revelacao(
    db: Session, evento: Event, sorteio: Draw, nomes_animacao: list[str], duracao_ms: int
) -> DisplayState:
    """Marca o telao como "sorteando" DENTRO da transacao do sorteio (sem commit).

    A trava "um sorteio por revelacao" (blocos.em_revelacao) le este estado;
    grava-lo na mesma transacao exclusiva do resultado impede que um segundo
    sorteio simultaneo passe entre o commit do resultado e a mudanca do telao.
    O telao so e avisado (publicar_estado) depois do commit.
    """
    ds = db.get(DisplayState, evento.id)
    if ds is None:
        ds = DisplayState(event_id=evento.id, estado=EstadoTelao.AGUARDANDO.value, versao=1)
        db.add(ds)
    _aplicar(
        ds, EstadoTelao.SORTEANDO.value, sorteio.prize_unit_id, sorteio.id, nomes_animacao, duracao_ms
    )
    return ds


def notificar_atualizacao(db: Session, evento: Event) -> None:
    """Reemite o estado atual (usado apos mudancas de configuracao/cores)."""
    ds = obter_display(db, evento)
    bus.publicar(evento.id, {"tipo": "estado", **_serializar(db, evento, ds)})
