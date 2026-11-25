from __future__ import annotations

import enum
import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from .database import Base
from .texto import normalizar_busca, normalizar_matricula


def utcnow() -> datetime:
    """Instante atual em UTC, sem tzinfo (o banco guarda sempre UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TratamentoAusente(str, enum.Enum):
    BLOQUEAR = "bloquear"          # ausente nem entra no sorteio
    RESORTEAR = "resortear"        # anula e sorteia de novo na hora
    MANTER_PENDENTE = "pendente"   # ganha, mas o premio fica pendente de retirada


class ModoSorteio(str, enum.Enum):
    # Todos os elegiveis concorrem; o telao mostra o numero da sorte (padrao).
    NUMERO_SORTE = "numero_sorte"
    # So concorrem os elegiveis com matricula numerica dentro da faixa do evento.
    FAIXA_MATRICULA = "faixa_matricula"


class StatusUnidade(str, enum.Enum):
    DISPONIVEL = "disponivel"
    SORTEADO = "sorteado"
    ENTREGUE = "entregue"
    # Sobra de um premio excluido pelo admin que ja tinha sorteio anulado: a
    # unidade fica so pelo historico e nunca mais e sorteada.
    REMOVIDO = "removido"


class StatusSorteio(str, enum.Enum):
    VALIDO = "valido"
    ANULADO = "anulado"


class EstadoTelao(str, enum.Enum):
    AGUARDANDO = "aguardando"
    PREMIO = "premio"
    SORTEANDO = "sorteando"
    RESULTADO = "resultado"
    ENCERRAMENTO = "encerramento"
    # Apresentacao dos ganhadores de um bloco (Fase 7).
    CARROSSEL_GANHADORES = "carrossel_ganhadores"


class Papel(str, enum.Enum):
    """Perfil de acesso. As permissoes de cada papel ficam em app/permissoes.py.

    Migracao 0007: a antiga RECEPCAO (entrega de premios) virou ORGANIZADOR e o
    antigo CHECKIN virou a nova RECEPCAO (check-in e consulta do numero).
    Migracao 0010: ORGANIZADOR passou a ser o "Organizador - RH" (configura o
    evento) e as contas que existiam nele, de entregas, viraram ENTREGAS.
    SORTEIO e o perfil "Sorteador".
    """

    ADMIN = "ADMIN"
    SORTEIO = "SORTEIO"
    ORGANIZADOR = "ORGANIZADOR"
    RECEPCAO = "RECEPCAO"
    ENTREGAS = "ENTREGAS"
    COLABORADOR = "COLABORADOR"


PAPEIS_SQL = ", ".join(f"'{p.value}'" for p in Papel)


class StatusBloco(str, enum.Enum):
    PLANEJADO = "PLANEJADO"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    PAUSADO = "PAUSADO"
    FINALIZADO = "FINALIZADO"


class TipoNotificacao(str, enum.Enum):
    PREMIO_GANHO = "PREMIO_GANHO"
    SORTEIO_ANULADO = "SORTEIO_ANULADO"


class User(Base):
    """Conta de autenticacao. Nao e o cadastro do participante (ver Participant.usuario_id)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"papel IN ({PAPEIS_SQL})", name="ck_users_papel_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    senha_hash: Mapped[str] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Menor privilegio por padrao: contas novas nascem COLABORADOR.
    papel: Mapped[str] = mapped_column(
        String(20), default=Papel.COLABORADOR.value, server_default=Papel.COLABORADOR.value
    )
    # Area da pessoa na empresa (TI, RH...). So informativo: NUNCA da permissao.
    setor: Mapped[str] = mapped_column(String(80), default="", server_default="")
    # Organizador - RH autorizado pelo admin a operar sorteios e o telao.
    pode_sortear: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Sessao: incrementar invalida todos os tokens ja emitidos para a conta
    # (desativacao, troca de perfil, redefinicao de senha, "encerrar sessoes").
    sessao_versao: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    ultimo_acesso_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Protecao contra tentativas repetidas de login.
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Senha temporaria (criacao ou redefinicao pelo admin) precisa ser trocada.
    deve_trocar_senha: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    senha_alterada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("capacidade_bloco_padrao >= 1", name="ck_events_capacidade_bloco_positiva"),
        CheckConstraint("carrossel_segundos >= 1", name="ck_events_carrossel_minimo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    empresa_nome: Mapped[str] = mapped_column(String(200), default="")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    cor_fundo: Mapped[str] = mapped_column(String(20), default="#0B1F3A")
    cor_primaria: Mapped[str] = mapped_column(String(20), default="#D4AF37")
    cor_texto: Mapped[str] = mapped_column(String(20), default="#F8FAFC")
    cor_destaque: Mapped[str] = mapped_column(String(20), default="#1D4ED8")

    mensagem_boas_vindas: Mapped[str] = mapped_column(Text, default="Bem-vindos!")
    mensagem_encerramento: Mapped[str] = mapped_column(Text, default="Obrigado por participar!")
    regras_participacao: Mapped[str] = mapped_column(Text, default="")

    som_ativado: Mapped[bool] = mapped_column(Boolean, default=True)
    reduzir_animacoes: Mapped[bool] = mapped_column(Boolean, default=False)
    duracao_animacao_ms: Mapped[int] = mapped_column(Integer, default=6000)
    fuso_horario: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    # Unidades por bloco na distribuicao automatica.
    capacidade_bloco_padrao: Mapped[int] = mapped_column(Integer, default=25, server_default="25")

    # Recepcao sem login (/recepcao: check-in pela matricula e consulta do
    # numero). Desligada por padrao: o admin ou o organizador abre no dia.
    recepcao_publica_ativa: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # Autocadastro pelo celular: desligado por padrao (o admin decide quando abrir).
    autocadastro_ativo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Periodo opcional do cadastro pelo QR Code (UTC). NULL = sem limite.
    autocadastro_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    autocadastro_fim: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Legado (cadastro antigo com pulseira). O Portal do Colaborador nunca
    # confirma presenca: presenca e pulseira ficam com o check-in da Recepcao.
    autocadastro_confirma_presenca: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    # Tempo de cada ganhador no carrossel do telao. Nunca menos de 5 s.
    carrossel_segundos: Mapped[int] = mapped_column(Integer, default=6, server_default="6")

    telao_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # --- Regras de elegibilidade ---
    permite_multiplas_vitorias: Mapped[bool] = mapped_column(Boolean, default=False)
    exige_presenca: Mapped[bool] = mapped_column(Boolean, default=True)
    tratamento_ausente: Mapped[str] = mapped_column(
        String(20), default=TratamentoAusente.RESORTEAR.value
    )
    ausente_pode_concorrer_novamente: Mapped[bool] = mapped_column(Boolean, default=False)
    # Modo do sorteio (ver ModoSorteio). A faixa so vale no modo faixa_matricula
    # e e comparada com a matricula sem zeros a esquerda ("00026" = 26).
    modo_sorteio: Mapped[str] = mapped_column(
        String(20), default=ModoSorteio.NUMERO_SORTE.value, server_default=ModoSorteio.NUMERO_SORTE.value
    )
    matricula_faixa_inicio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matricula_faixa_fim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regras_confirmadas_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Marca eventos de demonstracao, para que nunca se misturem aos reais.
    demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    participantes: Mapped[list["Participant"]] = relationship(
        back_populates="evento", cascade="all, delete-orphan"
    )
    premios: Mapped[list["Prize"]] = relationship(
        back_populates="evento", cascade="all, delete-orphan", order_by="Prize.ordem"
    )


class Participant(Base):
    """Cadastro do participante em um evento.

    A conta de acesso (User) e separada: uma pessoa importada por planilha pode
    ativar a conta depois, e o vinculo e feito por `usuario_id`, sem duplicar o
    participante. Um usuario so pode estar vinculado a um participante por evento.
    """

    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("event_id", "matricula", name="uq_participante_matricula_evento"),
        # Indices unicos (e nao constraints) porque o SQLite cria indices em
        # tabelas existentes sem recria-las. Varios NULL sao permitidos.
        Index("uq_participante_pulseira_evento", "event_id", "pulseira", unique=True),
        Index("uq_participante_usuario_evento", "event_id", "usuario_id", unique=True),
        Index("uq_participante_numero_evento", "event_id", "numero_sorteio", unique=True),
        # CPF (codigo protegido) nunca se repete no evento. Varios NULL sao permitidos.
        Index("uq_participante_cpf_evento", "event_id", "cpf_hash", unique=True),
        Index("ix_participante_matricula_normalizada", "event_id", "matricula_normalizada"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    # Nome sem acentos e em minusculas, para a pesquisa (ver _manter_nome_busca).
    nome_busca: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # String para preservar zeros a esquerda (ex.: "00123").
    matricula: Mapped[str] = mapped_column(String(60))
    # "00026", "026" e "26" -> "26" (ver texto.normalizar_matricula). Mantida
    # pelo ORM em toda gravacao (_manter_nome_busca).
    matricula_normalizada: Mapped[str] = mapped_column(String(60), default="", server_default="")
    # Identificacao no Portal do Colaborador (LGPD): o CPF e a data de
    # nascimento NUNCA sao gravados. Ficam so codigos HMAC com chave secreta
    # (services/identificacao.py): um de nascimento + 5 primeiros digitos do
    # CPF (para conferir a identidade) e um do CPF completo (para impedir CPF
    # repetido). Sem a chave, os codigos nao revelam nada.
    identificacao_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cpf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    setor: Mapped[str] = mapped_column(String(160), default="")
    foto_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Texto (nao inteiro) para preservar zeros e prefixos impressos na pulseira.
    pulseira: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Numero do sorteio: aleatorio, unico no evento, atribuido automaticamente
    # em toda inclusao (ver _atribuir_numeros_sorteio). Serve para identificar
    # a pessoa na recepcao; NAO participa da escolha do ganhador.
    numero_sorteio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    presente: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    participando: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    motivo_participacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    evento: Mapped[Event] = relationship(back_populates="participantes")

    @property
    def tem_identificacao(self) -> bool:
        """Tem CPF e nascimento importados (pode fazer o cadastro pelo QR Code)."""
        return self.identificacao_hash is not None


class Prize(Base):
    __tablename__ = "prizes"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    nome_busca: Mapped[str] = mapped_column(String(200), default="", server_default="")
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    imagem_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantidade: Mapped[int] = mapped_column(Integer, default=1)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Preenchido quando o admin exclui um premio que ja teve sorteio: some da
    # tela de Premios, mas os resultados continuam apontando para ele.
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    evento: Mapped[Event] = relationship(back_populates="premios")
    unidades: Mapped[list["PrizeUnit"]] = relationship(
        back_populates="premio", cascade="all, delete-orphan", order_by="PrizeUnit.numero"
    )


class PrizeUnit(Base):
    """Uma unidade sorteavel de um premio (premio com quantidade 3 tem 3 unidades)."""

    __tablename__ = "prize_units"
    __table_args__ = (UniqueConstraint("prize_id", "numero", name="uq_unidade_numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prize_id: Mapped[int] = mapped_column(ForeignKey("prizes.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=StatusUnidade.DISPONIVEL.value)
    # NULL = unidade ainda nao distribuida em bloco.
    bloco_id: Mapped[int | None] = mapped_column(
        ForeignKey("blocos_sorteio.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Posicao dentro do bloco: define o "premio atual" na execucao.
    ordem_bloco: Mapped[int | None] = mapped_column(Integer, nullable=True)

    premio: Mapped[Prize] = relationship(back_populates="unidades")
    bloco: Mapped["BlocoSorteio | None"] = relationship(back_populates="unidades")


class Draw(Base):
    """Resultado de uma rodada. Nunca e apagado: anulacao vira status + motivo."""

    __tablename__ = "draws"
    __table_args__ = (
        # Garante no banco que uma unidade nunca tenha dois resultados validos.
        Index(
            "uq_draw_unidade_valida",
            "prize_unit_id",
            unique=True,
            sqlite_where=text("status = 'valido'"),
            postgresql_where=text("status = 'valido'"),
        ),
        Index("uq_draw_idempotencia", "idempotency_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    prize_unit_id: Mapped[int] = mapped_column(ForeignKey("prize_units.id", ondelete="CASCADE"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="RESTRICT"))

    rodada: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=StatusSorteio.VALIDO.value, index=True)

    idempotency_key: Mapped[str] = mapped_column(String(80))

    # Conferencia posterior: quem estava elegivel no instante do sorteio.
    elegiveis_ids: Mapped[list] = mapped_column(JSON, default=list)
    elegiveis_total: Mapped[int] = mapped_column(Integer, default=0)
    # Semente/diagnostico do sorteio (indice escolhido dentro da lista ordenada).
    indice_sorteado: Mapped[int] = mapped_column(Integer, default=0)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    criado_por_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    entregue: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entregue_por_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    anulado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    anulado_por_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    motivo_anulacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "ausencia" | "desistencia" | "erro_operacional" | "outro"
    tipo_anulacao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    estorno_entrega: Mapped[bool] = mapped_column(Boolean, default=False)

    # Encadeia o novo sorteio ao resultado anulado que o originou.
    draw_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("draws.id"), nullable=True)

    # Bloco em que o sorteio aconteceu, gravado no instante do sorteio. Nao se
    # le de prize_units.bloco_id porque uma unidade anulada pode ser
    # redistribuida para outro bloco, e o historico nao pode mudar com isso.
    # Sem ondelete: um bloco com resultados registrados nao pode ser apagado.
    bloco_id: Mapped[int | None] = mapped_column(
        ForeignKey("blocos_sorteio.id"), nullable=True, index=True
    )

    unidade: Mapped[PrizeUnit] = relationship()
    participante: Mapped[Participant] = relationship()
    criado_por: Mapped[User] = relationship(foreign_keys=[criado_por_id])
    entregue_por: Mapped[User | None] = relationship(foreign_keys=[entregue_por_id])
    anulado_por: Mapped[User | None] = relationship(foreign_keys=[anulado_por_id])


class BlocoSorteio(Base):
    """Grupo de unidades de premio sorteadas em sequencia (ex.: 25 por bloco)."""

    __tablename__ = "blocos_sorteio"
    __table_args__ = (
        UniqueConstraint("event_id", "numero", name="uq_bloco_numero_evento"),
        Index("ix_blocos_sorteio_event_ordem", "event_id", "ordem"),
        CheckConstraint("capacidade >= 1", name="ck_bloco_capacidade_positiva"),
        CheckConstraint(
            "status IN ('PLANEJADO', 'EM_ANDAMENTO', 'PAUSADO', 'FINALIZADO')",
            name="ck_bloco_status_valido",
        ),
        # No maximo um bloco em andamento por evento: dois operadores nao
        # conseguem iniciar blocos diferentes ao mesmo tempo.
        Index(
            "uq_bloco_em_andamento_evento",
            "event_id",
            unique=True,
            sqlite_where=text("status = 'EM_ANDAMENTO'"),
            postgresql_where=text("status = 'EM_ANDAMENTO'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    capacidade: Mapped[int] = mapped_column(Integer, default=25)
    status: Mapped[str] = mapped_column(
        String(20), default=StatusBloco.PLANEJADO.value, index=True
    )
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finalizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Bloco excluido pelo admin que ja tinha sorteios: some da gestao de blocos,
    # mas continua existindo para o historico (Draw.bloco_id aponta para ele).
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Ao excluir, o numero sai do caminho (fica negativo, nunca exibido) para os
    # blocos ativos voltarem a ser 01, 02...; o historico mostra este numero.
    numero_original: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def numero_exibicao(self) -> int:
        """Numero que aparece nas telas (o original, se o bloco foi excluido)."""
        return self.numero_original if self.numero_original is not None else self.numero

    @property
    def nome_exibicao(self) -> str:
        return f"{self.nome} (excluído)" if self.excluido_em is not None else self.nome

    unidades: Mapped[list[PrizeUnit]] = relationship(back_populates="bloco")
    finalizado_por: Mapped[User | None] = relationship()


class Notificacao(Base):
    """Aviso individual e persistente (ex.: premio ganho, resultado anulado).

    `usuario_id` pode ser NULL: o ganhador talvez ainda nao tenha ativado a
    conta. A notificacao fica ligada ao participante e aparece quando ele ativar.
    """

    __tablename__ = "notificacoes"
    __table_args__ = (
        # Impede notificacoes duplicadas em retentativas ou reconexoes.
        UniqueConstraint("draw_id", "tipo", name="uq_notificacao_sorteio_tipo"),
        Index("ix_notificacoes_usuario_lida_criada", "usuario_id", "lida", "criada_em"),
        Index("ix_notificacoes_participante_criada", "participant_id", "criada_em"),
        Index("ix_notificacoes_evento_criada", "event_id", "criada_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE")
    )
    draw_id: Mapped[int | None] = mapped_column(
        ForeignKey("draws.id", ondelete="CASCADE"), nullable=True
    )
    prize_id: Mapped[int | None] = mapped_column(
        ForeignKey("prizes.id", ondelete="SET NULL"), nullable=True
    )
    tipo: Mapped[str] = mapped_column(String(40))
    titulo: Mapped[str] = mapped_column(String(200))
    mensagem: Mapped[str] = mapped_column(Text)
    lida: Mapped[bool] = mapped_column(Boolean, default=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A notificacao de premio so aparece quando o telao revela o ganhador
    # (fim da animacao): o celular nao pode estragar a surpresa do palco.
    # NULL = visivel desde a criacao.
    disponivel_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Push no celular: marcado ANTES do envio (com UPDATE condicional), entao
    # cada notificacao gera no maximo um push, mesmo com o telao reapresentando
    # o resultado ou o servidor reiniciando.
    push_enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InscricaoPush(Base):
    """Aparelho que aceitou receber notificacoes push (Web Push / PWA).

    Uma inscricao pertence a uma conta. O endpoint e unico: se o aparelho
    passa a ser usado por outra conta, a inscricao muda de dono.
    """

    __tablename__ = "push_inscricoes"
    __table_args__ = (Index("ix_push_inscricoes_usuario", "usuario_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ultimo_envio_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    falhas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class RuleChange(Base):
    __tablename__ = "rule_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    campo: Mapped[str] = mapped_column(String(80))
    valor_anterior: Mapped[str] = mapped_column(String(200))
    valor_novo: Mapped[str] = mapped_column(String(200))
    apos_primeiro_sorteio: Mapped[bool] = mapped_column(Boolean, default=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    usuario: Mapped[User] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acao: Mapped[str] = mapped_column(String(80), index=True)
    detalhes: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    usuario: Mapped[User | None] = relationship()


class DisplayState(Base):
    """Estado atual do telao. Persistido para que F5/reconexao recuperem a tela."""

    __tablename__ = "display_states"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    estado: Mapped[str] = mapped_column(String(20), default=EstadoTelao.AGUARDANDO.value)
    prize_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("prize_units.id", ondelete="SET NULL"), nullable=True
    )
    draw_id: Mapped[int | None] = mapped_column(
        ForeignKey("draws.id", ondelete="SET NULL"), nullable=True
    )
    # Instante em que a animacao deve revelar o resultado (UTC).
    revelar_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Nomes embaralhados usados na animacao (apenas elegiveis, sem matricula).
    nomes_animacao: Mapped[list] = mapped_column(JSON, default=list)
    # Carrossel dos ganhadores: estado oficial no servidor. O slide atual e
    # carrossel_indice + segundos desde carrossel_desde / duracao; com
    # carrossel_desde NULL a apresentacao esta pausada em carrossel_indice.
    carrossel_bloco_id: Mapped[int | None] = mapped_column(
        ForeignKey("blocos_sorteio.id", ondelete="SET NULL"), nullable=True
    )
    carrossel_indice: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    carrossel_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    carrossel_duracao_s: Mapped[int] = mapped_column(Integer, default=6, server_default="6")
    versao: Mapped[int] = mapped_column(Integer, default=0)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


def faixa_numeros(total: int) -> tuple[int, int]:
    """Menor faixa de numeros com o mesmo total de digitos que fica no maximo
    meio ocupada: 1000-9999 ate 4.500 pessoas, 10000-99999 ate 45.000..."""
    digitos = 4
    while total > 9 * 10 ** (digitos - 1) // 2:
        digitos += 1
    return 10 ** (digitos - 1), 10**digitos - 1


@event.listens_for(Session, "before_flush")
def _atribuir_numeros_sorteio(session, flush_context, instances) -> None:  # noqa: ANN001
    """Todo participante novo recebe um numero aleatorio unico no evento.

    Roda em qualquer caminho de inclusao (importacao, cadastro manual, demo,
    testes). Como toda escrita usa BEGIN IMMEDIATE, a leitura dos numeros ja
    usados fica consistente ate o commit; o indice unico e a ultima defesa.
    """
    novos = [o for o in session.new if isinstance(o, Participant) and o.numero_sorteio is None]
    if not novos:
        return
    grupos: dict[tuple, list[Participant]] = {}
    for p in novos:
        if p.event_id is not None:
            chave: tuple = ("id", p.event_id)
        elif p.evento is not None and p.evento.id is not None:
            chave = ("id", p.evento.id)
        else:  # evento novo, ainda sem id: nenhum numero usado no banco
            chave = ("obj", id(p.evento))
        grupos.setdefault(chave, []).append(p)

    for (tipo, valor), lista in grupos.items():
        usados: set[int] = set()
        if tipo == "id":
            with session.no_autoflush:
                usados = set(
                    session.scalars(
                        select(Participant.numero_sorteio).where(
                            Participant.event_id == valor, Participant.numero_sorteio.is_not(None)
                        )
                    )
                )
        usados |= {
            o.numero_sorteio
            for o in session.new
            if isinstance(o, Participant) and o.numero_sorteio is not None
            and (o.event_id == valor if tipo == "id" else id(o.evento) == valor)
        }
        menor, maior = faixa_numeros(len(usados) + len(lista))
        for p in lista:
            numero = menor + secrets.randbelow(maior - menor + 1)
            while numero in usados:
                numero = menor + secrets.randbelow(maior - menor + 1)
            usados.add(numero)
            p.numero_sorteio = numero


@event.listens_for(Participant, "before_insert")
@event.listens_for(Participant, "before_update")
@event.listens_for(Prize, "before_insert")
@event.listens_for(Prize, "before_update")
def _manter_nome_busca(mapper, connection, alvo) -> None:  # noqa: ANN001
    """Toda gravacao pelo ORM recalcula a forma de busca do nome (e da matricula)."""
    alvo.nome_busca = normalizar_busca(alvo.nome)
    if isinstance(alvo, Participant):
        alvo.matricula_normalizada = normalizar_matricula(alvo.matricula)
