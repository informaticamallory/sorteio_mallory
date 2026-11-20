from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Draw, Event, ModoSorteio, Participant, StatusSorteio, TratamentoAusente


def numero_da_matricula(participante: Participant) -> int | None:
    """Matricula como numero ("00026" -> 26); None se tiver letras ou simbolos."""
    texto = participante.matricula_normalizada or ""
    return int(texto) if texto.isdigit() else None


def modo_faixa_matricula(evento: Event) -> bool:
    return evento.modo_sorteio == ModoSorteio.FAIXA_MATRICULA.value


def matricula_da_sorte(evento: Event, participante: Participant) -> str | None:
    """No modo faixa de matriculas, a matricula e o numero da sorte exibido.

    Preenchido so nesse modo: e o que o cartao, a consulta e o telao mostram
    no lugar do numero aleatorio (decisao do evento: com o sorteio pela
    matricula, ela aparece tambem no telao). No modo padrao devolve None e
    tudo continua mostrando o numero aleatorio. O QR Code e a busca seguem
    usando o numero aleatorio internamente.
    """
    if not modo_faixa_matricula(evento):
        return None
    return participante.matricula or None


def na_faixa(evento: Event, participante: Participant) -> bool:
    numero = numero_da_matricula(participante)
    inicio, fim = evento.matricula_faixa_inicio, evento.matricula_faixa_fim
    if numero is None or inicio is None or fim is None:
        return False
    return inicio <= numero <= fim


def participantes_elegiveis(db: Session, evento: Event) -> list[Participant]:
    """Lista, em ordem estavel (por id), quem pode concorrer na proxima rodada.

    Regras aplicadas, nesta ordem:
      1. participacao ativa (nao excluido pelo organizador);
      2. presenca confirmada, se a regra exigir (ou se ausentes sao bloqueados);
      3. ja ganhou antes, se o evento nao permitir multiplas vitorias;
      4. teve um resultado anulado por ausencia e a regra nao permite reconcorrer;
      5. modo faixa de matriculas: so quem tem matricula numerica dentro da faixa.

    O sorteio escolhe UM indice uniforme nesta lista. No modo faixa isso tem a
    mesma distribuicao de "sortear um numero na faixa e repetir ate cair em um
    elegivel", sem as tentativas vazias.
    """
    condicoes = [Participant.event_id == evento.id, Participant.participando.is_(True)]
    if evento.exige_presenca or evento.tratamento_ausente == TratamentoAusente.BLOQUEAR.value:
        condicoes.append(Participant.presente.is_(True))

    participantes = list(
        db.scalars(select(Participant).where(*condicoes).order_by(Participant.id)).all()
    )

    if not evento.permite_multiplas_vitorias:
        ja_ganharam = set(
            db.scalars(
                select(Draw.participant_id).where(
                    Draw.event_id == evento.id,
                    Draw.status == StatusSorteio.VALIDO.value,
                )
            ).all()
        )
        participantes = [p for p in participantes if p.id not in ja_ganharam]

    if not evento.ausente_pode_concorrer_novamente:
        anulados_por_ausencia = set(
            db.scalars(
                select(Draw.participant_id).where(
                    Draw.event_id == evento.id,
                    Draw.status == StatusSorteio.ANULADO.value,
                    Draw.tipo_anulacao == "ausencia",
                )
            ).all()
        )
        participantes = [p for p in participantes if p.id not in anulados_por_ausencia]

    if modo_faixa_matricula(evento):
        participantes = [p for p in participantes if na_faixa(evento, p)]

    return participantes


def ids_ja_ganharam(db: Session, evento: Event) -> set[int]:
    return set(
        db.scalars(
            select(Draw.participant_id).where(
                Draw.event_id == evento.id, Draw.status == StatusSorteio.VALIDO.value
            )
        ).all()
    )


def resumo_regras(evento: Event) -> list[str]:
    """Texto legivel das regras, exibido ao organizador antes do primeiro sorteio."""
    tratamento = {
        TratamentoAusente.BLOQUEAR.value: "Ausentes não entram no sorteio.",
        TratamentoAusente.RESORTEAR.value: (
            "Se o ganhador não estiver presente, o resultado é anulado e a unidade é sorteada novamente."
        ),
        TratamentoAusente.MANTER_PENDENTE.value: (
            "Se o ganhador não estiver presente, o prêmio fica pendente de retirada."
        ),
    }[evento.tratamento_ausente]

    if modo_faixa_matricula(evento):
        if evento.matricula_faixa_inicio is not None and evento.matricula_faixa_fim is not None:
            modo = (
                "Modo do sorteio: faixa de matrículas, de "
                f"{evento.matricula_faixa_inicio} a {evento.matricula_faixa_fim}. "
                "Só concorre quem tem matrícula numérica dentro da faixa."
            )
        else:
            modo = "Modo do sorteio: faixa de matrículas (faixa ainda não definida)."
    else:
        modo = "Modo do sorteio: número da sorte. Todos os elegíveis concorrem com a mesma chance."

    return [
        modo,
        "Cada pessoa pode ganhar varias vezes."
        if evento.permite_multiplas_vitorias
        else "Cada pessoa pode ganhar apenas uma vez.",
        "Somente participantes com presenca confirmada concorrem."
        if evento.exige_presenca
        else "Todos os participantes ativos concorrem, com ou sem presenca confirmada.",
        tratamento,
        "Quem teve resultado anulado por ausencia pode concorrer nas proximas rodadas."
        if evento.ausente_pode_concorrer_novamente
        else "Quem teve resultado anulado por ausência não concorre nas próximas rodadas.",
    ]
