from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

PULSEIRA_RE = re.compile(r"^[A-Z0-9-]{1,40}$")


def normalizar_pulseira(valor: str | None) -> str | None:
    """Texto em maiusculas, sem espacos; vazio vira None. Preserva zeros a esquerda."""
    if valor is None:
        return None
    texto = valor.strip().upper()
    if not texto:
        return None
    if not PULSEIRA_RE.match(texto):
        raise ValueError("pulseira deve ter ate 40 caracteres: letras, numeros ou hifen")
    return texto


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    usuario: str
    senha: str


class UsuarioOut(ORMModel):
    id: int
    usuario: str
    nome: str
    papel: str
    deve_trocar_senha: bool = False
    # Para a interface adaptar menus. Quem decide o acesso e sempre o backend.
    permissoes: list[str] = []
    # A conta esta ligada a um cadastro de participante (tem Cartao da Sorte).
    tem_cartao: bool = False


class TrocarSenhaIn(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=128)
    senha_nova: str = Field(min_length=1, max_length=128)


# ---------------------------------------------------------------- usuarios (admin)
USUARIO_RE = re.compile(r"^[a-z0-9._-]{3,80}$")


class UsuarioAdminOut(ORMModel):
    id: int
    usuario: str
    nome: str
    papel: str
    setor: str = ""
    pode_sortear: bool = False
    ativo: bool
    criado_em: datetime
    ultimo_acesso_em: datetime | None
    bloqueado_ate: datetime | None
    deve_trocar_senha: bool


class UsuarioNovoIn(BaseModel):
    usuario: str = Field(min_length=3, max_length=80)
    nome: str = Field(min_length=1, max_length=160)
    papel: str
    setor: str = Field(default="", max_length=80)
    pode_sortear: bool = False

    @field_validator("usuario")
    @classmethod
    def _usuario(cls, v: str) -> str:
        v = v.strip().lower()
        if not USUARIO_RE.match(v):
            raise ValueError("use de 3 a 80 caracteres: letras minusculas, numeros, ponto, hifen ou sublinhado")
        return v


class UsuarioEdicaoIn(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=160)
    papel: str | None = None
    ativo: bool | None = None
    setor: str | None = Field(default=None, max_length=80)
    pode_sortear: bool | None = None


class UsuarioEdicaoOut(UsuarioAdminOut):
    # So quando a edicao promove um colaborador a perfil da equipe: a senha
    # fraca (5 digitos do CPF) e trocada por uma temporaria, exibida uma vez.
    senha_temporaria: str | None = None


class SenhaTemporariaOut(BaseModel):
    usuario: UsuarioAdminOut
    # Exibida uma unica vez; o sistema guarda apenas o hash.
    senha_temporaria: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


# ---------------------------------------------------------------- recepcao (publica, sem login)
class EventoRecepcaoOut(ORMModel):
    id: int
    nome: str
    empresa_nome: str
    logo_url: str | None
    demo: bool


class PremioConsultaOut(BaseModel):
    premio_nome: str
    bloco_numero: int | None
    entregue: bool


class LocalizarMatriculaIn(BaseModel):
    matricula: str = Field(min_length=1, max_length=60)


class CheckinIn(BaseModel):
    participante_id: int


class AtendidoOut(BaseModel):
    """O minimo para a recepcao: sem foto, setor, pulseira ou dados de conta.

    `premios`: resultados validos ja revelados no telao.
    """

    id: int
    matricula: str
    nome: str
    numero_sorteio: int | None
    # Modo faixa de matriculas: a matricula e o numero da sorte exibido.
    matricula_da_sorte: str | None = None
    presente: bool
    participando: bool
    premios: list[PremioConsultaOut] = []


class CheckinOut(AtendidoOut):
    ja_estava_presente: bool


# ---------------------------------------------------------------- evento
class EventoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    empresa_nome: str = ""
    demo: bool = False


class ExcluirEventoIn(BaseModel):
    # Nome do evento digitado pelo admin, como confirmacao.
    nome_confirmacao: str = Field(min_length=1, max_length=200)


class EventoConfigIn(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    empresa_nome: str | None = None
    logo_url: str | None = None
    cor_fundo: str | None = None
    cor_primaria: str | None = None
    cor_texto: str | None = None
    cor_destaque: str | None = None
    mensagem_boas_vindas: str | None = None
    mensagem_encerramento: str | None = None
    regras_participacao: str | None = None
    som_ativado: bool | None = None
    reduzir_animacoes: bool | None = None
    duracao_animacao_ms: int | None = Field(default=None, ge=1000, le=30000)
    fuso_horario: str | None = None
    recepcao_publica_ativa: bool | None = None
    autocadastro_ativo: bool | None = None
    autocadastro_confirma_presenca: bool | None = None
    # Periodo do cadastro pelo QR Code. Enviar null remove o limite.
    autocadastro_inicio: datetime | None = None
    autocadastro_fim: datetime | None = None
    # Carrossel: cada ganhador fica no telao por pelo menos 5 segundos.
    carrossel_segundos: int | None = Field(default=None, ge=5, le=60)

    @field_validator("autocadastro_inicio", "autocadastro_fim")
    @classmethod
    def _utc_sem_fuso(cls, v: datetime | None) -> datetime | None:
        # O banco guarda sempre UTC sem tzinfo.
        if v is not None and v.tzinfo is not None:
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class RegrasIn(BaseModel):
    permite_multiplas_vitorias: bool | None = None
    exige_presenca: bool | None = None
    tratamento_ausente: str | None = None
    ausente_pode_concorrer_novamente: bool | None = None
    # Modo do sorteio e faixa de matriculas (a faixa e conferida junto com o
    # modo no router: o modo faixa_matricula exige inicio <= fim).
    modo_sorteio: str | None = None
    matricula_faixa_inicio: int | None = Field(default=None, ge=0, le=999_999_999)
    matricula_faixa_fim: int | None = Field(default=None, ge=0, le=999_999_999)

    @field_validator("tratamento_ausente")
    @classmethod
    def _valida(cls, v: str | None) -> str | None:
        if v is not None and v not in {"bloquear", "resortear", "pendente"}:
            raise ValueError("tratamento_ausente invalido")
        return v

    @field_validator("modo_sorteio")
    @classmethod
    def _valida_modo(cls, v: str | None) -> str | None:
        if v is not None and v not in {"numero_sorte", "faixa_matricula"}:
            raise ValueError("modo_sorteio invalido")
        return v


class RegrasOut(ORMModel):
    permite_multiplas_vitorias: bool
    exige_presenca: bool
    tratamento_ausente: str
    ausente_pode_concorrer_novamente: bool
    modo_sorteio: str = "numero_sorte"
    matricula_faixa_inicio: int | None = None
    matricula_faixa_fim: int | None = None
    regras_confirmadas_em: datetime | None


class FaixaMatriculaOut(BaseModel):
    """Previa da faixa de matriculas: quem fica dentro e quem fica de fora."""

    inicio: int | None
    fim: int | None
    participantes_ativos: int
    dentro_da_faixa: int
    fora_da_faixa: int
    matricula_nao_numerica: int
    menor_matricula: int | None
    maior_matricula: int | None


class EventoOut(ORMModel):
    id: int
    nome: str
    empresa_nome: str
    logo_url: str | None
    cor_fundo: str
    cor_primaria: str
    cor_texto: str
    cor_destaque: str
    mensagem_boas_vindas: str
    mensagem_encerramento: str
    regras_participacao: str
    som_ativado: bool
    reduzir_animacoes: bool
    duracao_animacao_ms: int
    fuso_horario: str
    telao_token: str
    permite_multiplas_vitorias: bool
    exige_presenca: bool
    tratamento_ausente: str
    ausente_pode_concorrer_novamente: bool
    modo_sorteio: str = "numero_sorte"
    matricula_faixa_inicio: int | None = None
    matricula_faixa_fim: int | None = None
    regras_confirmadas_em: datetime | None
    capacidade_bloco_padrao: int = 25
    recepcao_publica_ativa: bool = False
    autocadastro_ativo: bool = False
    autocadastro_confirma_presenca: bool = True
    autocadastro_inicio: datetime | None = None
    autocadastro_fim: datetime | None = None
    carrossel_segundos: int = 6
    demo: bool
    criado_em: datetime


class MudancaRegraOut(BaseModel):
    id: int
    campo: str
    valor_anterior: str
    valor_novo: str
    apos_primeiro_sorteio: bool
    usuario_nome: str
    criado_em: datetime


# ---------------------------------------------------------------- participantes
class ParticipanteIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    matricula: str = Field(min_length=1, max_length=60)
    setor: str = ""
    foto_url: str | None = None
    presente: bool = False
    pulseira: str | None = None

    @field_validator("nome", "matricula", "setor")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()

    @field_validator("pulseira")
    @classmethod
    def _pulseira(cls, v: str | None) -> str | None:
        return normalizar_pulseira(v)


class ParticipanteUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    matricula: str | None = Field(default=None, min_length=1, max_length=60)
    setor: str | None = None
    foto_url: str | None = None
    # Enviar null remove a pulseira; omitir o campo mantem a atual.
    pulseira: str | None = None

    @field_validator("pulseira")
    @classmethod
    def _pulseira(cls, v: str | None) -> str | None:
        return normalizar_pulseira(v)


class PresencaIn(BaseModel):
    presente: bool


class ParticipacaoIn(BaseModel):
    participando: bool
    motivo: str = Field(min_length=3, max_length=500)


class ParticipanteOut(ORMModel):
    id: int
    nome: str
    matricula: str
    setor: str
    foto_url: str | None
    pulseira: str | None = None
    numero_sorteio: int | None = None
    presente: bool
    participando: bool
    motivo_participacao: str | None
    ja_ganhou: bool = False
    # Tem CPF e nascimento importados (pode se cadastrar pelo QR Code).
    tem_identificacao: bool = False
    tem_conta: bool = False


class LinhaImportacao(BaseModel):
    linha: int
    nome: str
    matricula: str
    setor: str
    erros: list[str] = []
    duplicada_na_planilha: bool = False
    ja_existe_no_evento: bool = False
    # CPF e nascimento validos na linha (o CPF e a data nunca voltam ao navegador).
    tem_identificacao: bool = False
    # Codigos HMAC calculados no servidor (ver services/identificacao.py).
    codigo_identificacao: str | None = None
    codigo_cpf: str | None = None


class PreviaImportacao(BaseModel):
    total_linhas: int
    validas: int
    com_erro: int
    duplicadas: int
    com_identificacao: int = 0
    linhas: list[LinhaImportacao]


CODIGO_RE = re.compile(r"^[0-9a-f]{64}$")


class LinhaConfirmacaoIn(ParticipanteIn):
    codigo_identificacao: str | None = None
    codigo_cpf: str | None = None

    @field_validator("codigo_identificacao", "codigo_cpf")
    @classmethod
    def _codigo(cls, v: str | None) -> str | None:
        if v is not None and not CODIGO_RE.match(v):
            raise ValueError("codigo de identificacao invalido")
        return v


class ConfirmarImportacaoIn(BaseModel):
    linhas: list[LinhaConfirmacaoIn]
    # O que fazer com matriculas que ja existem no evento.
    atualizar_existentes: bool = False
    # Completar/atualizar CPF e nascimento (codigos) de quem ja existe no evento.
    atualizar_identificacao: bool = False


# Frase que precisa ser digitada para zerar a lista de participantes.
FRASE_ZERAR_PARTICIPANTES = "ZERAR"


class ZerarParticipantesIn(BaseModel):
    confirmacao: str


class ParticipanteMantidoOut(BaseModel):
    nome: str
    matricula: str
    motivo: str


class ZerarParticipantesOut(BaseModel):
    removidos: int
    mantidos: list[ParticipanteMantidoOut]
    backup: str | None


# ---------------------------------------------------------------- premios
class PremioIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = None
    imagem_url: str | None = None
    quantidade: int = Field(default=1, ge=1, le=500)
    ordem: int = 0


class LinhaImportPremio(BaseModel):
    linha: int
    nome: str
    descricao: str | None = None
    quantidade: int
    erros: list[str]
    ja_existe: bool


class PreviaImportPremios(BaseModel):
    linhas: list[LinhaImportPremio]


class PremioImportItem(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = None
    quantidade: int = Field(default=1, ge=1, le=500)


class ImportarPremiosIn(BaseModel):
    linhas: list[PremioImportItem] = Field(min_length=1, max_length=2000)


class ImportarPremiosOut(BaseModel):
    criados: int
    ignorados: int


class PremioUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    descricao: str | None = None
    imagem_url: str | None = None
    quantidade: int | None = Field(default=None, ge=1, le=500)
    ordem: int | None = None


class UnidadeOut(ORMModel):
    id: int
    numero: int
    status: str
    ganhador_nome: str | None = None
    ganhador_setor: str | None = None
    draw_id: int | None = None
    bloco_id: int | None = None
    ordem_bloco: int | None = None


class PremioOut(ORMModel):
    id: int
    nome: str
    descricao: str | None
    imagem_url: str | None
    quantidade: int
    ordem: int
    unidades: list[UnidadeOut] = []
    disponiveis: int = 0


class ReordenarIn(BaseModel):
    ordem: list[int]  # ids de premios na ordem desejada


# ---------------------------------------------------------------- sorteio
class SortearIn(BaseModel):
    prize_unit_id: int
    idempotency_key: str = Field(min_length=8, max_length=80)
    # Modo blocos: obrigatorio para sortear fora da sequencia do bloco (so admin).
    motivo_fora_da_ordem: str | None = Field(default=None, max_length=300)


class ElegiveisOut(BaseModel):
    total: int
    bloqueios: list[str] = []
    pode_sortear: bool
    # Modo blocos: a unidade escolhida nao e a proxima da sequencia do bloco.
    fora_da_ordem: bool = False
    proxima_unidade_id: int | None = None


class SorteioOut(BaseModel):
    id: int
    rodada: int
    status: str
    premio_id: int
    premio_nome: str
    premio_imagem_url: str | None
    unidade_id: int
    unidade_numero: int
    ganhador_id: int
    ganhador_nome: str
    ganhador_matricula: str
    ganhador_setor: str
    ganhador_foto_url: str | None
    ganhador_pulseira: str | None = None
    evento_id: int | None = None
    evento_nome: str | None = None
    evento_fuso: str | None = None
    elegiveis_total: int
    criado_em: datetime
    criado_por: str
    entregue: bool
    entregue_em: datetime | None
    entregue_por: str | None
    anulado_em: datetime | None
    anulado_por: str | None
    motivo_anulacao: str | None
    tipo_anulacao: str | None
    estorno_entrega: bool
    draw_anterior_id: int | None
    bloco_id: int | None = None
    bloco_numero: int | None = None
    bloco_nome: str | None = None
    reaproveitado: bool = False


class EntregaIn(BaseModel):
    entregue: bool
    # Pulseira apresentada no balcao. Se informada, precisa ser a do ganhador.
    pulseira_conferida: str | None = None
    # Obrigatorio para desfazer (entregue=false).
    motivo: str | None = Field(default=None, max_length=500)

    @field_validator("pulseira_conferida")
    @classmethod
    def _pulseira(cls, v: str | None) -> str | None:
        return normalizar_pulseira(v)


class EntregaLoteIn(BaseModel):
    """Varias unidades do MESMO ganhador no mesmo atendimento."""

    sorteios: list[int] = Field(min_length=1, max_length=100)
    pulseira_conferida: str | None = None
    # Foto opcional da entrega, ja enviada por /api/uploads/imagem.
    foto_url: str | None = None

    @field_validator("pulseira_conferida")
    @classmethod
    def _pulseira(cls, v: str | None) -> str | None:
        return normalizar_pulseira(v)

    @field_validator("foto_url")
    @classmethod
    def _foto(cls, v: str | None) -> str | None:
        if not v:
            return None
        # So imagens gravadas pelo proprio sistema (nada de link externo).
        if not re.fullmatch(r"/uploads/[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|webp)", v):
            raise ValueError("Foto da entrega inválida")
        return v


class EntregasResumoOut(BaseModel):
    # Resultados validos (anulados nunca contam).
    sorteados: int
    entregues: int
    pendentes: int
    percentual: int


class PremiadoOut(BaseModel):
    """Uma unidade sorteada (resultado valido) na Central de Entregas."""

    sorteio_id: int
    participante_id: int
    nome: str
    matricula: str
    pulseira: str | None
    numero_sorteio: int | None
    foto_url: str | None
    premio_id: int
    premio_nome: str
    premio_imagem_url: str | None
    unidade_numero: int
    quantidade_premio: int
    bloco_numero: int | None
    sorteado_em: datetime
    entregue: bool
    entregue_em: datetime | None
    entregue_por: str | None


class PaginaPremiadosOut(BaseModel):
    itens: list[PremiadoOut]
    total: int
    pagina: int
    paginas: int


class HistoricoEntregaOut(BaseModel):
    id: int
    acao: str  # entrega_registrada | entrega_revertida
    criado_em: datetime
    atendente: str
    sorteio_id: int | None
    participante: str | None
    matricula: str | None
    premio: str | None
    unidade: int | None
    bloco_numero: int | None
    pulseira_conferida: str | None
    motivo: str | None = None
    # Situacao ATUAL da unidade: entregue | pendente | anulado.
    situacao_atual: str | None = None
    # Foto opcional tirada na confirmacao da entrega.
    foto_url: str | None = None


class PaginaHistoricoEntregasOut(BaseModel):
    itens: list[HistoricoEntregaOut]
    total: int
    pagina: int
    paginas: int


class OpcaoFiltroOut(BaseModel):
    id: int
    nome: str


class FiltrosEntregasOut(BaseModel):
    blocos: list[OpcaoFiltroOut]
    premios: list[OpcaoFiltroOut]
    operadores: list[OpcaoFiltroOut]


class AnularIn(BaseModel):
    motivo: str = Field(min_length=5, max_length=1000)
    tipo: str = Field(default="outro")
    # Obrigatorio quando o premio ja foi marcado como entregue.
    confirmar_estorno: bool = False

    @field_validator("tipo")
    @classmethod
    def _valida_tipo(cls, v: str) -> str:
        if v not in {"ausencia", "desistencia", "erro_operacional", "outro"}:
            raise ValueError("tipo de anulacao invalido")
        return v


# ---------------------------------------------------------------- recepcao, credenciamento, area pessoal
class PremioGanhoOut(BaseModel):
    sorteio_id: int
    rodada: int
    premio_nome: str
    premio_imagem_url: str | None
    unidade_numero: int
    bloco_numero: int | None
    entregue: bool
    entregue_em: datetime | None
    entregue_por: str | None
    quantidade_premio: int | None = None
    sorteado_em: datetime | None = None


class ColaboradorRecepcaoOut(BaseModel):
    id: int
    nome: str
    matricula: str
    setor: str
    foto_url: str | None
    pulseira: str | None
    numero_sorteio: int | None = None
    presente: bool
    participando: bool
    premios: list[PremioGanhoOut]


class AtendimentoOut(BaseModel):
    id: int
    acao: str
    criado_em: datetime
    atendente: str
    participante: str | None
    premio: str | None
    unidade: int | None
    pulseira_conferida: str | None


class CredenciamentoResumoOut(BaseModel):
    participantes: int
    participando: int
    presentes: int
    ausentes: int
    com_pulseira: int
    sem_pulseira: int
    com_conta: int


class CredenciadoOut(BaseModel):
    id: int
    nome: str
    matricula: str
    setor: str
    foto_url: str | None
    pulseira: str | None
    numero_sorteio: int | None = None
    presente: bool
    participando: bool
    tem_conta: bool


class PaginaCredenciadosOut(BaseModel):
    itens: list[CredenciadoOut]
    total: int
    pagina: int
    paginas: int


class PulseiraCredenciamentoIn(BaseModel):
    pulseira: str
    # Obrigatorio para TROCAR uma pulseira ja atribuida (procedimento controlado).
    motivo: str | None = Field(default=None, max_length=300)

    @field_validator("pulseira")
    @classmethod
    def _pulseira(cls, v: str) -> str:
        normalizada = normalizar_pulseira(v)
        if normalizada is None:
            raise ValueError("informe o numero da pulseira")
        return normalizada


class LiberarCadastroIn(BaseModel):
    # Fica na auditoria: por que a pessoa precisa refazer o cadastro.
    motivo: str = Field(min_length=5, max_length=300)


# ---------------------------------------------------------------- autocadastro (publico)
class EventoAutocadastroOut(BaseModel):
    id: int
    nome: str
    empresa_nome: str
    logo_url: str | None
    cor_fundo: str
    cor_primaria: str
    demo: bool


class IdentificacaoIn(BaseModel):
    """Primeiro acesso pelo QR Code. Nada disto e gravado ou registrado em log.

    Formato invalido NAO gera erro 422 detalhado: o servico responde a mesma
    mensagem generica de "dados nao conferem" (ver services/autocadastro.py).
    """

    matricula: str = Field(min_length=1, max_length=60)
    # "aaaa-mm-dd" (campo de data do navegador).
    nascimento: str = Field(min_length=1, max_length=20)
    # 5 primeiros digitos do CPF.
    cpf5: str = Field(min_length=1, max_length=20)


class IdentificacaoOut(BaseModel):
    # Passe curto (minutos) para concluir o cadastro. Nao e sessao.
    passe: str
    nome: str
    matricula: str
    foto_url: str | None
    login: str


class CartaoSorteOut(BaseModel):
    """Meu Cartao da Sorte: o numero vem do banco e nunca e gerado aqui."""

    evento_id: int
    evento_nome: str
    empresa_nome: str
    nome: str
    matricula: str
    foto_url: str | None
    numero_sorteio: int | None
    # Modo faixa de matriculas: a matricula e o numero da sorte exibido.
    matricula_da_sorte: str | None = None
    presente: bool
    participando: bool


class AutocadastroOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut
    login: str
    conta_nova: bool
    cartao: CartaoSorteOut


# ---------------------------------------------------------------- area pessoal
class MinhaParticipacaoOut(BaseModel):
    evento_id: int
    evento_nome: str
    empresa_nome: str = ""
    nome: str
    matricula: str
    setor: str
    foto_url: str | None
    pulseira: str | None
    numero_sorteio: int | None = None
    # Modo faixa de matriculas: a matricula e o numero da sorte exibido.
    matricula_da_sorte: str | None = None
    presente: bool
    participando: bool = True
    premios: list[PremioGanhoOut]


class PushStatusOut(BaseModel):
    # Push configurado no servidor (chaves VAPID + endereco https).
    disponivel: bool
    chave_publica: str | None
    motivo: str | None = None
    aparelhos: int = 0


class InscricaoPushIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)

    @field_validator("endpoint")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("endpoint de push invalido")
        return v


class CancelarPushIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)


class MinhaAreaOut(BaseModel):
    nome: str
    usuario: str
    participacoes: list[MinhaParticipacaoOut]
    notificacoes_nao_lidas: int = 0


class NotificacaoOut(BaseModel):
    id: int
    tipo: str
    titulo: str
    mensagem: str
    lida: bool
    criada_em: datetime
    evento_id: int
    evento_nome: str
    sorteio_id: int | None
    premio_nome: str | None
    premio_imagem_url: str | None
    bloco_numero: int | None
    # Situacao atual do resultado: aguardando_retirada | entregue | anulado.
    situacao: str | None


# ---------------------------------------------------------------- historico
class PaginaSorteiosOut(BaseModel):
    itens: list[SorteioOut]
    total: int
    pagina: int
    por_pagina: int
    paginas: int


class OperadorOut(BaseModel):
    id: int
    nome: str


class RegistroAuditoriaOut(BaseModel):
    id: int
    acao: str
    detalhes: dict
    usuario: str
    criado_em: datetime


class SorteioDetalheOut(BaseModel):
    sorteio: SorteioOut
    indice_sorteado: int
    # Todos os resultados da mesma unidade, inclusive anulados: mostra a
    # cadeia de anulacoes e resorteios sem precisar seguir os vinculos.
    historico_da_unidade: list[SorteioOut]
    auditoria: list[RegistroAuditoriaOut]


# ---------------------------------------------------------------- blocos
class BlocoIn(BaseModel):
    nome: str | None = Field(default=None, max_length=120)
    capacidade: int | None = Field(default=None, ge=1, le=1000)
    descricao: str | None = Field(default=None, max_length=500)


class BlocoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    capacidade: int | None = Field(default=None, ge=1, le=1000)
    # Enviar "" apaga a descricao; omitir mantem.
    descricao: str | None = Field(default=None, max_length=500)


class DistribuirIn(BaseModel):
    capacidade: int = Field(default=25, ge=1, le=1000)
    # Intercala os premios (o mesmo premio nao sai varias vezes seguidas).
    misturar: bool = False


class PreviaBlocoOut(BaseModel):
    numero: int
    nome: str
    unidades: int


class PreviaDistribuicaoOut(BaseModel):
    """Simulacao: nada e gravado."""

    capacidade: int
    unidades: int
    blocos: list[PreviaBlocoOut]
    # Blocos planejados que serao recriados (nomes, descricoes e ajustes manuais se perdem).
    planejados_refeitos: list[str] = []


class DistribuirNosBlocosIn(BaseModel):
    misturar: bool = False


class PreviaNosBlocosItemOut(BaseModel):
    numero: int
    nome: str
    unidades: int
    capacidade: int


class PreviaNosBlocosOut(BaseModel):
    """Simulacao do preenchimento dos blocos planejados ja criados."""

    unidades: int
    blocos: list[PreviaNosBlocosItemOut]
    # Unidades que nao cabem na capacidade dos blocos: ficam sem bloco.
    sobra: int


class ReordenarBlocosIn(BaseModel):
    # Ids dos blocos PLANEJADOS na nova ordem (todos eles).
    blocos: list[int] = Field(min_length=1)


class DistribuicaoItemIn(BaseModel):
    bloco_id: int
    unidades: list[int]
    capacidade: int | None = Field(default=None, ge=1, le=1000)


class DistribuicaoIn(BaseModel):
    blocos: list[DistribuicaoItemIn] = Field(min_length=1)
    # Versao lida em GET /distribuicao. Se outra pessoa salvou depois, 409.
    versao: str | None = Field(default=None, max_length=64)


class FinalizarBlocoIn(BaseModel):
    # Obrigatorio quando ainda ha unidades sem sorteio no bloco.
    confirmar_pendentes: bool = False


class RemanescentesIn(BaseModel):
    nome: str | None = Field(default=None, max_length=120)
    # Unidades por bloco; sem valor, usa a capacidade padrao do evento.
    capacidade: int | None = Field(default=None, ge=1, le=1000)
    # Intercala os premios (o mesmo premio nao sai varias vezes seguidas).
    misturar: bool = False


class BlocoOut(BaseModel):
    id: int
    numero: int
    nome: str
    descricao: str | None = None
    capacidade: int
    status: str
    ordem: int
    criado_em: datetime
    iniciado_em: datetime | None
    finalizado_em: datetime | None
    finalizado_por: str | None
    total: int
    sorteadas: int
    entregues: int
    restantes: int
    percentual: int


class BlocosOut(BaseModel):
    blocos: list[BlocoOut]
    capacidade_padrao: int
    bloco_ativo_id: int | None
    modo_blocos: bool
    unidades_total: int
    unidades_sem_bloco: int
    # Disponiveis sem bloco + disponiveis deixadas em blocos finalizados.
    unidades_remanescentes: int
    # Sorteadas antes da existencia de blocos (modo legado); nunca se movem.
    sorteadas_sem_bloco: int


class UnidadeBlocoOut(BaseModel):
    id: int
    prize_id: int
    premio_nome: str
    premio_imagem_url: str | None
    numero: int
    quantidade_premio: int
    status: str
    bloco_id: int | None
    ordem_bloco: int | None
    ganhador_nome: str | None = None
    ganhador_setor: str | None = None


class BlocoComUnidadesOut(BaseModel):
    bloco: BlocoOut
    unidades: list[UnidadeBlocoOut]


class DistribuicaoOut(BaseModel):
    blocos: list[BlocoComUnidadesOut]
    sem_bloco: list[UnidadeBlocoOut]
    sorteadas_sem_bloco: int
    # Impressao digital da distribuicao atual (deteccao de edicao simultanea).
    versao: str = ""


class BlocoDetalheOut(BaseModel):
    bloco: BlocoOut
    unidades: list[UnidadeBlocoOut]
    resultados: list[SorteioOut]


class GanhadorBlocoOut(BaseModel):
    rodada: int
    premio_nome: str
    premio_imagem_url: str | None
    premio_descricao: str | None = None
    unidade_numero: int
    ganhador_nome: str
    ganhador_setor: str
    ganhador_foto_url: str | None
    ganhador_numero: int | None = None


# ---------------------------------------------------------------- telao
class TelaoComandoIn(BaseModel):
    estado: str
    prize_unit_id: int | None = None

    @field_validator("estado")
    @classmethod
    def _valida(cls, v: str) -> str:
        if v not in {"aguardando", "premio", "sorteando", "resultado", "encerramento"}:
            raise ValueError("estado invalido")
        return v


ACOES_CARROSSEL = {"iniciar", "pausar", "continuar", "repetir", "proximo", "anterior", "encerrar"}


class CarrosselComandoIn(BaseModel):
    acao: str
    # Obrigatorio em "iniciar": bloco cujos ganhadores serao apresentados.
    bloco_id: int | None = None

    @field_validator("acao")
    @classmethod
    def _acao(cls, v: str) -> str:
        if v not in ACOES_CARROSSEL:
            raise ValueError("acao invalida")
        return v


class TelaoPremioOut(BaseModel):
    nome: str
    descricao: str | None
    imagem_url: str | None
    unidade_numero: int
    unidade_total: int


class TelaoGanhadorOut(BaseModel):
    nome: str
    setor: str
    foto_url: str | None
    numero_sorteio: int | None = None
    # Modo faixa de matriculas: a matricula e o numero da sorte exibido.
    matricula_da_sorte: str | None = None


class TelaoGaleriaItem(BaseModel):
    premio_nome: str
    premio_imagem_url: str | None
    unidade_numero: int
    ganhador_nome: str
    ganhador_setor: str
    ganhador_foto_url: str | None
    ganhador_numero: int | None = None
    ganhador_matricula_da_sorte: str | None = None


class TelaoEstadoOut(BaseModel):
    versao: int
    estado: str
    evento: dict
    rodada: int | None = None
    premio: TelaoPremioOut | None = None
    ganhador: TelaoGanhadorOut | None = None
    nomes_animacao: list[str] = []
    revelar_em: datetime | None = None
    servidor_agora: datetime
    galeria: list[TelaoGaleriaItem] = []


# ---------------------------------------------------------------- relatorio
class ResumoOut(BaseModel):
    participantes_total: int
    participantes_presentes: int
    participantes_elegiveis: int
    premios_total: int
    unidades_total: int
    unidades_disponiveis: int
    unidades_sorteadas: int
    unidades_entregues: int
    sorteios_anulados: int
