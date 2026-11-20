"""Consultas compartilhadas pela recepcao, credenciamento e area pessoal."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, aliased

from ..models import BlocoSorteio, Draw, Participant, Prize, PrizeUnit, StatusSorteio, User
from ..texto import contem, normalizar_busca, normalizar_matricula


def condicao_busca_participante(q: str) -> list:
    """Cada palavra precisa aparecer no nome (sem acento), matricula ou pulseira."""
    return [
        or_(
            contem(Participant.nome_busca, normalizar_busca(termo)),
            contem(Participant.matricula, termo),
            # "26" encontra "00026".
            Participant.matricula_normalizada == normalizar_matricula(termo),
            contem(Participant.pulseira, termo.upper()),
        )
        for termo in q.split()
    ]


def premios_ganhos(db: Session, participantes: list[int]) -> dict[int, list[dict]]:
    """Resultados VALIDOS de cada participante, na ordem dos sorteios."""
    if not participantes:
        return {}
    entregador = aliased(User)
    linhas = db.execute(
        select(Draw, PrizeUnit, Prize, BlocoSorteio, entregador)
        .join(PrizeUnit, Draw.prize_unit_id == PrizeUnit.id)
        .join(Prize, PrizeUnit.prize_id == Prize.id)
        .outerjoin(BlocoSorteio, Draw.bloco_id == BlocoSorteio.id)
        .outerjoin(entregador, Draw.entregue_por_id == entregador.id)
        .where(
            Draw.participant_id.in_(participantes),
            Draw.status == StatusSorteio.VALIDO.value,
        )
        .order_by(Draw.rodada)
    ).all()
    resultado: dict[int, list[dict]] = defaultdict(list)
    for sorteio, unidade, premio, bloco, quem_entregou in linhas:
        resultado[sorteio.participant_id].append(
            {
                "sorteio_id": sorteio.id,
                "rodada": sorteio.rodada,
                "premio_nome": premio.nome,
                "premio_imagem_url": premio.imagem_url,
                "unidade_numero": unidade.numero,
                "bloco_numero": bloco.numero if bloco else None,
                "entregue": sorteio.entregue,
                "entregue_em": sorteio.entregue_em,
                "entregue_por": quem_entregou.nome if quem_entregou else None,
                "quantidade_premio": premio.quantidade,
                "sorteado_em": sorteio.criado_em,
            }
        )
    return resultado
