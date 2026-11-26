import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { novaChaveIdempotencia, requisitar } from '../api'
import { useAuth } from '../auth'
import { BarraProgresso, EtiquetaBloco, numeroBloco } from '../componentes/blocos'
import ControleCarrossel from '../componentes/ControleCarrossel'
import { Aviso, Carregando, ImagemPremio, Modal, Vazio } from '../componentes/ui'
import type {
  Bloco,
  BlocosResumo,
  Elegiveis,
  Premio,
  Sorteio as SorteioTipo,
  Unidade,
} from '../types'
import { useTelao } from '../useTelao'
import { ModalFinalizar } from './Blocos'
import { usePainel } from './PainelLayout'
import ModalAnulacao from './ModalAnulacao'
import Icone from '../componentes/Icone'

// Outro operador pode iniciar, pausar ou finalizar blocos em outro aparelho.
const ATUALIZAR_BLOCOS_MS = 10_000

// Sorteio automático: quanto tempo o ganhador fica na tela antes do próximo.
const CHAVE_PAUSA = 'sorteio.pausa_automatico'
const PAUSA_PADRAO_S = 8
const PAUSA_MIN_S = 0.5
const PAUSA_MAX_S = 60

/** Entre 0,5 e 60 s, em passos de 0,5 s. */
function limitarPausa(valor: number): number {
  if (!Number.isFinite(valor)) return PAUSA_PADRAO_S
  return Math.min(PAUSA_MAX_S, Math.max(PAUSA_MIN_S, Math.round(valor * 2) / 2))
}

function lerPausa(): number {
  try {
    const salvo = localStorage.getItem(CHAVE_PAUSA)
    return salvo ? limitarPausa(Number(salvo)) : PAUSA_PADRAO_S
  } catch {
    return PAUSA_PADRAO_S
  }
}

interface Selecao {
  premio: Premio
  unidade: Unidade
}

export default function Sorteio() {
  const { evento, resumo, recarregarResumo } = usePainel()
  const { pode } = useAuth()
  const { estado: telao, conexao, recarregar: recarregarTelao } = useTelao(evento.telao_token)

  const [premios, setPremios] = useState<Premio[] | null>(null)
  const [selecao, setSelecao] = useState<Selecao | null>(null)
  const [elegiveis, setElegiveis] = useState<Elegiveis | null>(null)
  const [resultado, setResultado] = useState<SorteioTipo | null>(null)
  // Enquanto true, o painel esconde o nome para não entregar o resultado antes
  // da revelação no telão. Deixa de valer quando o telão revela ou se o
  // resultado é anulado.
  const [aguardandoRevelacao, setAguardandoRevelacao] = useState(false)
  const [sorteando, setSorteando] = useState(false)
  const [erro, setErro] = useState('')
  const [anulando, setAnulando] = useState(false)
  const [blocos, setBlocos] = useState<BlocosResumo | null>(null)
  const [finalizando, setFinalizando] = useState<Bloco | null>(null)
  const [operandoBloco, setOperandoBloco] = useState(false)
  // Modo blocos: motivo informado pelo admin para sortear fora da sequência
  // (vale para a seleção atual) e o prêmio que está pedindo para pular.
  const [motivoFora, setMotivoFora] = useState<string | null>(null)
  const [pulandoPara, setPulandoPara] = useState<Selecao | null>(null)
  const podePular = pode('pular_ordem_do_bloco')
  // Sorteio automático: sorteia o próximo da sequência sozinho, com uma pausa
  // mostrando o ganhador. Roda neste navegador; cada sorteio continua sendo
  // um sorteio normal no servidor (aleatório, auditado, um por vez).
  const [automatico, setAutomatico] = useState(false)
  const [pausaS, setPausaS] = useState<number>(lerPausa)
  const [textoPausa, setTextoPausa] = useState(() => String(pausaS))
  const [proximoEm, setProximoEm] = useState<number | null>(null)
  const [agora, setAgora] = useState(() => Date.now())
  const [avisoAuto, setAvisoAuto] = useState('')
  // Ao ligar o automático, o primeiro sorteio sai na hora (sem esperar a pausa).
  const imediatoRef = useRef(false)

  // Uma chave por tentativa de sorteio da MESMA unidade: cliques repetidos e
  // novas tentativas reutilizam a chave e nunca criam um segundo resultado.
  const chaveRef = useRef<{ unidade: number; chave: string } | null>(null)

  const carregarPremios = useCallback(async () => {
    const lista = await requisitar<Premio[]>(`/api/events/${evento.id}/premios`)
    setPremios(lista)
    return lista
  }, [evento.id])

  useEffect(() => {
    void carregarPremios().catch((e) =>
      setErro(e instanceof Error ? e.message : 'Falha ao carregar prêmios'),
    )
  }, [carregarPremios])

  const carregarBlocos = useCallback(async () => {
    try {
      setBlocos(await requisitar<BlocosResumo>(`/api/events/${evento.id}/blocos`))
    } catch {
      // Sem blocos disponíveis: a tela segue no modo simples, prêmio a prêmio.
      setBlocos(null)
    }
  }, [evento.id])

  // O servidor é a fonte oficial: recarrega a cada mudança no telão (um
  // sorteio, de qualquer operador) e periodicamente.
  useEffect(() => {
    void carregarBlocos()
  }, [carregarBlocos, telao?.versao])

  useEffect(() => {
    const intervalo = window.setInterval(() => {
      void carregarBlocos()
      void carregarPremios().catch(() => undefined)
    }, ATUALIZAR_BLOCOS_MS)
    return () => window.clearInterval(intervalo)
  }, [carregarBlocos, carregarPremios])

  const conferir = useCallback(async () => {
    const parametros = selecao ? `?prize_unit_id=${selecao.unidade.id}` : ''
    setElegiveis(
      await requisitar<Elegiveis>(`/api/events/${evento.id}/sorteio/elegiveis${parametros}`),
    )
  }, [evento.id, selecao])

  // Reconfere também a cada mudança do telão (ex.: apresentação de ganhadores
  // iniciada ou encerrada libera ou bloqueia o próximo sorteio).
  useEffect(() => {
    void conferir().catch(() => setElegiveis(null))
  }, [conferir, premios, telao?.versao])

  // O telão revelou: o painel pode mostrar o nome.
  useEffect(() => {
    if (telao?.estado === 'resultado') setAguardandoRevelacao(false)
  }, [telao?.estado])

  // Se o aviso do telão se perder (conexão oscilando), relê o estado depois da
  // animação para não deixar o painel (e o automático) esperando à toa.
  useEffect(() => {
    if (!aguardandoRevelacao) return
    const id = window.setTimeout(() => void recarregarTelao(), evento.duracao_animacao_ms + 3000)
    return () => window.clearTimeout(id)
  }, [aguardandoRevelacao, evento.duracao_animacao_ms, recarregarTelao])

  const modoBlocos = blocos?.modo_blocos === true
  const blocoAtivo = blocos?.blocos.find((b) => b.id === blocos.bloco_ativo_id) ?? null

  // Modo blocos: só as unidades do bloco em andamento, na sequência do bloco.
  // Modo simples: todas as unidades disponíveis, na ordem dos prêmios.
  const disponiveis = useMemo(() => {
    const todas = (premios ?? []).flatMap((premio) =>
      premio.unidades
        .filter((u) => u.status === 'disponivel')
        .map((unidade) => ({ premio, unidade })),
    )
    if (!modoBlocos) return todas
    if (!blocoAtivo) return []
    return todas
      .filter(({ unidade }) => unidade.bloco_id === blocoAtivo.id)
      .sort((a, b) => (a.unidade.ordem_bloco ?? 0) - (b.unidade.ordem_bloco ?? 0))
  }, [premios, modoBlocos, blocoAtivo])

  // "Prêmio atual": a próxima unidade da sequência. Não troca enquanto um
  // resultado está na tela (o operador ainda registra entrega ou anulação).
  // Modo blocos: fora da sequência só fica selecionado com o motivo do admin.
  useEffect(() => {
    if (!premios || resultado) return
    const aindaDisponivel = selecao && disponiveis.some((d) => d.unidade.id === selecao.unidade.id)
    const naSequencia = !modoBlocos || disponiveis[0]?.unidade.id === selecao?.unidade.id
    if (aindaDisponivel && (naSequencia || motivoFora)) return
    setSelecao(disponiveis[0] ?? null)
    setMotivoFora(null)
  }, [premios, resultado, selecao, disponiveis, modoBlocos, motivoFora])

  async function operarBloco(bloco: Bloco, acao: 'iniciar' | 'pausar' | 'finalizar') {
    setOperandoBloco(true)
    setErro('')
    try {
      await requisitar(`/api/events/${evento.id}/blocos/${bloco.id}/${acao}`, {
        metodo: 'POST',
        corpo: acao === 'finalizar' ? { confirmar_pendentes: bloco.restantes > 0 } : {},
      })
      setResultado(null)
      setSelecao(null)
      await Promise.all([carregarBlocos(), carregarPremios(), recarregarResumo()])
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Operação não concluída')
      await carregarBlocos()
    } finally {
      setOperandoBloco(false)
    }
  }

  async function apresentarPremio(novaSelecao: Selecao, motivo: string | null = null) {
    setSelecao(novaSelecao)
    setMotivoFora(motivo)
    setResultado(null)
    setErro('')
    await requisitar(`/api/events/${evento.id}/telao`, {
      metodo: 'POST',
      corpo: { estado: 'premio', prize_unit_id: novaSelecao.unidade.id },
    })
  }

  async function comandarTelao(estado: 'aguardando' | 'encerramento') {
    await requisitar(`/api/events/${evento.id}/telao`, { metodo: 'POST', corpo: { estado } })
    if (estado !== 'encerramento') setResultado(null)
  }

  /** Sorteia a unidade `alvo` (manual, "Sortear próximo" ou automático). */
  async function sortear(alvo: Selecao, motivo: string | null): Promise<boolean> {
    if (sorteando) return false
    setErro('')
    setSorteando(true)
    setSelecao(alvo)
    if (chaveRef.current?.unidade !== alvo.unidade.id) {
      chaveRef.current = { unidade: alvo.unidade.id, chave: novaChaveIdempotencia() }
    }
    try {
      const sorteio = await requisitar<SorteioTipo>(`/api/events/${evento.id}/sorteio`, {
        metodo: 'POST',
        corpo: {
          prize_unit_id: alvo.unidade.id,
          idempotency_key: chaveRef.current.chave,
          ...(motivo ? { motivo_fora_da_ordem: motivo } : {}),
        },
      })
      setMotivoFora(null)
      setResultado(sorteio)
      setAguardandoRevelacao(!sorteio.reaproveitado)
      chaveRef.current = null
      await Promise.all([carregarPremios(), recarregarResumo(), recarregarTelao(), carregarBlocos()])
      return true
    } catch (e) {
      // A chave e preservada: tentar de novo a mesma unidade e uma nova
      // tentativa da MESMA rodada, nao um segundo sorteio.
      setErro(e instanceof Error ? e.message : 'Falha ao sortear')
      return false
    } finally {
      setSorteando(false)
    }
  }

  function iniciarSorteio() {
    if (selecao) void sortear(selecao, motivoFora)
  }

  function alterarPausa(valor: number) {
    const pausa = limitarPausa(valor)
    setPausaS(pausa)
    try {
      localStorage.setItem(CHAVE_PAUSA, String(pausa))
    } catch {
      /* fica só nesta tela */
    }
  }

  function ligarAutomatico() {
    setAvisoAuto('')
    setErro('')
    imediatoRef.current = true
    setAutomatico(true)
  }

  async function registrarEntrega(entregue: boolean) {
    if (!resultado) return
    const atualizado = await requisitar<SorteioTipo>(
      `/api/events/${evento.id}/sorteios/${resultado.id}/entrega`,
      { metodo: 'POST', corpo: { entregue } },
    )
    setResultado(atualizado)
    await Promise.all([carregarPremios(), recarregarResumo(), carregarBlocos()])
  }

  const emAnimacao = telao?.estado === 'sorteando'
  const revelado = resultado !== null && !aguardandoRevelacao
  const bloqueado = !elegiveis?.pode_sortear || sorteando || emAnimacao || automatico
  const proximo = disponiveis[0] ?? null
  // Janela aberta (anular, finalizar, pular): o automático espera.
  const emEspera = anulando || finalizando !== null || pulandoPara !== null

  // O automático sempre usa a versão mais recente de `sortear` e do próximo.
  const sortearRef = useRef(sortear)
  sortearRef.current = sortear
  const proximoRef = useRef(proximo)
  proximoRef.current = proximo

  // Laço do automático: espera a revelação no telão, conta a pausa e sorteia o
  // próximo da sequência. Para sozinho no fim ou em qualquer erro do servidor.
  useEffect(() => {
    if (!automatico) {
      setProximoEm(null)
      return
    }
    if (sorteando || emAnimacao || emEspera || (resultado !== null && !revelado)) {
      setProximoEm(null)
      return
    }
    if (!proximoRef.current) {
      setAutomatico(false)
      setProximoEm(null)
      setAvisoAuto(
        modoBlocos
          ? 'Sorteio automático concluído: todos os prêmios do bloco foram sorteados. Confira se algum ganhador ausente precisa ser anulado e finalize o bloco.'
          : 'Sorteio automático concluído: não há mais prêmios disponíveis.',
      )
      return
    }
    const espera = resultado !== null && !imediatoRef.current ? pausaS * 1000 : 0
    setProximoEm(Date.now() + espera)
    const id = window.setTimeout(() => {
      const alvo = proximoRef.current
      imediatoRef.current = false
      setProximoEm(null)
      if (!alvo) return
      void sortearRef.current(alvo, null).then((ok) => {
        if (ok) return
        setAutomatico(false)
        setErro((atual) => `${atual} O sorteio automático foi pausado.`.trim())
      })
    }, espera)
    return () => window.clearTimeout(id)
  }, [
    automatico,
    sorteando,
    emAnimacao,
    emEspera,
    resultado?.id,
    resultado?.status,
    revelado,
    proximo?.unidade.id,
    pausaS,
    modoBlocos,
  ])

  // Contagem regressiva na tela.
  useEffect(() => {
    if (proximoEm === null) return
    setAgora(Date.now())
    const id = window.setInterval(() => setAgora(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [proximoEm])

  const statusAuto = !automatico
    ? null
    : sorteando
      ? 'Sorteando...'
      : emEspera
        ? 'Em espera enquanto a janela está aberta.'
        : emAnimacao || (resultado !== null && !revelado)
          ? 'Aguardando o telão revelar o ganhador...'
          : proximoEm !== null && proximo
            ? `Próximo sorteio em ${Math.max(0, Math.ceil((proximoEm - agora) / 1000))} s: ${proximo.premio.nome} (unidade ${proximo.unidade.numero})`
            : 'Preparando o próximo sorteio...'

  if (premios === null) return <Carregando />

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {avisoAuto && <Aviso tipo="sucesso">{avisoAuto}</Aviso>}

      {!evento.regras_confirmadas_em && (
        <Aviso tipo="atencao">
          As regras ainda não foram confirmadas.{' '}
          {pode('definir_regras') ? (
            <>
              <Link to="../regras" className="font-semibold underline">
                Revise o resumo das regras
              </Link>{' '}
              antes do primeiro sorteio.
            </>
          ) : (
            'Peça a um administrador para confirmá-las antes do primeiro sorteio.'
          )}
        </Aviso>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        {/* ------------------------------------------------ painel de controle */}
        <section className="space-y-4">
          {!modoBlocos && blocos && pode('configurar_blocos') && (
            <p className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
              Este evento ainda não tem blocos, então o sorteio é prêmio a prêmio. Para escolher e iniciar
              por bloco aqui, crie os blocos em{' '}
              <Link to="../blocos" className="font-semibold text-marca-700 underline">
                Blocos
              </Link>
              .
            </p>
          )}
          {modoBlocos && blocos && (
            <PainelBloco
              blocos={blocos}
              ativo={blocoAtivo}
              ocupado={operandoBloco || sorteando}
              configura={pode('configurar_blocos')}
              aoOperar={(bloco, acao) =>
                acao === 'finalizar' ? setFinalizando(bloco) : void operarBloco(bloco, acao)
              }
            />
          )}

          <div className="cartao p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-slate-900">
                1. {modoBlocos ? 'Prêmio atual' : 'Prêmio da rodada'}
              </h2>
              {(!modoBlocos || blocoAtivo) && (
                <span className="text-sm text-slate-500">
                  {disponiveis.length} {modoBlocos ? 'restante(s) no bloco' : 'unidade(s) disponível(is)'}
                </span>
              )}
            </div>

            {disponiveis.length === 0 ? (
              <Vazio
                titulo={
                  modoBlocos && !blocoAtivo
                    ? 'Nenhum bloco em andamento'
                    : 'Nenhuma unidade disponível'
                }
                descricao={
                  modoBlocos && !blocoAtivo
                    ? 'Inicie ou continue um bloco para sortear os prêmios dele.'
                    : modoBlocos
                      ? 'Todos os prêmios deste bloco foram sorteados.'
                      : 'Todos os prêmios já foram sorteados ou não há prêmios cadastrados.'
                }
              />
            ) : (
              <div className="grid max-h-72 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
                {disponiveis.map(({ premio, unidade }, posicao) => {
                  const ativo = selecao?.unidade.id === unidade.id
                  // Modo blocos: só o próximo da sequência; pular é do admin, com motivo.
                  const foraDaSequencia = modoBlocos && posicao > 0
                  const travado = (foraDaSequencia && !podePular) || automatico
                  return (
                    <button
                      key={unidade.id}
                      type="button"
                      disabled={travado}
                      title={
                        automatico
                          ? 'Pause o automático para escolher outro prêmio.'
                          : travado
                          ? 'Os prêmios do bloco saem na sequência definida.'
                          : foraDaSequencia
                            ? 'Sortear fora da sequência (pede o motivo)'
                            : undefined
                      }
                      onClick={() =>
                        foraDaSequencia
                          ? setPulandoPara({ premio, unidade })
                          : void apresentarPremio({ premio, unidade })
                      }
                      className={`flex items-center gap-3 rounded-lg border p-2 text-left transition ${
                        ativo
                          ? 'border-marca-500 bg-marca-50'
                          : travado
                            ? 'cursor-not-allowed border-slate-200 opacity-60'
                            : 'border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      <div className="h-12 w-12 shrink-0 overflow-hidden rounded bg-slate-100">
                        <ImagemPremio
                          url={premio.imagem_url}
                          nome={premio.nome}
                          className="h-full w-full text-slate-400"
                        />
                      </div>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-slate-900">
                          {premio.nome}
                        </span>
                        <span className="block text-xs text-slate-500">
                          {modoBlocos && `${posicao + 1}º · `}Unidade {unidade.numero} de{' '}
                          {premio.quantidade}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>
            )}

            {modoBlocos && disponiveis.length > 1 && !motivoFora && (
              <p className="mt-3 text-xs text-slate-500">
                Os prêmios saem na sequência do bloco.
                {podePular && ' Para sortear outro antes, clique nele e informe o motivo.'}
              </p>
            )}

            {modoBlocos && motivoFora && selecao && (
              <div className="mt-3">
                <Aviso tipo="atencao">
                  <strong>Fora da sequência:</strong> {selecao.premio.nome} (unidade{' '}
                  {selecao.unidade.numero}). Motivo: {motivoFora}. Fica registrado na auditoria.{' '}
                  {disponiveis[0] && (
                    <button
                      type="button"
                      className="font-semibold underline"
                      onClick={() => void apresentarPremio(disponiveis[0])}
                    >
                      Voltar à sequência
                    </button>
                  )}
                </Aviso>
              </div>
            )}
          </div>

          <div className="cartao p-5">
            <h2 className="mb-3 font-semibold text-slate-900">2. Conferência e sorteio</h2>

            <div className="mb-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md border border-borda bg-slate-50 p-2.5">
                <p className="text-xl font-semibold tabular-nums text-slate-900">{elegiveis?.total ?? '—'}</p>
                <p className="text-xs text-slate-500">Elegíveis</p>
              </div>
              <div className="rounded-md border border-borda bg-slate-50 p-2.5">
                <p className="text-xl font-semibold tabular-nums text-slate-900">
                  {resumo?.participantes_presentes ?? '—'}
                </p>
                <p className="text-xs text-slate-500">Presentes</p>
              </div>
              <div className="rounded-md border border-borda bg-slate-50 p-2.5">
                <p className="text-xl font-semibold tabular-nums text-slate-900">
                  {modoBlocos ? (blocoAtivo?.restantes ?? '—') : (resumo?.unidades_disponiveis ?? '—')}
                </p>
                <p className="text-xs text-slate-500">
                  {modoBlocos ? 'Restantes no bloco' : 'Prêmios restantes'}
                </p>
              </div>
            </div>

            {elegiveis && elegiveis.bloqueios.length > 0 && (
              <div className="mb-4">
                <Aviso tipo="atencao">
                  <ul className="list-inside list-disc space-y-1">
                    {elegiveis.bloqueios.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                </Aviso>
              </div>
            )}

            <button
              type="button"
              className="btn-primario h-11 w-full text-base"
              disabled={bloqueado}
              onClick={() => void iniciarSorteio()}
            >
              {sorteando
                ? 'Sorteando...'
                : emAnimacao
                  ? 'Animação em andamento no telão...'
                  : 'Iniciar sorteio'}
            </button>

            {selecao && (
              <p className="mt-2 text-center text-xs text-slate-500">
                {selecao.premio.nome} · unidade {selecao.unidade.numero} de{' '}
                {selecao.premio.quantidade}
              </p>
            )}

            {/* ------------------------------------------------ automático */}
            {(proximo || automatico) && (
              <div
                className={`mt-4 rounded-lg border p-3 ${automatico ? 'border-marca-300 bg-marca-50/60' : 'border-slate-200'}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900">Sorteio automático</p>
                    <p className="text-xs text-slate-500">
                      Sorteia {modoBlocos ? 'os prêmios do bloco' : 'os prêmios'} na sequência, um após o outro.
                    </p>
                  </div>
                  <label className="flex items-center gap-1.5 text-xs text-slate-600">
                    Ganhador na tela por
                    <input
                      type="number"
                      min={PAUSA_MIN_S}
                      max={PAUSA_MAX_S}
                      step={0.5}
                      inputMode="decimal"
                      className="campo h-9 w-20 px-2 text-center"
                      value={textoPausa}
                      onChange={(e) => {
                        // Aceita a digitação livre ("0", "0.", "0,5") e só aplica números válidos.
                        setTextoPausa(e.target.value)
                        const valor = Number(e.target.value.replace(',', '.'))
                        if (e.target.value !== '' && Number.isFinite(valor) && valor >= PAUSA_MIN_S) alterarPausa(valor)
                      }}
                      onBlur={() => setTextoPausa(String(pausaS))}
                      aria-label="Segundos com o ganhador na tela antes do próximo sorteio"
                    />
                    s
                  </label>
                </div>
                {statusAuto && (
                  <p className="mt-2 text-sm font-medium text-marca-700" aria-live="polite">
                    {statusAuto}
                  </p>
                )}
                {automatico ? (
                  <button
                    type="button"
                    className="btn-neutro mt-3 h-11 w-full"
                    onClick={() => setAutomatico(false)}
                  >
                    <Icone nome="pausa" className="h-4 w-4" />
                    Pausar automático
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn-primario mt-3 h-11 w-full"
                    disabled={sorteando || emAnimacao || !proximo || motivoFora !== null}
                    onClick={ligarAutomatico}
                  >
                    <Icone nome="play" className="h-4 w-4" />
                    Iniciar automático
                  </button>
                )}
                <p className="mt-2 text-xs text-slate-500">
                  Pause para tratar um ganhador ausente: abrir a anulação também segura o próximo sorteio.
                  {modoBlocos && ' No fim do bloco ele para sozinho; a finalização continua com você.'}
                </p>
              </div>
            )}
          </div>

          {/* ------------------------------------------------ resultado */}
          {resultado && (
            <div className="cartao overflow-hidden">
              <div className="border-b border-borda px-4 py-2.5">
                <h2 className="titulo-secao">
                  3. Resultado da rodada {resultado.rodada}
                  {resultado.reaproveitado && (
                    <span className="ml-2 text-xs font-normal text-slate-500">
                      (resultado já registrado — nenhum sorteio novo foi feito)
                    </span>
                  )}
                </h2>
              </div>

              {!revelado ? (
                <div className="px-5 py-8 text-center">
                  <p className="text-sm text-slate-500">
                    Resultado registrado no servidor. Aguardando a revelação no telão...
                  </p>
                </div>
              ) : (
                <div className="space-y-4 p-5">
                  <div className="flex items-center gap-4">
                    <div className="h-16 w-16 shrink-0 overflow-hidden rounded-full bg-slate-200">
                      {resultado.ganhador_foto_url ? (
                        <img
                          src={resultado.ganhador_foto_url}
                          alt=""
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <span className="flex h-full w-full items-center justify-center text-lg font-semibold text-slate-500">
                          {resultado.ganhador_nome.slice(0, 1)}
                        </span>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-lg font-semibold text-slate-900">{resultado.ganhador_nome}</p>
                      <p className="text-sm text-slate-500">
                        Matrícula {resultado.ganhador_matricula}
                        {resultado.ganhador_setor ? ` · ${resultado.ganhador_setor}` : ''}
                      </p>
                      <p className="text-xs text-slate-400">
                        Entre {resultado.elegiveis_total} participante(s) elegível(is)
                      </p>
                    </div>
                  </div>

                  {resultado.status === 'anulado' ? (
                    <Aviso tipo="erro">
                      Resultado anulado: {resultado.motivo_anulacao}. Selecione a unidade novamente
                      para sortear outro ganhador.
                    </Aviso>
                  ) : (
                    <div className="flex flex-wrap items-center gap-2">
                      {resultado.entregue ? (
                        <>
                          <span className="etiqueta bg-emerald-50 px-2 py-1 text-emerald-700">
                            <Icone nome="check" className="h-3.5 w-3.5" /> Entrega confirmada
                            {resultado.entregue_por ? ` por ${resultado.entregue_por}` : ''}
                          </span>
                          {pode('confirmar_entrega') && (
                            <button
                              type="button"
                              className="btn-neutro"
                              onClick={() => void registrarEntrega(false)}
                            >
                              Desfazer entrega
                            </button>
                          )}
                        </>
                      ) : (
                        <>
                          {pode('confirmar_entrega') && (
                            <button
                              type="button"
                              className="btn-primario"
                              onClick={() => void registrarEntrega(true)}
                            >
                              Confirmar entrega
                            </button>
                          )}
                          <span className="etiqueta bg-amber-100 px-3 py-2 text-amber-800">
                            Pendente de entrega
                          </span>
                        </>
                      )}
                      {pode('anular_resultado') ? (
                        <button
                          type="button"
                          className="btn-perigo ml-auto"
                          onClick={() => setAnulando(true)}
                        >
                          Anular e sortear de novo
                        </button>
                      ) : (
                        <span className="ml-auto text-xs text-slate-500">
                          Ganhador ausente? Peça a um administrador para anular.
                        </span>
                      )}
                    </div>
                  )}

                  {/* Semiautomático: um clique sorteia o próximo da sequência. */}
                  {proximo && !automatico && (
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <button
                        type="button"
                        className="btn-primario h-11 flex-1"
                        disabled={sorteando || emAnimacao}
                        onClick={() => void sortear(proximo, null)}
                      >
                        Sortear próximo: {proximo.premio.nome} <Icone nome="avancar" className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        className="btn-neutro h-11"
                        title="Mostra o próximo prêmio no telão sem sortear"
                        onClick={() => void apresentarPremio(proximo)}
                      >
                        Só apresentar
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>

        {/* ------------------------------------------------ telão */}
        <aside className="space-y-4">
          {modoBlocos && blocos && pode('controlar_telao') && (
            <ControleCarrossel eventId={evento.id} telao={telao} blocos={blocos.blocos} />
          )}
          <div className="cartao p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold text-slate-900">Telão</h2>
              <span
                className={`etiqueta ${
                  conexao === 'conectado'
                    ? 'bg-emerald-100 text-emerald-800'
                    : conexao === 'reconectando'
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-rose-100 text-rose-800'
                }`}
              >
                {conexao === 'conectado'
                  ? 'Sincronizado'
                  : conexao === 'reconectando'
                    ? 'Reconectando'
                    : 'Sem conexão'}
              </span>
            </div>

            <div className="mb-4 rounded-md border border-borda bg-slate-50 px-3 py-2.5">
              <p className="text-xs text-slate-500">Estado atual</p>
              <p className="font-medium text-slate-900">
                {
                  {
                    aguardando: 'Tela de espera',
                    premio: 'Apresentando prêmio',
                    sorteando: 'Sorteando...',
                    resultado: 'Mostrando ganhador',
                    encerramento: 'Encerramento',
                    carrossel_ganhadores: 'Apresentando ganhadores',
                  }[telao?.estado ?? 'aguardando']
                }
              </p>
              {telao?.premio && (
                <p className="mt-0.5 truncate text-xs text-slate-500">
                  {telao.premio.nome} · un. {telao.premio.unidade_numero}/
                  {telao.premio.unidade_total}
                </p>
              )}
            </div>

            <div className="grid gap-2">
              <button
                type="button"
                className="btn-neutro"
                onClick={() => void comandarTelao('aguardando')}
              >
                Voltar para a tela de espera
              </button>
              <button
                type="button"
                className="btn-neutro"
                disabled={!selecao}
                onClick={() => selecao && void apresentarPremio(selecao)}
              >
                Reapresentar o prêmio
              </button>
              <button
                type="button"
                className="btn-neutro"
                onClick={() => void comandarTelao('encerramento')}
              >
                Ir para o encerramento
              </button>
              <a
                href={`/telao/${evento.telao_token}`}
                target="_blank"
                rel="noreferrer"
                className="btn-primario"
              >
                Abrir telão em nova aba
              </a>
            </div>
          </div>

          <div className="cartao p-5 text-sm text-slate-600">
            <h3 className="mb-2 font-semibold text-slate-900">Regras em vigor</h3>
            <ul className="space-y-1">
              <li className="font-medium text-slate-800">
                Modo:{' '}
                {evento.modo_sorteio === 'faixa_matricula'
                  ? `faixa de matrículas ${evento.matricula_faixa_inicio ?? '?'} a ${evento.matricula_faixa_fim ?? '?'}`
                  : 'número da sorte'}
              </li>
              <li>
                {evento.permite_multiplas_vitorias
                  ? 'Pode ganhar várias vezes'
                  : 'Cada pessoa ganha uma vez'}
              </li>
              <li>
                {evento.exige_presenca
                  ? 'Somente presença confirmada'
                  : 'Presença não é obrigatória'}
              </li>
              <li>
                Ausente:{' '}
                {
                  {
                    bloquear: 'não concorre',
                    resortear: 'anula e sorteia de novo',
                    pendente: 'prêmio fica pendente',
                  }[evento.tratamento_ausente]
                }
              </li>
            </ul>
            {pode('definir_regras') && (
              <Link to="../regras" className="mt-3 inline-block text-xs font-medium underline">
                Alterar regras
              </Link>
            )}
          </div>
        </aside>
      </div>

      <ModalAnulacao
        aberto={anulando}
        sorteio={resultado}
        eventId={evento.id}
        aoFechar={() => setAnulando(false)}
        aoConcluir={async (atualizado) => {
          setResultado(atualizado)
          setAguardandoRevelacao(false)
          setAnulando(false)
          await Promise.all([carregarPremios(), recarregarResumo(), recarregarTelao(), carregarBlocos()])
        }}
      />

      <ModalFinalizar
        bloco={finalizando}
        aoFechar={() => setFinalizando(null)}
        aoConfirmar={async (bloco) => {
          setFinalizando(null)
          await operarBloco(bloco, 'finalizar')
        }}
      />

      <ModalForaDaSequencia
        destino={pulandoPara}
        proximo={disponiveis[0] ?? null}
        aoFechar={() => setPulandoPara(null)}
        aoConfirmar={async (motivo) => {
          if (!pulandoPara) return
          const destino = pulandoPara
          setPulandoPara(null)
          try {
            await apresentarPremio(destino, motivo)
          } catch (e) {
            setErro(e instanceof Error ? e.message : 'Não foi possível apresentar o prêmio')
          }
        }}
      />
    </div>
  )
}

/** Admin: sortear um prêmio do bloco antes do próximo da sequência, com motivo. */
function ModalForaDaSequencia({
  destino,
  proximo,
  aoFechar,
  aoConfirmar,
}: {
  destino: Selecao | null
  proximo: Selecao | null
  aoFechar: () => void
  aoConfirmar: (motivo: string) => Promise<void> | void
}) {
  const [motivo, setMotivo] = useState('')

  useEffect(() => {
    if (destino) setMotivo('')
  }, [destino])

  if (!destino) return null
  const valido = motivo.trim().length >= 5

  return (
    <Modal titulo="Sortear fora da sequência" aberto={destino !== null} aoFechar={aoFechar}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (valido) void aoConfirmar(motivo.trim())
        }}
      >
        <Aviso tipo="atencao">
          O próximo da sequência é{' '}
          <strong>
            {proximo ? `${proximo.premio.nome} (unidade ${proximo.unidade.numero})` : '—'}
          </strong>
          . Você vai sortear antes{' '}
          <strong>
            {destino.premio.nome} (unidade {destino.unidade.numero})
          </strong>
          . O motivo fica registrado na auditoria do sorteio.
        </Aviso>
        <div>
          <label className="rotulo" htmlFor="motivo-fora-da-sequencia">
            Motivo (mínimo 5 caracteres)
          </label>
          <textarea
            id="motivo-fora-da-sequencia"
            className="campo"
            rows={3}
            required
            minLength={5}
            maxLength={300}
            autoFocus
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: patrocinador precisa sair mais cedo"
          />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn-primario" disabled={!valido}>
            Selecionar este prêmio
          </button>
        </div>
      </form>
    </Modal>
  )
}

function PainelBloco({
  blocos,
  ativo,
  ocupado,
  configura,
  aoOperar,
}: {
  blocos: BlocosResumo
  ativo: Bloco | null
  ocupado: boolean
  /** Pode abrir a tela de Blocos (o Sorteador não pode). */
  configura: boolean
  aoOperar: (bloco: Bloco, acao: 'iniciar' | 'pausar' | 'finalizar') => void
}) {
  if (ativo) {
    const concluido = ativo.restantes === 0
    return (
      <div className="cartao border-emerald-300 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
              BLOCO ATUAL · {numeroBloco(ativo.numero)}
            </p>
            <h2 className="text-lg font-semibold text-slate-900">{ativo.nome}</h2>
            <p className="text-sm text-slate-600">
              {ativo.sorteadas} de {ativo.total} sorteado(s) · {ativo.restantes} restante(s)
            </p>
          </div>
          <EtiquetaBloco status={ativo.status} />
        </div>
        <div className="mt-3">
          <BarraProgresso percentual={ativo.percentual} rotulo={`Progresso do ${ativo.nome}`} />
        </div>
        {concluido && (
          <div className="mt-3">
            <Aviso tipo="sucesso">
              Todos os prêmios deste bloco foram sorteados. Confira se algum ganhador ausente precisa
              ser anulado e então finalize o bloco.
            </Aviso>
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-neutro"
            disabled={ocupado}
            onClick={() => aoOperar(ativo, 'pausar')}
          >
            Pausar bloco
          </button>
          <button
            type="button"
            className={concluido ? 'btn-primario' : 'btn-neutro'}
            disabled={ocupado}
            onClick={() => aoOperar(ativo, 'finalizar')}
          >
            Finalizar bloco
          </button>
        </div>
      </div>
    )
  }

  const iniciaveis = blocos.blocos.filter(
    (b) => (b.status === 'PLANEJADO' || b.status === 'PAUSADO') && b.restantes > 0,
  )
  return (
    <div className="cartao p-5">
      <h2 className="font-semibold text-slate-900">Selecione o bloco</h2>
      {iniciaveis.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600">
          Não há blocos para iniciar.{' '}
          {blocos.unidades_remanescentes > 0
            ? `Há ${blocos.unidades_remanescentes} prêmio(s) remanescente(s): ${
                configura ? 'crie um bloco com eles na aba Blocos.' : 'peça ao organizador para criar um bloco com eles.'
              }`
            : 'Todos os blocos foram finalizados.'}{' '}
          {configura && (
            <Link to="../blocos" className="font-semibold underline">
              Abrir Blocos
            </Link>
          )}
        </p>
      ) : (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {iniciaveis.map((b) => (
            <li key={b.id} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 p-3">
              <div className="min-w-0">
                <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{numeroBloco(b.numero)}</p>
                <p className="truncate text-sm font-medium text-slate-900">{b.nome}</p>
                <p className="text-xs text-slate-500">
                  {b.restantes} de {b.total} restante(s)
                </p>
              </div>
              <button
                type="button"
                className="btn-primario shrink-0 px-3 py-1.5"
                disabled={ocupado}
                onClick={() => aoOperar(b, 'iniciar')}
              >
                {b.status === 'PAUSADO' ? 'Continuar' : 'Iniciar'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
