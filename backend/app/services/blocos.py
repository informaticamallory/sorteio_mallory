"""Regras dos blocos de sorteio.

Principios:
  * o servidor e a fonte oficial do estado; toda funcao roda dentro da
    transacao da requisicao (BEGIN IMMEDIATE no SQLite);
  * unidade ja sorteada nunca muda de bloco, e resultados nunca sao alterados;
  * blocos PLANEJADO aceitam qualquer reorganizacao; EM_ANDAMENTO e PAUSADO
    ficam congelados; FINALIZADO so pode liberar unidades disponiveis (ex.:
    depois de uma anulacao), que seguem para um bloco de remanescentes.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    AuditLog,
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
    StatusUnidade,
    User,
    utcnow,
)
from .elegibilidade import matricula_da_sorte
from .erros import RegraDeNegocio

NOME_REMANESCENTES = "Prêmios remanescentes"

T = TypeVar("T")


@dataclass
class Progresso:
    total: int = 0
    sorteadas: int = 0
    entregues: int = 0
    restantes: int = 0

    @property
    def percentual(self) -> int:
        return round(100 * self.sorteadas / self.total) if self.total else 0


def _auditar(db: Session, evento: Event, usuario: User, acao: str, detalhes: dict) -> None:
    db.add(AuditLog(event_id=evento.id, usuario_id=usuario.id, acao=acao, detalhes=detalhes))


def nome_padrao(numero: int) -> str:
    return f"Bloco {numero:02d}"


# ------------------------------------------------------------------ consultas
def blocos_do_evento(db: Session, evento_id: int) -> list[BlocoSorteio]:
    return list(
        db.scalars(
            select(BlocoSorteio)
            .where(BlocoSorteio.event_id == evento_id)
            .order_by(BlocoSorteio.ordem, BlocoSorteio.numero)
        ).all()
    )


def unidades_do_evento(db: Session, evento_id: int) -> list[tuple[PrizeUnit, Prize]]:
    """Todas as unidades, na ordem de apresentacao cadastrada nos premios."""
    return [
        (unidade, premio)
        for unidade, premio in db.execute(
            select(PrizeUnit, Prize)
            .join(Prize, PrizeUnit.prize_id == Prize.id)
            .where(Prize.event_id == evento_id)
            .order_by(Prize.ordem, Prize.id, PrizeUnit.numero)
        ).all()
    ]


def modo_blocos(db: Session, evento_id: int) -> bool:
    """Evento com ao menos um bloco: todo sorteio passa a exigir bloco em andamento."""
    return (
        db.scalar(select(BlocoSorteio.id).where(BlocoSorteio.event_id == evento_id).limit(1))
        is not None
    )


def bloco_em_andamento(db: Session, evento_id: int) -> BlocoSorteio | None:
    return db.scalar(
        select(BlocoSorteio).where(
            BlocoSorteio.event_id == evento_id,
            BlocoSorteio.status == StatusBloco.EM_ANDAMENTO.value,
        )
    )


def progresso_por_bloco(db: Session, evento_id: int) -> dict[int | None, Progresso]:
    resultado: dict[int | None, Progresso] = defaultdict(Progresso)
    linhas = db.execute(
        select(PrizeUnit.bloco_id, PrizeUnit.status, func.count(PrizeUnit.id))
        .join(Prize, PrizeUnit.prize_id == Prize.id)
        .where(Prize.event_id == evento_id)
        .group_by(PrizeUnit.bloco_id, PrizeUnit.status)
    ).all()
    for bloco_id, status, quantidade in linhas:
        p = resultado[bloco_id]
        p.total += quantidade
        if status == StatusUnidade.DISPONIVEL.value:
            p.restantes += quantidade
        else:
            p.sorteadas += quantidade
            if status == StatusUnidade.ENTREGUE.value:
                p.entregues += quantidade
    return resultado


def unidades_ordenadas_do_bloco(db: Session, bloco: BlocoSorteio) -> list[tuple[PrizeUnit, Prize]]:
    return [
        (unidade, premio)
        for unidade, premio in db.execute(
            select(PrizeUnit, Prize)
            .join(Prize, PrizeUnit.prize_id == Prize.id)
            .where(PrizeUnit.bloco_id == bloco.id)
            .order_by(PrizeUnit.ordem_bloco, Prize.ordem, Prize.id, PrizeUnit.numero)
        ).all()
    ]


def proxima_do_bloco(db: Session, bloco_id: int) -> tuple[PrizeUnit, Prize] | None:
    """A proxima unidade a sortear: a primeira disponivel na sequencia do bloco.

    Uma unidade cujo resultado foi anulado volta a ficar disponivel e, por
    estar mais acima na sequencia, volta a ser a proxima.
    """
    linha = db.execute(
        select(PrizeUnit, Prize)
        .join(Prize, PrizeUnit.prize_id == Prize.id)
        .where(PrizeUnit.bloco_id == bloco_id, PrizeUnit.status == StatusUnidade.DISPONIVEL.value)
        .order_by(PrizeUnit.ordem_bloco, Prize.ordem, Prize.id, PrizeUnit.numero)
        .limit(1)
    ).first()
    return (linha[0], linha[1]) if linha else None


def _remanescentes(db: Session, evento_id: int) -> list[tuple[PrizeUnit, Prize]]:
    """Unidades disponiveis sem bloco ou deixadas em blocos ja finalizados."""
    finalizados = {
        b.id: b for b in blocos_do_evento(db, evento_id) if b.status == StatusBloco.FINALIZADO.value
    }
    candidatas = [
        (u, p)
        for u, p in unidades_do_evento(db, evento_id)
        if u.status == StatusUnidade.DISPONIVEL.value
        and (u.bloco_id is None or u.bloco_id in finalizados)
    ]

    def chave(item: tuple[PrizeUnit, Prize]) -> tuple:
        unidade, premio = item
        bloco = finalizados.get(unidade.bloco_id)
        # Primeiro as que sobraram dos blocos finalizados (na ordem deles),
        # depois as que nunca foram distribuidas (na ordem dos premios).
        return (
            0 if bloco else 1,
            bloco.ordem if bloco else 0,
            unidade.ordem_bloco or 0,
            premio.ordem,
            premio.id,
            unidade.numero,
        )

    return sorted(candidatas, key=chave)


def contagem_remanescentes(db: Session, evento_id: int) -> int:
    return len(_remanescentes(db, evento_id))


# ------------------------------------------------------------------ regras do sorteio
def em_revelacao(db: Session, evento: Event) -> bool:
    """O telao ainda esta revelando um sorteio (animacao nao terminou)."""
    ds = db.get(DisplayState, evento.id)
    return (
        ds is not None
        and ds.estado == EstadoTelao.SORTEANDO.value
        and ds.revelar_em is not None
        and utcnow() < ds.revelar_em
    )


def bloqueio_do_bloco(db: Session, evento: Event, unidade: PrizeUnit) -> str | None:
    """Motivo pelo qual a unidade nao pode ser sorteada agora (modo blocos)."""
    if not modo_blocos(db, evento.id):
        return None
    if unidade.bloco_id is None:
        return "Esta unidade ainda não foi distribuída em um bloco."
    bloco = db.get(BlocoSorteio, unidade.bloco_id)
    if bloco is None or bloco.status != StatusBloco.EM_ANDAMENTO.value:
        situacao = {
            StatusBloco.PLANEJADO.value: "ainda não foi iniciado",
            StatusBloco.PAUSADO.value: "está pausado",
            StatusBloco.FINALIZADO.value: "já foi finalizado",
        }.get(bloco.status if bloco else "", "não está em andamento")
        nome = bloco.nome if bloco else "bloco"
        return f"O {nome} {situacao}. Sorteie apenas unidades do bloco em andamento."
    if em_revelacao(db, evento):
        return "Aguarde o telão revelar o sorteio em andamento antes de iniciar outro."
    ds = db.get(DisplayState, evento.id)
    if ds is not None and ds.carrossel_bloco_id is not None:
        # A apresentacao dos ganhadores nunca e interrompida por um sorteio:
        # o operador encerra a apresentacao explicitamente.
        return "Encerre a apresentação dos ganhadores no telão antes de sortear."
    return None


# ------------------------------------------------------------------ criacao e edicao
def _proximo(db: Session, evento_id: int) -> tuple[int, int]:
    numero, ordem = db.execute(
        select(
            func.coalesce(func.max(BlocoSorteio.numero), 0),
            func.coalesce(func.max(BlocoSorteio.ordem), 0),
        ).where(BlocoSorteio.event_id == evento_id)
    ).one()
    return numero + 1, ordem + 1


def _nome_livre(db: Session, evento_id: int, nome: str, ignorar_id: int | None = None) -> None:
    """Dois blocos com o mesmo nome no evento confundem o operador no palco."""
    existente = db.scalar(
        select(BlocoSorteio.id).where(
            BlocoSorteio.event_id == evento_id,
            func.lower(BlocoSorteio.nome) == nome.lower(),
            BlocoSorteio.id != (ignorar_id or 0),
        )
    )
    if existente is not None:
        raise RegraDeNegocio(f"Já existe um bloco chamado “{nome}” neste evento. Escolha outro nome.")


def criar_bloco(
    db: Session,
    evento: Event,
    usuario: User,
    nome: str | None,
    capacidade: int | None,
    descricao: str | None = None,
) -> BlocoSorteio:
    numero, ordem = _proximo(db, evento.id)
    nome_final = (nome or "").strip() or nome_padrao(numero)
    _nome_livre(db, evento.id, nome_final)
    bloco = BlocoSorteio(
        event_id=evento.id,
        numero=numero,
        ordem=ordem,
        nome=nome_final,
        descricao=(descricao or "").strip() or None,
        capacidade=capacidade or evento.capacidade_bloco_padrao,
    )
    db.add(bloco)
    db.flush()
    _auditar(db, evento, usuario, "bloco_criado", {"bloco_id": bloco.id, "numero": numero, "nome": nome_final})
    return bloco


def editar_bloco(
    db: Session,
    evento: Event,
    bloco: BlocoSorteio,
    usuario: User,
    nome: str | None,
    capacidade: int | None,
    descricao: str | None = None,
) -> BlocoSorteio:
    alteracoes: dict = {}
    if nome is not None and nome.strip() and nome.strip() != bloco.nome:
        _nome_livre(db, evento.id, nome.strip(), ignorar_id=bloco.id)
        alteracoes["nome"] = [bloco.nome, nome.strip()]
        bloco.nome = nome.strip()
    if descricao is not None and (descricao.strip() or None) != bloco.descricao:
        alteracoes["descricao"] = [bloco.descricao, descricao.strip() or None]
        bloco.descricao = descricao.strip() or None
    if capacidade is not None and capacidade != bloco.capacidade:
        if bloco.status == StatusBloco.FINALIZADO.value:
            raise RegraDeNegocio("Não é possível alterar a capacidade de um bloco finalizado.")
        ocupadas = progresso_por_bloco(db, evento.id)[bloco.id].total
        if capacidade < ocupadas:
            raise RegraDeNegocio(
                f"O {bloco.nome} tem {ocupadas} unidades. Mova unidades antes de reduzir "
                f"a capacidade para {capacidade}."
            )
        alteracoes["capacidade"] = [bloco.capacidade, capacidade]
        bloco.capacidade = capacidade
    if alteracoes:
        _auditar(db, evento, usuario, "bloco_editado", {"bloco_id": bloco.id, **alteracoes})
    return bloco


def remover_bloco(db: Session, evento: Event, bloco: BlocoSorteio, usuario: User) -> int:
    """Exclui um bloco PLANEJADO sem nenhum sorteio. Os premios voltam para "sem bloco".

    Nunca apaga premios, unidades, ganhadores ou historico. As condicoes sao
    conferidas de novo aqui, dentro da transacao (outra pessoa pode ter
    iniciado o bloco depois que a tela foi aberta). Devolve quantas unidades
    ficaram sem bloco.
    """
    if bloco.status != StatusBloco.PLANEJADO.value:
        raise RegraDeNegocio(
            f"O {bloco.nome} já foi iniciado, pausado ou finalizado e não pode ser excluído."
        )
    if db.scalar(select(Draw.id).where(Draw.bloco_id == bloco.id).limit(1)) is not None:
        raise RegraDeNegocio(f"O {bloco.nome} tem sorteios registrados e não pode ser excluído.")
    unidades = list(bloco.unidades)
    if any(u.status != StatusUnidade.DISPONIVEL.value for u in unidades):
        raise RegraDeNegocio(f"O {bloco.nome} tem prêmios já sorteados e não pode ser excluído.")
    for unidade in unidades:
        unidade.bloco_id = None
        unidade.ordem_bloco = None
    _auditar(
        db,
        evento,
        usuario,
        "bloco_removido",
        {"bloco_id": bloco.id, "numero": bloco.numero, "nome": bloco.nome, "unidades_liberadas": len(unidades)},
    )
    db.delete(bloco)
    return len(unidades)


def reordenar_blocos(db: Session, evento: Event, ids: list[int], usuario: User) -> None:
    """Nova sequencia dos blocos PLANEJADOS.

    Os planejados trocam entre si as posicoes que ja ocupavam: blocos
    iniciados, pausados e finalizados ficam exatamente onde estao, e o numero
    (identificador "Bloco 03") nunca muda.
    """
    planejados = [b for b in blocos_do_evento(db, evento.id) if b.status == StatusBloco.PLANEJADO.value]
    por_id = {b.id: b for b in planejados}
    if len(ids) != len(set(ids)) or set(ids) != set(por_id):
        raise RegraDeNegocio(
            "A lista precisa ter todos os blocos planejados, uma vez cada. Atualize a página: "
            "outro usuário pode ter alterado os blocos.",
            409,
        )
    posicoes = sorted(b.ordem for b in planejados)
    antes = [b.numero for b in planejados]
    for posicao, bloco_id in zip(posicoes, ids):
        por_id[bloco_id].ordem = posicao
    _auditar(
        db,
        evento,
        usuario,
        "blocos_reordenados",
        {"antes": antes, "depois": [por_id[i].numero for i in ids]},
    )


# ------------------------------------------------------------------ distribuicao
def misturar_por_premio(itens: list[T], premio_de: Callable[[T], int]) -> list[T]:
    """Intercala os premios: cada um fica espalhado ao longo da sequencia e o
    mesmo premio nao sai duas vezes seguidas sempre que houver outro para
    colocar no meio.

    Deterministico (sem sorteio): a ordem dos premios nao interfere em quem
    ganha e o resultado pode ser conferido e ajustado no "Organizar".
    Ex.: 4 Air Fryers + 2 TVs + 1 bicicleta -> AF, TV, AF, BIC, AF, TV, AF.
    """
    grupos = list(_agrupar(itens, premio_de).values())
    total = len(itens)
    usados = [0] * len(grupos)

    def alvo(g: int) -> tuple[float, int]:
        # Espalhamento uniforme: a k-esima unidade de um premio com c unidades
        # "deveria" estar na posicao relativa (k + 0.5) / c da sequencia.
        return ((usados[g] + 0.5) / len(grupos[g]), g)

    # Um premio com mais da metade das unidades obriga a repetir: nesse caso
    # vale so o espalhamento uniforme (nao junta o premio maior no fim).
    evitar_repeticao = max(map(len, grupos), default=0) <= (total + 1) // 2

    def ainda_da_sem_repetir(ultimo: int) -> bool:
        """Sobra (comecando por um premio diferente de `ultimo`) sem repetir?"""
        restantes = [len(grupos[g]) - usados[g] for g in range(len(grupos))]
        r = sum(restantes)
        m = max(restantes, default=0)
        if m > (r + 1) // 2:
            return False
        # Com r impar e m no limite, o maior tem de vir primeiro: nao pode ser o ultimo.
        return not (r % 2 == 1 and m == (r + 1) // 2 and restantes[ultimo] == m)

    sequencia: list[T] = []
    ultimo = -1
    for _ in range(total):
        candidatos = sorted(
            (g for g in range(len(grupos)) if usados[g] < len(grupos[g])), key=alvo
        )
        escolhido = candidatos[0]
        if evitar_repeticao:
            for g in candidatos:
                if g == ultimo:
                    continue
                usados[g] += 1
                viavel = ainda_da_sem_repetir(g)
                usados[g] -= 1
                if viavel:
                    escolhido = g
                    break
        sequencia.append(grupos[escolhido][usados[escolhido]])
        usados[escolhido] += 1
        ultimo = escolhido
    return sequencia


def _agrupar(itens: list[T], premio_de: Callable[[T], int]) -> dict[int, list[T]]:
    grupos: dict[int, list[T]] = {}
    for item in itens:
        grupos.setdefault(premio_de(item), []).append(item)
    return grupos


def _distribuiveis(db: Session, evento: Event) -> tuple[dict[int, BlocoSorteio], list[PrizeUnit]]:
    """Blocos planejados (refeitos pela distribuicao) e as unidades que entram nela."""
    planejados = {
        b.id: b for b in blocos_do_evento(db, evento.id) if b.status == StatusBloco.PLANEJADO.value
    }
    distribuiveis = [
        unidade
        for unidade, _premio in unidades_do_evento(db, evento.id)
        if unidade.status == StatusUnidade.DISPONIVEL.value
        and (unidade.bloco_id is None or unidade.bloco_id in planejados)
    ]
    return planejados, distribuiveis


def previa_distribuicao(db: Session, evento: Event, capacidade: int) -> dict:
    """O que a distribuicao automatica faria, sem gravar nada."""
    if capacidade < 1:
        raise RegraDeNegocio("A capacidade do bloco deve ser de pelo menos 1 unidade.", 422)
    planejados, distribuiveis = _distribuiveis(db, evento)
    if not distribuiveis:
        raise RegraDeNegocio("Não há unidades disponíveis para distribuir.")
    # Os planejados sao apagados antes de numerar os novos (mesma conta de _proximo).
    restantes = [b for b in blocos_do_evento(db, evento.id) if b.id not in planejados]
    numero = max((b.numero for b in restantes), default=0) + 1
    blocos = []
    for inicio in range(0, len(distribuiveis), capacidade):
        quantidade = len(distribuiveis[inicio : inicio + capacidade])
        blocos.append({"numero": numero, "nome": nome_padrao(numero), "unidades": quantidade})
        numero += 1
    return {
        "capacidade": capacidade,
        "unidades": len(distribuiveis),
        "blocos": blocos,
        "planejados_refeitos": [b.nome for b in planejados.values()],
    }


def distribuir_automaticamente(
    db: Session, evento: Event, capacidade: int, usuario: User, misturar: bool = False
) -> list[BlocoSorteio]:
    """Reparte as unidades disponiveis em blocos de `capacidade`.

    Refaz apenas o que ainda nao comecou: blocos PLANEJADO sao recriados e as
    unidades disponiveis sem bloco entram na conta. Blocos iniciados ou
    finalizados, e unidades ja sorteadas, nao sao tocados. Ex.: 107 unidades
    com capacidade 25 geram blocos de 25, 25, 25, 25 e 7. Com `misturar`, os
    premios sao intercalados (ver misturar_por_premio) antes de repartir.
    """
    if capacidade < 1:
        raise RegraDeNegocio("A capacidade do bloco deve ser de pelo menos 1 unidade.", 422)

    planejados, distribuiveis = _distribuiveis(db, evento)
    if not distribuiveis:
        raise RegraDeNegocio("Não há unidades disponíveis para distribuir.")
    if misturar:
        distribuiveis = misturar_por_premio(distribuiveis, lambda u: u.prize_id)

    for unidade in distribuiveis:
        unidade.bloco_id = None
        unidade.ordem_bloco = None
    for bloco in planejados.values():
        db.delete(bloco)
    db.flush()

    evento.capacidade_bloco_padrao = capacidade
    numero, ordem = _proximo(db, evento.id)
    criados: list[BlocoSorteio] = []
    for inicio in range(0, len(distribuiveis), capacidade):
        lote = distribuiveis[inicio : inicio + capacidade]
        bloco = BlocoSorteio(
            event_id=evento.id,
            numero=numero,
            ordem=ordem,
            nome=nome_padrao(numero),
            capacidade=capacidade,
        )
        db.add(bloco)
        db.flush()
        for posicao, unidade in enumerate(lote, start=1):
            unidade.bloco_id = bloco.id
            unidade.ordem_bloco = posicao
        criados.append(bloco)
        numero += 1
        ordem += 1

    _auditar(
        db,
        evento,
        usuario,
        "blocos_distribuidos",
        {
            "capacidade": capacidade,
            "unidades": len(distribuiveis),
            "blocos_criados": [b.numero for b in criados],
            "blocos_planejados_refeitos": len(planejados),
            "premios_misturados": misturar,
        },
    )
    return criados


def versao_distribuicao(db: Session, evento_id: int) -> str:
    """Impressao digital da distribuicao: muda a qualquer movimentacao, criacao,
    exclusao, reordenacao ou sorteio. Usada para recusar o salvamento de quem
    organizou em cima de uma versao antiga (dois administradores ao mesmo tempo)."""
    partes = [
        f"b{b.id}:{b.status}:{b.capacidade}:{b.ordem}" for b in blocos_do_evento(db, evento_id)
    ] + [
        f"u{u.id}:{u.bloco_id}:{u.ordem_bloco}:{u.status}" for u, _p in unidades_do_evento(db, evento_id)
    ]
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:32]


def salvar_distribuicao(
    db: Session, evento: Event, itens: list[dict], usuario: User, versao: str | None = None
) -> None:
    """Aplica a distribuicao manual de forma atomica, validando tudo antes.

    `itens`: [{"bloco_id", "unidades": [ids na ordem], "capacidade"?}]. Unidades
    que estavam em um bloco informado e nao aparecem mais ficam sem bloco.
    Com `versao`, recusa (409) se a distribuicao mudou desde a leitura.
    """
    if versao is not None and versao != versao_distribuicao(db, evento.id):
        raise RegraDeNegocio(
            "Outro usuário alterou os blocos enquanto você organizava. Suas mudanças não foram "
            "salvas: recarregue a organização e refaça os ajustes.",
            409,
        )
    blocos = {b.id: b for b in blocos_do_evento(db, evento.id)}
    unidades = {u.id: u for u, _p in unidades_do_evento(db, evento.id)}

    destino: dict[int, tuple[int | None, int | None]] = {}
    informados: set[int] = set()
    for item in itens:
        bloco_id = item["bloco_id"]
        if bloco_id not in blocos:
            raise RegraDeNegocio(f"Bloco {bloco_id} não pertence a este evento.", 422)
        if bloco_id in informados:
            raise RegraDeNegocio(f"O bloco {blocos[bloco_id].nome} foi informado duas vezes.", 422)
        informados.add(bloco_id)
        for posicao, unidade_id in enumerate(item["unidades"], start=1):
            if unidade_id not in unidades:
                raise RegraDeNegocio(f"Unidade {unidade_id} não pertence a este evento.", 422)
            if unidade_id in destino:
                raise RegraDeNegocio(f"A unidade {unidade_id} aparece em mais de um lugar.", 422)
            destino[unidade_id] = (bloco_id, posicao)

    for unidade in unidades.values():
        if unidade.bloco_id in informados and unidade.id not in destino:
            destino[unidade.id] = (None, None)

    # ---- validacao (nada e gravado se qualquer regra falhar)
    for item in itens:
        bloco = blocos[item["bloco_id"]]
        if bloco.status in {StatusBloco.EM_ANDAMENTO.value, StatusBloco.PAUSADO.value}:
            atual = [u.id for u, _p in unidades_ordenadas_do_bloco(db, bloco)]
            if list(item["unidades"]) != atual:
                raise RegraDeNegocio(
                    f"O {bloco.nome} já foi iniciado; suas unidades não podem ser reorganizadas."
                )
        nova = item.get("capacidade")
        if nova and nova != bloco.capacidade and bloco.status == StatusBloco.FINALIZADO.value:
            raise RegraDeNegocio("Não é possível alterar a capacidade de um bloco finalizado.")

    movidas = 0
    for unidade_id, (bloco_destino, _ordem) in destino.items():
        unidade = unidades[unidade_id]
        if bloco_destino == unidade.bloco_id:
            continue
        movidas += 1
        if unidade.status != StatusUnidade.DISPONIVEL.value:
            raise RegraDeNegocio(
                "Unidades já sorteadas não podem mudar de bloco (o histórico do sorteio "
                "precisa continuar rastreável)."
            )
        origem = blocos.get(unidade.bloco_id) if unidade.bloco_id else None
        if origem is not None and origem.status not in {
            StatusBloco.PLANEJADO.value,
            StatusBloco.FINALIZADO.value,
        }:
            raise RegraDeNegocio(f"O {origem.nome} já foi iniciado; suas unidades não podem sair.")
        if bloco_destino is not None and blocos[bloco_destino].status != StatusBloco.PLANEJADO.value:
            raise RegraDeNegocio(
                f"Só blocos ainda não iniciados recebem unidades ({blocos[bloco_destino].nome})."
            )

    for item in itens:
        bloco = blocos[item["bloco_id"]]
        capacidade = item.get("capacidade") or bloco.capacidade
        if capacidade < 1:
            raise RegraDeNegocio("A capacidade do bloco deve ser de pelo menos 1 unidade.", 422)
        if len(item["unidades"]) > capacidade:
            raise RegraDeNegocio(
                f"O {bloco.nome} ficaria com {len(item['unidades'])} unidades, acima da "
                f"capacidade de {capacidade}. Aumente a capacidade para confirmar."
            )

    # ---- aplicacao
    capacidades_alteradas = {}
    for item in itens:
        bloco = blocos[item["bloco_id"]]
        nova = item.get("capacidade")
        if nova and nova != bloco.capacidade:
            capacidades_alteradas[bloco.numero] = [bloco.capacidade, nova]
            bloco.capacidade = nova
    for unidade_id, (bloco_destino, ordem) in destino.items():
        unidade = unidades[unidade_id]
        bloco_atual = blocos.get(unidade.bloco_id) if unidade.bloco_id else None
        # Bloco finalizado so libera unidades; a ordem das que ficam nao muda.
        if bloco_atual is not None and bloco_atual.status == StatusBloco.FINALIZADO.value and (
            bloco_destino == unidade.bloco_id
        ):
            continue
        unidade.bloco_id = bloco_destino
        unidade.ordem_bloco = ordem

    _auditar(
        db,
        evento,
        usuario,
        "distribuicao_salva",
        {
            "blocos": sorted(blocos[b].numero for b in informados),
            "unidades_movidas": movidas,
            "capacidades_alteradas": capacidades_alteradas,
        },
    )


def _plano_remanescentes(
    db: Session, evento: Event, nome: str | None, capacidade: int | None, misturar: bool = False
) -> tuple[list[tuple[PrizeUnit, Prize]], list[dict]]:
    """Unidades remanescentes e os blocos (numero, nome, quantidade) que as recebem.

    Respeita a capacidade (padrao: a do evento): 30 remanescentes com 25 por
    bloco viram dois blocos, de 25 e 5. Com `misturar`, os premios sao intercalados.
    """
    candidatas = _remanescentes(db, evento.id)
    if not candidatas:
        raise RegraDeNegocio("Não há unidades remanescentes para um novo bloco.")
    if misturar:
        candidatas = misturar_por_premio(candidatas, lambda par: par[1].id)
    tamanho = capacidade or evento.capacidade_bloco_padrao
    if tamanho < 1:
        raise RegraDeNegocio("A capacidade do bloco deve ser de pelo menos 1 unidade.", 422)
    base = (nome or "").strip() or NOME_REMANESCENTES
    lotes = [candidatas[i : i + tamanho] for i in range(0, len(candidatas), tamanho)]
    numero, _ordem = _proximo(db, evento.id)
    usados = {
        n.lower() for n in db.scalars(select(BlocoSorteio.nome).where(BlocoSorteio.event_id == evento.id))
    }
    plano = []
    sufixo = 1
    for indice, lote in enumerate(lotes):
        # Nome livre no evento: "Prêmios remanescentes", "... 2", "... 3"...
        candidato = base if len(lotes) == 1 and base.lower() not in usados else f"{base} {sufixo}"
        while candidato.lower() in usados:
            sufixo += 1
            candidato = f"{base} {sufixo}"
        usados.add(candidato.lower())
        sufixo += 1
        # Como antes: o bloco nasce cheio (capacidade = unidades do lote); a
        # capacidade configurada e o limite de cada lote.
        plano.append(
            {"numero": numero + indice, "nome": candidato, "unidades": len(lote), "capacidade": len(lote)}
        )
    return candidatas, plano


def previa_remanescentes(db: Session, evento: Event, nome: str | None, capacidade: int | None) -> dict:
    candidatas, plano = _plano_remanescentes(db, evento, nome, capacidade)
    return {
        "capacidade": capacidade or evento.capacidade_bloco_padrao,
        "unidades": len(candidatas),
        "blocos": [{k: p[k] for k in ("numero", "nome", "unidades")} for p in plano],
        "planejados_refeitos": [],
    }


def criar_bloco_remanescentes(
    db: Session,
    evento: Event,
    usuario: User,
    nome: str | None,
    capacidade: int | None = None,
    misturar: bool = False,
) -> list[BlocoSorteio]:
    candidatas, plano = _plano_remanescentes(db, evento, nome, capacidade, misturar)
    criados: list[BlocoSorteio] = []
    inicio = 0
    for item in plano:
        numero, ordem = _proximo(db, evento.id)
        bloco = BlocoSorteio(
            event_id=evento.id,
            numero=numero,
            ordem=ordem,
            nome=item["nome"],
            capacidade=item["capacidade"],
        )
        db.add(bloco)
        db.flush()
        for posicao, (unidade, _premio) in enumerate(candidatas[inicio : inicio + item["unidades"]], start=1):
            unidade.bloco_id = bloco.id
            unidade.ordem_bloco = posicao
        inicio += item["unidades"]
        criados.append(bloco)
        _auditar(
            db,
            evento,
            usuario,
            "bloco_remanescentes_criado",
            {
                "bloco_id": bloco.id,
                "numero": numero,
                "unidades": item["unidades"],
                "premios_misturados": misturar,
            },
        )
    return criados


# ------------------------------------------------------------------ ciclo de vida
def iniciar_bloco(db: Session, evento: Event, bloco: BlocoSorteio, usuario: User) -> BlocoSorteio:
    """Inicia ou retoma. Repetir o comando com o bloco ja em andamento nao faz nada."""
    if bloco.status == StatusBloco.EM_ANDAMENTO.value:
        return bloco
    if bloco.status == StatusBloco.FINALIZADO.value:
        raise RegraDeNegocio(f"O {bloco.nome} já foi finalizado.")
    ativo = bloco_em_andamento(db, evento.id)
    if ativo is not None:
        raise RegraDeNegocio(
            f"O {ativo.nome} já está em andamento. Pause-o ou finalize-o antes de iniciar outro."
        )
    if progresso_por_bloco(db, evento.id)[bloco.id].restantes == 0:
        raise RegraDeNegocio(f"O {bloco.nome} não tem unidades disponíveis para sortear.")

    retomada = bloco.status == StatusBloco.PAUSADO.value
    bloco.status = StatusBloco.EM_ANDAMENTO.value
    if bloco.iniciado_em is None:
        bloco.iniciado_em = utcnow()
    try:
        db.flush()
    except IntegrityError as exc:  # pragma: no cover - backstop do indice unico parcial
        db.rollback()
        raise RegraDeNegocio("Outro bloco foi iniciado ao mesmo tempo. Atualize a tela.") from exc
    _auditar(
        db,
        evento,
        usuario,
        "bloco_retomado" if retomada else "bloco_iniciado",
        {"bloco_id": bloco.id, "numero": bloco.numero},
    )
    return bloco


def pausar_bloco(db: Session, evento: Event, bloco: BlocoSorteio, usuario: User) -> BlocoSorteio:
    if bloco.status == StatusBloco.PAUSADO.value:
        return bloco
    if bloco.status != StatusBloco.EM_ANDAMENTO.value:
        raise RegraDeNegocio(f"O {bloco.nome} não está em andamento.")
    bloco.status = StatusBloco.PAUSADO.value
    _auditar(db, evento, usuario, "bloco_pausado", {"bloco_id": bloco.id, "numero": bloco.numero})
    return bloco


def finalizar_bloco(
    db: Session, evento: Event, bloco: BlocoSorteio, usuario: User, confirmar_pendentes: bool
) -> BlocoSorteio:
    if bloco.status == StatusBloco.FINALIZADO.value:
        return bloco
    if bloco.status not in {StatusBloco.EM_ANDAMENTO.value, StatusBloco.PAUSADO.value}:
        raise RegraDeNegocio(f"O {bloco.nome} ainda não foi iniciado.")
    pendentes = progresso_por_bloco(db, evento.id)[bloco.id].restantes
    if pendentes and not confirmar_pendentes:
        raise RegraDeNegocio(
            f"O {bloco.nome} ainda tem {pendentes} unidade(s) sem sorteio. Confirme para "
            "finalizar mesmo assim; elas poderao ir para um bloco de remanescentes."
        )
    bloco.status = StatusBloco.FINALIZADO.value
    bloco.finalizado_em = utcnow()
    bloco.finalizado_por_id = usuario.id
    _auditar(
        db,
        evento,
        usuario,
        "bloco_finalizado",
        {"bloco_id": bloco.id, "numero": bloco.numero, "pendentes": pendentes},
    )
    return bloco


def reabrir_bloco(db: Session, evento: Event, bloco: BlocoSorteio, usuario: User) -> BlocoSorteio:
    """Volta um bloco FINALIZADO que ainda tem premios sem sorteio para PAUSADO.

    Nada do que ja foi sorteado muda. Quem finalizou e quando ficam na
    auditoria (bloco_finalizado e bloco_reaberto); o bloco volta a ser
    conduzido normalmente (Continuar). Premios que ja foram para um bloco de
    remanescentes nao voltam: nesse caso nao ha o que reabrir.
    """
    if bloco.status == StatusBloco.PAUSADO.value:
        return bloco
    if bloco.status != StatusBloco.FINALIZADO.value:
        raise RegraDeNegocio(f"O {bloco.nome} não está finalizado.")
    restantes = progresso_por_bloco(db, evento.id)[bloco.id].restantes
    if restantes == 0:
        raise RegraDeNegocio(
            f"O {bloco.nome} não tem prêmios sem sorteio. Não há o que reabrir."
        )
    anterior = {
        "finalizado_em": bloco.finalizado_em.isoformat() if bloco.finalizado_em else None,
        "finalizado_por_id": bloco.finalizado_por_id,
    }
    bloco.status = StatusBloco.PAUSADO.value
    bloco.finalizado_em = None
    bloco.finalizado_por_id = None
    _auditar(
        db,
        evento,
        usuario,
        "bloco_reaberto",
        {"bloco_id": bloco.id, "numero": bloco.numero, "restantes": restantes, **anterior},
    )
    return bloco


# ------------------------------------------------------------------ resultados
def ganhadores_do_bloco(db: Session, bloco: BlocoSorteio) -> list[dict]:
    """Resultados validos do bloco na ordem dos sorteios (base do carrossel da Fase 7).

    Usa Draw.bloco_id (bloco em que o sorteio aconteceu), e nao a posicao atual
    da unidade. Sem matricula nem pulseira: o carrossel e exibido no telao.
    """
    evento = db.get(Event, bloco.event_id)
    linhas = db.execute(
        select(Draw, PrizeUnit, Prize, Participant)
        .join(PrizeUnit, Draw.prize_unit_id == PrizeUnit.id)
        .join(Prize, PrizeUnit.prize_id == Prize.id)
        .join(Participant, Draw.participant_id == Participant.id)
        .where(Draw.bloco_id == bloco.id, Draw.status == StatusSorteio.VALIDO.value)
        .order_by(Draw.rodada)
    ).all()
    return [
        {
            "rodada": sorteio.rodada,
            "premio_nome": premio.nome,
            "premio_imagem_url": premio.imagem_url,
            "premio_descricao": premio.descricao,
            "unidade_numero": unidade.numero,
            "ganhador_nome": participante.nome,
            "ganhador_setor": participante.setor,
            "ganhador_foto_url": participante.foto_url,
            # Numero do sorteio: identificacao publica, nao e dado pessoal.
            "ganhador_numero": participante.numero_sorteio,
            # So no modo faixa de matriculas (a matricula e o numero da sorte).
            "ganhador_matricula_da_sorte": matricula_da_sorte(evento, participante),
        }
        for sorteio, unidade, premio, participante in linhas
    ]
