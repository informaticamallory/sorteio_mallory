import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { novaChaveIdempotencia, requisitar } from '../api'
import { useAuth } from '../auth'
import { BarraProgresso, EtiquetaBloco, numeroBloco } from '../componentes/blocos'
import ControleCarrossel from '../componentes/ControleCarrossel'
import { Aviso, Carregando, ImagemPremio, Vazio } from '../componentes/ui'
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

  // Uma chave por tentativa de sorteio: cliques repetidos e novas tentativas da
  // mesma requisicao reutilizam a chave e nunca criam um segundo resultado.
  const chaveRef = useRef<string | null>(null)

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
  useEffect(() => {
    if (!premios || resultado) return
    if (selecao && disponiveis.some((d) => d.unidade.id === selecao.unidade.id)) return
    setSelecao(disponiveis[0] ?? null)
  }, [premios, resultado, selecao, disponiveis])

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

  async function apresentarPremio(novaSelecao: Selecao) {
    setSelecao(novaSelecao)
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

  async function iniciarSorteio() {
    if (!selecao || sorteando) return
    setErro('')
    setSorteando(true)
    if (!chaveRef.current) chaveRef.current = novaChaveIdempotencia()
    try {
      const sorteio = await requisitar<SorteioTipo>(`/api/events/${evento.id}/sorteio`, {
        metodo: 'POST',
        corpo: { prize_unit_id: selecao.unidade.id, idempotency_key: chaveRef.current },
      })
      setResultado(sorteio)
      setAguardandoRevelacao(!sorteio.reaproveitado)
      chaveRef.current = null
      await Promise.all([carregarPremios(), recarregarResumo(), recarregarTelao(), carregarBlocos()])
    } catch (e) {
      // A chave e preservada: tocar em "Iniciar sorteio" de novo e uma nova
      // tentativa da MESMA rodada, nao um segundo sorteio.
      setErro(e instanceof Error ? e.message : 'Falha ao sortear')
    } finally {
      setSorteando(false)
    }
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
  const bloqueado = !elegiveis?.pode_sortear || sorteando || emAnimacao

  if (premios === null) return <Carregando />

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

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
          {modoBlocos && blocos && (
            <PainelBloco
              blocos={blocos}
              ativo={blocoAtivo}
              ocupado={operandoBloco || sorteando}
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
                  return (
                    <button
                      key={unidade.id}
                      type="button"
                      onClick={() => void apresentarPremio({ premio, unidade })}
                      className={`flex items-center gap-3 rounded-lg border p-2 text-left transition ${
                        ativo
                          ? 'border-marca-500 bg-marca-50'
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

                  {disponiveis.length > 0 && (
                    <button
                      type="button"
                      className="btn-primario w-full"
                      onClick={() => void apresentarPremio(disponiveis[0])}
                    >
                      Próximo prêmio: {disponiveis[0].premio.nome} <Icone nome="avancar" className="h-4 w-4" />
                    </button>
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
    </div>
  )
}

function PainelBloco({
  blocos,
  ativo,
  ocupado,
  aoOperar,
}: {
  blocos: BlocosResumo
  ativo: Bloco | null
  ocupado: boolean
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
            ? `Há ${blocos.unidades_remanescentes} prêmio(s) remanescente(s): crie um bloco com eles na aba Blocos.`
            : 'Todos os blocos foram finalizados.'}{' '}
          <Link to="../blocos" className="font-semibold underline">
            Abrir Blocos
          </Link>
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
