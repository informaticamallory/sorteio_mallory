export type Papel = 'ADMIN' | 'SORTEIO' | 'ORGANIZADOR' | 'RECEPCAO' | 'ENTREGAS' | 'COLABORADOR'

/** Recepção: o mínimo para check-in e consulta do número. */
export interface PremioConsulta {
  premio_nome: string
  bloco_numero: number | null
  entregue: boolean
}

export interface Atendido {
  id: number
  matricula: string
  nome: string
  numero_sorteio: number | null
  /** Modo faixa de matrículas: a matrícula é o número da sorte exibido. */
  matricula_da_sorte?: string | null
  presente: boolean
  participando: boolean
  /** Prêmios válidos já revelados no telão. */
  premios: PremioConsulta[]
}

export interface EventoRecepcao {
  id: number
  nome: string
  empresa_nome: string
  logo_url: string | null
  demo: boolean
}

export interface CheckinFeito extends Atendido {
  ja_estava_presente: boolean
}

export interface Usuario {
  id: number
  usuario: string
  nome: string
  papel: Papel
  deve_trocar_senha?: boolean
  // Usado só para adaptar a interface; o backend decide o acesso.
  permissoes?: string[]
  // A conta também é participante (tem Cartão da Sorte).
  tem_cartao?: boolean
}

export interface UsuarioAdmin {
  id: number
  usuario: string
  nome: string
  papel: Papel
  setor: string
  pode_sortear: boolean
  ativo: boolean
  criado_em: string
  ultimo_acesso_em: string | null
  bloqueado_ate: string | null
  deve_trocar_senha: boolean
}

export interface SenhaTemporaria {
  usuario: UsuarioAdmin
  senha_temporaria: string
}

export interface PremioGanho {
  sorteio_id: number
  rodada: number
  premio_nome: string
  premio_imagem_url: string | null
  unidade_numero: number
  bloco_numero: number | null
  entregue: boolean
  entregue_em: string | null
  entregue_por: string | null
  quantidade_premio?: number | null
  sorteado_em?: string | null
}

export interface ColaboradorRecepcao {
  id: number
  nome: string
  matricula: string
  setor: string
  foto_url: string | null
  pulseira: string | null
  numero_sorteio?: number | null
  presente: boolean
  participando: boolean
  premios: PremioGanho[]
}

export interface EntregasResumo {
  sorteados: number
  entregues: number
  pendentes: number
  percentual: number
}

export interface Premiado {
  sorteio_id: number
  participante_id: number
  nome: string
  matricula: string
  pulseira: string | null
  numero_sorteio: number | null
  foto_url: string | null
  premio_id: number
  premio_nome: string
  premio_imagem_url: string | null
  unidade_numero: number
  quantidade_premio: number
  bloco_numero: number | null
  sorteado_em: string
  entregue: boolean
  entregue_em: string | null
  entregue_por: string | null
}

export interface Pagina<T> {
  itens: T[]
  total: number
  pagina: number
  paginas: number
}

export interface HistoricoEntrega {
  id: number
  acao: 'entrega_registrada' | 'entrega_revertida'
  criado_em: string
  atendente: string
  sorteio_id: number | null
  participante: string | null
  matricula: string | null
  premio: string | null
  unidade: number | null
  bloco_numero: number | null
  pulseira_conferida: string | null
  motivo: string | null
  situacao_atual: 'entregue' | 'pendente' | 'anulado' | null
}

export interface FiltrosEntregas {
  blocos: { id: number; nome: string }[]
  premios: { id: number; nome: string }[]
  operadores: { id: number; nome: string }[]
}

export interface Atendimento {
  id: number
  acao: string
  criado_em: string
  atendente: string
  participante: string | null
  premio: string | null
  unidade: number | null
  pulseira_conferida: string | null
}

export interface CredenciamentoResumo {
  participantes: number
  participando: number
  presentes: number
  ausentes: number
  com_pulseira: number
  sem_pulseira: number
  com_conta: number
}

export interface Credenciado {
  id: number
  nome: string
  matricula: string
  setor: string
  foto_url: string | null
  pulseira: string | null
  numero_sorteio?: number | null
  presente: boolean
  participando: boolean
  tem_conta: boolean
}

export interface PaginaCredenciados {
  itens: Credenciado[]
  total: number
  pagina: number
  paginas: number
}

export interface MinhaParticipacao {
  evento_id: number
  evento_nome: string
  empresa_nome: string
  nome: string
  matricula: string
  setor: string
  foto_url: string | null
  pulseira: string | null
  numero_sorteio: number | null
  /** Modo faixa de matrículas: a matrícula é o número da sorte exibido. */
  matricula_da_sorte?: string | null
  presente: boolean
  participando: boolean
  premios: PremioGanho[]
}

export interface MinhaArea {
  nome: string
  usuario: string
  participacoes: MinhaParticipacao[]
  notificacoes_nao_lidas: number
}

export interface PushStatus {
  disponivel: boolean
  chave_publica: string | null
  motivo: string | null
  aparelhos: number
}

export interface PortalSituacao {
  url_cadastro: string
  fonte_endereco: 'configurada' | 'rede_local' | 'navegador'
  aviso_endereco: string | null
  ativo: boolean
  aberto: boolean
  inicio: string | null
  fim: string | null
  participantes: number
  com_identificacao: number
  cadastrados: number
  push_disponivel: boolean
  push_motivo: string | null
}

export type SituacaoResultado = 'aguardando_retirada' | 'entregue' | 'anulado'

export interface Notificacao {
  id: number
  tipo: 'PREMIO_GANHO' | 'SORTEIO_ANULADO'
  titulo: string
  mensagem: string
  lida: boolean
  criada_em: string
  evento_id: number
  evento_nome: string
  sorteio_id: number | null
  premio_nome: string | null
  premio_imagem_url: string | null
  bloco_numero: number | null
  situacao: SituacaoResultado | null
}

export interface EventoAutocadastro {
  id: number
  nome: string
  empresa_nome: string
  logo_url: string | null
  cor_fundo: string
  cor_primaria: string
  demo: boolean
}

export interface Identificacao {
  passe: string
  nome: string
  matricula: string
  foto_url: string | null
  login: string
}

export interface CartaoSorte {
  evento_id: number
  evento_nome: string
  empresa_nome: string
  nome: string
  matricula: string
  foto_url: string | null
  numero_sorteio: number | null
  /** Modo faixa de matrículas: a matrícula é o número da sorte exibido. */
  matricula_da_sorte?: string | null
  presente: boolean
  participando: boolean
}

export interface AutocadastroConcluido {
  access_token: string
  usuario: Usuario
  login: string
  conta_nova: boolean
  cartao: CartaoSorte
}

export interface Evento {
  id: number
  nome: string
  empresa_nome: string
  logo_url: string | null
  cor_fundo: string
  cor_primaria: string
  cor_texto: string
  cor_destaque: string
  mensagem_boas_vindas: string
  mensagem_encerramento: string
  regras_participacao: string
  som_ativado: boolean
  reduzir_animacoes: boolean
  duracao_animacao_ms: number
  fuso_horario: string
  telao_token: string
  permite_multiplas_vitorias: boolean
  exige_presenca: boolean
  tratamento_ausente: 'bloquear' | 'resortear' | 'pendente'
  ausente_pode_concorrer_novamente: boolean
  /** "numero_sorte" (padrão) ou "faixa_matricula". */
  modo_sorteio: ModoSorteio
  matricula_faixa_inicio: number | null
  matricula_faixa_fim: number | null
  regras_confirmadas_em: string | null
  capacidade_bloco_padrao: number
  autocadastro_ativo: boolean
  autocadastro_confirma_presenca: boolean
  autocadastro_inicio: string | null
  autocadastro_fim: string | null
  carrossel_segundos: number
  demo: boolean
  criado_em: string
}

export interface Participante {
  id: number
  nome: string
  matricula: string
  setor: string
  foto_url: string | null
  pulseira: string | null
  numero_sorteio?: number | null
  presente: boolean
  participando: boolean
  motivo_participacao: string | null
  ja_ganhou: boolean
  tem_identificacao?: boolean
  tem_conta?: boolean
}

export type StatusUnidade = 'disponivel' | 'sorteado' | 'entregue'

export interface Unidade {
  id: number
  numero: number
  status: StatusUnidade
  ganhador_nome: string | null
  ganhador_setor: string | null
  draw_id: number | null
  bloco_id: number | null
  ordem_bloco: number | null
}

export interface Premio {
  id: number
  nome: string
  descricao: string | null
  imagem_url: string | null
  quantidade: number
  ordem: number
  unidades: Unidade[]
  disponiveis: number
}

export interface Sorteio {
  id: number
  rodada: number
  status: 'valido' | 'anulado'
  premio_id: number
  premio_nome: string
  premio_imagem_url: string | null
  unidade_id: number
  unidade_numero: number
  ganhador_id: number
  ganhador_nome: string
  ganhador_matricula: string
  ganhador_setor: string
  ganhador_foto_url: string | null
  ganhador_pulseira?: string | null
  evento_id?: number | null
  evento_nome?: string | null
  evento_fuso?: string | null
  elegiveis_total: number
  criado_em: string
  criado_por: string
  entregue: boolean
  entregue_em: string | null
  entregue_por: string | null
  anulado_em: string | null
  anulado_por: string | null
  motivo_anulacao: string | null
  tipo_anulacao: string | null
  estorno_entrega: boolean
  draw_anterior_id: number | null
  bloco_id: number | null
  bloco_numero: number | null
  bloco_nome: string | null
  reaproveitado: boolean
}

export interface PaginaSorteios {
  itens: Sorteio[]
  total: number
  pagina: number
  por_pagina: number
  paginas: number
}

export interface Operador {
  id: number
  nome: string
}

export interface SorteioDetalhe {
  sorteio: Sorteio
  indice_sorteado: number
  historico_da_unidade: Sorteio[]
  auditoria: RegistroAuditoria[]
}

export type StatusBloco = 'PLANEJADO' | 'EM_ANDAMENTO' | 'PAUSADO' | 'FINALIZADO'

export interface Bloco {
  id: number
  numero: number
  nome: string
  descricao?: string | null
  capacidade: number
  status: StatusBloco
  ordem: number
  criado_em: string
  iniciado_em: string | null
  finalizado_em: string | null
  finalizado_por: string | null
  total: number
  sorteadas: number
  entregues: number
  restantes: number
  percentual: number
}

export interface BlocosResumo {
  blocos: Bloco[]
  capacidade_padrao: number
  bloco_ativo_id: number | null
  modo_blocos: boolean
  unidades_total: number
  unidades_sem_bloco: number
  unidades_remanescentes: number
  sorteadas_sem_bloco: number
}

export interface UnidadeBloco {
  id: number
  prize_id: number
  premio_nome: string
  premio_imagem_url: string | null
  numero: number
  quantidade_premio: number
  status: StatusUnidade
  bloco_id: number | null
  ordem_bloco: number | null
  ganhador_nome: string | null
  ganhador_setor: string | null
}

export interface BlocoComUnidades {
  bloco: Bloco
  unidades: UnidadeBloco[]
}

export interface Distribuicao {
  blocos: BlocoComUnidades[]
  sem_bloco: UnidadeBloco[]
  sorteadas_sem_bloco: number
  versao: string
}

export interface PreviaDistribuicao {
  capacidade: number
  unidades: number
  blocos: { numero: number; nome: string; unidades: number }[]
  planejados_refeitos: string[]
}

export interface BlocoDetalhe {
  bloco: Bloco
  unidades: UnidadeBloco[]
  resultados: Sorteio[]
}

export interface Elegiveis {
  total: number
  bloqueios: string[]
  pode_sortear: boolean
}

export interface Resumo {
  participantes_total: number
  participantes_presentes: number
  participantes_elegiveis: number
  premios_total: number
  unidades_total: number
  unidades_disponiveis: number
  unidades_sorteadas: number
  unidades_entregues: number
  sorteios_anulados: number
}

export interface LinhaImportacao {
  linha: number
  nome: string
  matricula: string
  setor: string
  erros: string[]
  duplicada_na_planilha: boolean
  ja_existe_no_evento: boolean
  tem_identificacao: boolean
  codigo_identificacao: string | null
  codigo_cpf: string | null
}

export interface PreviaImportacao {
  total_linhas: number
  validas: number
  com_erro: number
  duplicadas: number
  com_identificacao: number
  linhas: LinhaImportacao[]
}

export interface MudancaRegra {
  id: number
  campo: string
  valor_anterior: string
  valor_novo: string
  apos_primeiro_sorteio: boolean
  usuario_nome: string
  criado_em: string
}

export type ModoSorteio = 'numero_sorte' | 'faixa_matricula'

/** Prévia da faixa de matrículas (quem fica dentro e quem fica fora). */
export interface FaixaMatricula {
  inicio: number | null
  fim: number | null
  participantes_ativos: number
  dentro_da_faixa: number
  fora_da_faixa: number
  matricula_nao_numerica: number
  menor_matricula: number | null
  maior_matricula: number | null
}

export interface ResumoRegras {
  itens: string[]
  regras_participacao: string
  confirmadas_em: string | null
  primeiro_sorteio_realizado: boolean
  elegiveis_agora: number
}

export type EstadoTelao =
  | 'aguardando'
  | 'premio'
  | 'sorteando'
  | 'resultado'
  | 'encerramento'
  | 'carrossel_ganhadores'

export interface SlideCarrossel {
  premio_nome: string
  premio_imagem_url: string | null
  premio_descricao?: string | null
  unidade_numero: number
  ganhador_nome: string
  ganhador_setor: string
  ganhador_foto_url: string | null
  ganhador_numero?: number | null
  ganhador_matricula_da_sorte?: string | null
}

/** Estado oficial do carrossel, mantido pelo servidor. */
export interface TelaoCarrossel {
  bloco_id: number
  slides: SlideCarrossel[]
  total: number
  duracao_s: number
  indice: number
  rodando_desde: string | null
  pausado: boolean
  posicao: number
}

export interface TelaoPremio {
  nome: string
  descricao: string | null
  imagem_url: string | null
  unidade_numero: number
  unidade_total: number
}

export interface TelaoGanhador {
  nome: string
  setor: string
  foto_url: string | null
  numero_sorteio?: number | null
  /** Modo faixa de matrículas: a matrícula é o número da sorte exibido. */
  matricula_da_sorte?: string | null
}

export interface TelaoGaleriaItem {
  premio_nome: string
  premio_imagem_url: string | null
  unidade_numero: number
  ganhador_nome: string
  ganhador_setor: string
  ganhador_foto_url: string | null
  ganhador_numero?: number | null
  ganhador_matricula_da_sorte?: string | null
}

export interface TelaoEventoPayload {
  nome: string
  empresa_nome: string
  logo_url: string | null
  cor_fundo: string
  cor_primaria: string
  cor_texto: string
  cor_destaque: string
  mensagem_boas_vindas: string
  mensagem_encerramento: string
  som_ativado: boolean
  reduzir_animacoes: boolean
  duracao_animacao_ms: number
  fuso_horario: string
}

export interface TelaoEstado {
  versao: number
  estado: EstadoTelao
  evento: TelaoEventoPayload
  rodada: number | null
  premio: TelaoPremio | null
  ganhador: TelaoGanhador | null
  nomes_animacao: string[]
  revelar_em: string | null
  servidor_agora: string
  galeria: TelaoGaleriaItem[]
  bloco?: { numero: number; nome: string } | null
  carrossel?: TelaoCarrossel | null
  carrossel_agendado_em?: string | null
}

export interface RegistroAuditoria {
  id: number
  acao: string
  detalhes: Record<string, unknown>
  usuario: string
  criado_em: string
}
