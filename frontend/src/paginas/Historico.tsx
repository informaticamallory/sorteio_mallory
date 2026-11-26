import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { baixarArquivo, requisitar } from '../api'
import { useAuth } from '../auth'
import { Aviso, Carregando, Etiqueta, ImagemPremio, Modal, Vazio } from '../componentes/ui'
import type {
  BlocosResumo,
  Evento,
  Operador,
  PaginaSorteios,
  RegistroAuditoria,
  Sorteio,
  SorteioDetalhe,
} from '../types'
import { usePainel } from './PainelLayout'
import ModalAnulacao from './ModalAnulacao'
import Icone from '../componentes/Icone'

const ESPERA_DIGITACAO_MS = 350
const POR_PAGINA = [25, 50, 100]

const ORDENACOES = [
  { valor: 'data:desc', rotulo: 'Mais recentes' },
  { valor: 'data:asc', rotulo: 'Mais antigos' },
  { valor: 'rodada:asc', rotulo: 'Rodada (crescente)' },
  { valor: 'ganhador:asc', rotulo: 'Ganhador (A–Z)' },
  { valor: 'premio:asc', rotulo: 'Prêmio (A–Z)' },
]

// Filtros guardados na URL: F5, voltar e links compartilhados mantêm a pesquisa.
// Chave "evento": ausente = evento atual; "todos" = todos os eventos.
const FILTROS = ['q', 'evento', 'bloco', 'de', 'ate', 'status', 'entrega', 'operador'] as const

export function formatar(data: string | null, fuso: string): string {
  if (!data) return '—'
  // O backend grava UTC; o sufixo Z garante a conversão correta para o fuso.
  return new Date(`${data}Z`).toLocaleString('pt-BR', { timeZone: fuso })
}

export default function Historico() {
  const { evento, recarregarResumo } = usePainel()
  const { pode } = useAuth()
  const [params, setParams] = useSearchParams()

  const [texto, setTexto] = useState(params.get('q') ?? '')
  const [pagina, setPagina] = useState<PaginaSorteios | null>(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')
  const [filtrosAbertos, setFiltrosAbertos] = useState(false)

  const [eventos, setEventos] = useState<Evento[]>([])
  const [blocos, setBlocos] = useState<BlocosResumo | null>(null)
  const [operadores, setOperadores] = useState<Operador[]>([])

  const [detalheId, setDetalheId] = useState<number | null>(null)
  const [auditoria, setAuditoria] = useState<RegistroAuditoria[] | null>(null)
  const sequencia = useRef(0)

  // ---------------------------------------------------------------- filtros
  const eventoFiltro = params.get('evento') ?? String(evento.id)
  const eventoId = eventoFiltro === 'todos' ? null : Number(eventoFiltro)
  const numeroPagina = Math.max(1, Number(params.get('pagina') ?? 1))
  const porPagina = POR_PAGINA.includes(Number(params.get('por_pagina'))) ? Number(params.get('por_pagina')) : 25
  const ordenacao = params.get('ordem') ?? 'data:desc'

  const ativos = FILTROS.filter((f) => f !== 'q' && f !== 'evento' && params.get(f)).length +
    (params.get('evento') ? 1 : 0)

  const alterar = useCallback(
    (mudancas: Record<string, string | null>, manterPagina = false) => {
      setParams(
        (atual) => {
          const novo = new URLSearchParams(atual)
          for (const [chave, valor] of Object.entries(mudancas)) {
            if (valor === null || valor === '') novo.delete(chave)
            else novo.set(chave, valor)
          }
          if (!manterPagina) novo.delete('pagina')
          return novo
        },
        { replace: true },
      )
    },
    [setParams],
  )

  function limpar() {
    setTexto('')
    setParams(new URLSearchParams(), { replace: true })
  }

  // Busca com espera: só consulta quando a digitação pausa.
  useEffect(() => {
    // Compara sem os espaços das pontas: "jo " e "jo" são a mesma pesquisa
    // (sem isso, o filtro seria reaplicado em ciclo, voltando à página 1).
    if (texto.trim() === (params.get('q') ?? '')) return
    const espera = window.setTimeout(() => alterar({ q: texto.trim() || null }), ESPERA_DIGITACAO_MS)
    return () => window.clearTimeout(espera)
  }, [texto, params, alterar])

  const consulta = useMemo(() => {
    const q = new URLSearchParams()
    const texto = params.get('q')
    if (texto) q.set('q', texto)
    if (eventoId !== null) q.set('event_id', String(eventoId))
    const bloco = params.get('bloco')
    if (bloco === 'sem') q.set('sem_bloco', 'true')
    else if (bloco) q.set('bloco_id', bloco)
    if (params.get('de')) q.set('data_inicio', params.get('de')!)
    if (params.get('ate')) q.set('data_fim', params.get('ate')!)
    if (params.get('status')) q.set('status', params.get('status')!)
    if (params.get('entrega')) q.set('entrega', params.get('entrega')!)
    if (params.get('operador')) q.set('operador_id', params.get('operador')!)
    const [ordenar, direcao] = ordenacao.split(':')
    q.set('ordenar', ordenar)
    q.set('direcao', direcao)
    return q
  }, [params, eventoId, ordenacao])

  // ---------------------------------------------------------------- dados
  const carregar = useCallback(async () => {
    const minha = ++sequencia.current
    setCarregando(true)
    try {
      const pedido = new URLSearchParams(consulta)
      pedido.set('pagina', String(numeroPagina))
      pedido.set('por_pagina', String(porPagina))
      const resposta = await requisitar<PaginaSorteios>(`/api/sorteios?${pedido.toString()}`)
      // Respostas fora de ordem (digitação rápida) não sobrescrevem a mais nova.
      if (minha !== sequencia.current) return
      setPagina(resposta)
      setErro('')
    } catch (e) {
      if (minha === sequencia.current) setErro(e instanceof Error ? e.message : 'Falha na pesquisa')
    } finally {
      if (minha === sequencia.current) setCarregando(false)
    }
  }, [consulta, numeroPagina, porPagina])

  useEffect(() => {
    void carregar()
  }, [carregar])

  useEffect(() => {
    void requisitar<Evento[]>('/api/events').then(setEventos).catch(() => setEventos([]))
  }, [])

  useEffect(() => {
    setBlocos(null)
    const consultaOperadores = eventoId !== null ? `?event_id=${eventoId}` : ''
    void requisitar<Operador[]>(`/api/sorteios/operadores${consultaOperadores}`)
      .then(setOperadores)
      .catch(() => setOperadores([]))
    if (eventoId !== null) {
      void requisitar<BlocosResumo>(`/api/events/${eventoId}/blocos`)
        .then(setBlocos)
        .catch(() => setBlocos(null))
    }
  }, [eventoId])

  async function exportar(formato: 'csv' | 'xlsx') {
    try {
      await baixarArquivo(`/api/sorteios/export.${formato}?${consulta.toString()}`, `sorteios.${formato}`)
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao exportar')
    }
  }

  const fusoPadrao = evento.fuso_horario
  const itens = pagina?.itens ?? []

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* ------------------------------------------------ pesquisa e filtros */}
      <section className="cartao space-y-3 p-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <label htmlFor="busca-historico" className="sr-only">
              Pesquisar
            </label>
            <input
              id="busca-historico"
              type="search"
              className="campo pr-9"
              placeholder="Nome, matrícula ou prêmio"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              autoComplete="off"
            />
            {carregando && (
              <span
                aria-label="Pesquisando"
                className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin rounded-full border-2 border-slate-300 border-t-marca-700"
              />
            )}
          </div>
          <button
            type="button"
            className="btn-neutro md:hidden"
            aria-expanded={filtrosAbertos}
            aria-controls="filtros-historico"
            onClick={() => setFiltrosAbertos((v) => !v)}
          >
            Filtros{ativos > 0 ? ` (${ativos})` : ''} <Icone nome={filtrosAbertos ? 'acima' : 'abaixo'} />
          </button>
        </div>

        <div
          id="filtros-historico"
          className={`${filtrosAbertos ? 'grid' : 'hidden'} gap-3 md:grid md:grid-cols-3 lg:grid-cols-4`}
        >
          <Filtro rotulo="Evento" id="f-evento">
            <select
              id="f-evento"
              className="campo"
              value={eventoFiltro}
              onChange={(e) =>
                alterar({
                  evento: e.target.value === String(evento.id) ? null : e.target.value,
                  bloco: null,
                  operador: null,
                })
              }
            >
              {eventos.length === 0 && <option value={evento.id}>{evento.nome}</option>}
              {eventos.map((ev) => (
                <option key={ev.id} value={ev.id}>
                  {ev.nome}
                  {ev.id === evento.id ? ' (atual)' : ''}
                </option>
              ))}
              <option value="todos">Todos os eventos</option>
            </select>
          </Filtro>

          <Filtro rotulo="Bloco" id="f-bloco">
            <select
              id="f-bloco"
              className="campo"
              value={params.get('bloco') ?? ''}
              disabled={eventoId === null}
              title={eventoId === null ? 'Escolha um evento para filtrar por bloco' : undefined}
              onChange={(e) => alterar({ bloco: e.target.value })}
            >
              <option value="">Todos</option>
              {blocos?.blocos.map((b) => (
                <option key={b.id} value={b.id}>
                  {String(b.numero).padStart(2, '0')} — {b.nome}
                </option>
              ))}
              <option value="sem">Sem bloco</option>
            </select>
          </Filtro>

          <Filtro rotulo="Situação do sorteio" id="f-status">
            <select
              id="f-status"
              className="campo"
              value={params.get('status') ?? ''}
              onChange={(e) => alterar({ status: e.target.value })}
            >
              <option value="">Todas</option>
              <option value="valido">Válidos</option>
              <option value="anulado">Anulados</option>
            </select>
          </Filtro>

          <Filtro rotulo="Entrega" id="f-entrega">
            <select
              id="f-entrega"
              className="campo"
              value={params.get('entrega') ?? ''}
              onChange={(e) => alterar({ entrega: e.target.value })}
            >
              <option value="">Todas</option>
              <option value="pendente">Pendentes</option>
              <option value="entregue">Entregues</option>
              <option value="estornado">Estornadas</option>
            </select>
          </Filtro>

          <Filtro rotulo="Operador" id="f-operador">
            <select
              id="f-operador"
              className="campo"
              value={params.get('operador') ?? ''}
              onChange={(e) => alterar({ operador: e.target.value })}
            >
              <option value="">Todos</option>
              {operadores.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.nome}
                </option>
              ))}
            </select>
          </Filtro>

          <Filtro rotulo="De" id="f-de">
            <input
              id="f-de"
              type="date"
              className="campo"
              value={params.get('de') ?? ''}
              max={params.get('ate') ?? undefined}
              onChange={(e) => alterar({ de: e.target.value })}
            />
          </Filtro>

          <Filtro rotulo="Até" id="f-ate">
            <input
              id="f-ate"
              type="date"
              className="campo"
              value={params.get('ate') ?? ''}
              min={params.get('de') ?? undefined}
              onChange={(e) => alterar({ ate: e.target.value })}
            />
          </Filtro>

          <div className="flex items-end">
            <button
              type="button"
              className="btn-neutro w-full"
              disabled={ativos === 0 && !params.get('q')}
              onClick={limpar}
            >
              Limpar filtros
            </button>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ barra de resultados */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600" aria-live="polite">
          {pagina ? (
            <>
              <strong>{pagina.total}</strong> resultado(s)
              {eventoId === null && ' em todos os eventos'}
            </>
          ) : (
            'Pesquisando...'
          )}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="ordenacao">
            Ordenar por
          </label>
          <select
            id="ordenacao"
            className="campo w-auto py-1.5"
            value={ordenacao}
            onChange={(e) => alterar({ ordem: e.target.value === 'data:desc' ? null : e.target.value })}
          >
            {ORDENACOES.map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.rotulo}
              </option>
            ))}
          </select>
          {pode('exportar_resultados') && (
            <>
              <button type="button" className="btn-neutro" disabled={!pagina?.total} onClick={() => void exportar('csv')}>
                Exportar CSV
              </button>
              <button type="button" className="btn-primario" disabled={!pagina?.total} onClick={() => void exportar('xlsx')}>
                Exportar XLSX
              </button>
            </>
          )}
        </div>
      </div>

      {/* ------------------------------------------------ resultados */}
      {pagina === null ? (
        <Carregando texto="Pesquisando..." />
      ) : itens.length === 0 ? (
        <div className="space-y-2">
          <Vazio
            titulo="Nenhum resultado encontrado"
            descricao={
              ativos > 0 || params.get('q')
                ? 'Revise a pesquisa ou limpe os filtros.'
                : 'Os sorteios aparecerão aqui.'
            }
          />
          {(ativos > 0 || params.get('q')) && (
            <div className="text-center">
              <button type="button" className="btn-neutro" onClick={limpar}>
                Limpar filtros
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className={`transition-opacity ${carregando ? 'opacity-60' : ''}`} aria-busy={carregando}>
          <TabelaResultados itens={itens} fusoPadrao={fusoPadrao} aoAbrir={setDetalheId} />
          <ListaResultados itens={itens} fusoPadrao={fusoPadrao} aoAbrir={setDetalheId} />
        </div>
      )}

      {pagina && pagina.total > 0 && (
        <nav className="flex flex-wrap items-center justify-between gap-2" aria-label="Paginação">
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <label htmlFor="por-pagina">Por página</label>
            <select
              id="por-pagina"
              className="campo w-auto py-1"
              value={porPagina}
              onChange={(e) => alterar({ por_pagina: e.target.value === '25' ? null : e.target.value })}
            >
              {POR_PAGINA.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn-neutro"
              disabled={numeroPagina <= 1 || carregando}
              onClick={() => alterar({ pagina: String(numeroPagina - 1) }, true)}
            >
              <Icone nome="voltar" className="h-4 w-4" /> Anterior
            </button>
            <span className="text-sm text-slate-600">
              Página {Math.min(numeroPagina, pagina.paginas)} de {pagina.paginas}
            </span>
            <button
              type="button"
              className="btn-neutro"
              disabled={numeroPagina >= pagina.paginas || carregando}
              onClick={() => alterar({ pagina: String(numeroPagina + 1) }, true)}
            >
              Próxima <Icone nome="avancar" className="h-4 w-4" />
            </button>
          </div>
        </nav>
      )}

      {/* ------------------------------------------------ auditoria do evento atual */}
      {pode('visualizar_auditoria') && (
      <section className="cartao p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">Registro de auditoria</h2>
          <button
            type="button"
            className="btn-neutro"
            onClick={async () =>
              setAuditoria(
                auditoria
                  ? null
                  : await requisitar<RegistroAuditoria[]>(`/api/events/${evento.id}/relatorio/auditoria`),
              )
            }
          >
            {auditoria ? 'Ocultar' : 'Mostrar'}
          </button>
        </div>
        {auditoria && <ListaAuditoria registros={auditoria} fuso={evento.fuso_horario} />}
      </section>
      )}

      <ModalDetalhe
        drawId={detalheId}
        fusoPadrao={fusoPadrao}
        aoFechar={() => setDetalheId(null)}
        aoAlterar={async () => {
          await carregar()
          await recarregarResumo()
        }}
      />
    </div>
  )
}

// ------------------------------------------------------------------ peças
function Filtro({ rotulo, id, children }: { rotulo: string; id: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="rotulo" htmlFor={id}>
        {rotulo}
      </label>
      {children}
    </div>
  )
}

function Foto({ url, nome, tamanho = 'h-10 w-10' }: { url: string | null; nome: string; tamanho?: string }) {
  return (
    <div className={`${tamanho} shrink-0 overflow-hidden rounded-full bg-slate-200`}>
      {url ? (
        <img src={url} alt="" className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-sm font-semibold text-slate-500">
          {nome.slice(0, 1).toUpperCase()}
        </span>
      )}
    </div>
  )
}

function SituacaoEntrega({ s }: { s: Sorteio }) {
  if (s.status === 'anulado') {
    return s.estorno_entrega ? (
      <span className="etiqueta bg-orange-100 text-orange-800">Estornado</span>
    ) : null
  }
  return <Etiqueta status={s.entregue ? 'entregue' : 'pendente'} />
}

function rotuloBloco(s: Sorteio): string {
  return s.bloco_numero ? `${String(s.bloco_numero).padStart(2, '0')} — ${s.bloco_nome}` : '—'
}

function TabelaResultados({
  itens,
  fusoPadrao,
  aoAbrir,
}: {
  itens: Sorteio[]
  fusoPadrao: string
  aoAbrir: (id: number) => void
}) {
  return (
    <div className="cartao hidden overflow-x-auto md:block">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2" scope="col">
              Ganhador
            </th>
            <th className="px-3 py-2" scope="col">
              Matrícula
            </th>
            <th className="px-3 py-2" scope="col">
              Pulseira
            </th>
            <th className="px-3 py-2" scope="col">
              Prêmio
            </th>
            <th className="px-3 py-2" scope="col">
              Bloco
            </th>
            <th className="px-3 py-2" scope="col">
              Data e hora
            </th>
            <th className="px-3 py-2" scope="col">
              Situação
            </th>
            <th className="px-3 py-2" scope="col">
              Operador
            </th>
            <th className="px-3 py-2" scope="col">
              <span className="sr-only">Ações</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {itens.map((s) => (
            <tr key={s.id} className={s.status === 'anulado' ? 'bg-rose-50/50' : ''}>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <Foto url={s.ganhador_foto_url} nome={s.ganhador_nome} />
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{s.ganhador_nome}</p>
                    <p className="text-xs text-slate-500">
                      Rodada {s.rodada}
                      {s.evento_nome ? ` · ${s.evento_nome}` : ''}
                    </p>
                  </div>
                </div>
              </td>
              <td className="px-3 py-2 font-mono text-xs">{s.ganhador_matricula}</td>
              <td className="px-3 py-2 font-mono text-xs">{s.ganhador_pulseira ?? '—'}</td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <div className="h-9 w-9 shrink-0 overflow-hidden rounded bg-slate-100">
                    <ImagemPremio url={s.premio_imagem_url} nome={s.premio_nome} className="h-full w-full text-slate-400" />
                  </div>
                  <span>
                    {s.premio_nome}
                    <span className="block text-xs text-slate-400">un. {s.unidade_numero}</span>
                  </span>
                </div>
              </td>
              <td className="px-3 py-2 text-xs text-slate-600">{rotuloBloco(s)}</td>
              <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-600">
                {formatar(s.criado_em, s.evento_fuso ?? fusoPadrao)}
              </td>
              <td className="px-3 py-2">
                <div className="flex flex-col items-start gap-1">
                  <Etiqueta status={s.status} />
                  <SituacaoEntrega s={s} />
                </div>
              </td>
              <td className="px-3 py-2 text-xs text-slate-600">{s.criado_por}</td>
              <td className="px-3 py-2 text-right">
                <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => aoAbrir(s.id)}>
                  Detalhes
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ListaResultados({
  itens,
  fusoPadrao,
  aoAbrir,
}: {
  itens: Sorteio[]
  fusoPadrao: string
  aoAbrir: (id: number) => void
}) {
  return (
    <ul className="space-y-2 md:hidden">
      {itens.map((s) => (
        <li key={s.id}>
          <button
            type="button"
            onClick={() => aoAbrir(s.id)}
            className={`cartao flex w-full items-start gap-3 p-3 text-left ${
              s.status === 'anulado' ? 'border-rose-200 bg-rose-50/50' : ''
            }`}
          >
            <Foto url={s.ganhador_foto_url} nome={s.ganhador_nome} />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-slate-900">{s.ganhador_nome}</p>
              <p className="text-xs text-slate-500">
                Matrícula <span className="font-mono">{s.ganhador_matricula}</span>
                {s.ganhador_pulseira ? (
                  <>
                    {' '}· Pulseira <span className="font-mono">{s.ganhador_pulseira}</span>
                  </>
                ) : null}
              </p>
              <p className="mt-1 text-sm text-slate-700">
                {s.premio_nome} <span className="text-xs text-slate-400">un. {s.unidade_numero}</span>
              </p>
              <p className="text-xs text-slate-500">
                {formatar(s.criado_em, s.evento_fuso ?? fusoPadrao)} · {s.criado_por}
                {s.bloco_numero ? ` · Bloco ${String(s.bloco_numero).padStart(2, '0')}` : ''}
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                <Etiqueta status={s.status} />
                <SituacaoEntrega s={s} />
              </div>
            </div>
            <div className="h-12 w-12 shrink-0 overflow-hidden rounded bg-slate-100">
              <ImagemPremio url={s.premio_imagem_url} nome={s.premio_nome} className="h-full w-full text-slate-400" />
            </div>
          </button>
        </li>
      ))}
    </ul>
  )
}

function ListaAuditoria({ registros, fuso }: { registros: RegistroAuditoria[]; fuso: string }) {
  return (
    <ul className="mt-3 max-h-96 space-y-1 overflow-y-auto text-xs">
      {registros.map((linha) => (
        <li key={linha.id} className="flex flex-wrap gap-2 border-b border-slate-100 py-1.5">
          <span className="font-mono text-slate-400">{formatar(linha.criado_em, fuso)}</span>
          <span className="font-semibold text-slate-700">{linha.acao}</span>
          <span className="text-slate-500">{linha.usuario}</span>
          <span className="w-full break-all font-mono text-slate-400">{JSON.stringify(linha.detalhes)}</span>
        </li>
      ))}
    </ul>
  )
}

// ------------------------------------------------------------------ detalhe
function ModalDetalhe({
  drawId,
  fusoPadrao,
  aoFechar,
  aoAlterar,
}: {
  drawId: number | null
  fusoPadrao: string
  aoFechar: () => void
  aoAlterar: () => Promise<void>
}) {
  const [detalhe, setDetalhe] = useState<SorteioDetalhe | null>(null)
  const [erro, setErro] = useState('')
  const [anulando, setAnulando] = useState(false)
  const { pode } = useAuth()

  const carregar = useCallback(async (id: number) => {
    try {
      setDetalhe(await requisitar<SorteioDetalhe>(`/api/sorteios/${id}`))
      setErro('')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao carregar o detalhe')
    }
  }, [])

  useEffect(() => {
    setDetalhe(null)
    if (drawId !== null) void carregar(drawId)
  }, [drawId, carregar])

  async function alternarEntrega(s: Sorteio) {
    try {
      await requisitar(`/api/events/${s.evento_id}/sorteios/${s.id}/entrega`, {
        metodo: 'POST',
        corpo: { entregue: !s.entregue },
      })
      await carregar(s.id)
      await aoAlterar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao registrar a entrega')
    }
  }

  const s = detalhe?.sorteio
  const fuso = s?.evento_fuso ?? fusoPadrao

  return (
    <>
      <Modal
        titulo={s ? `Rodada ${s.rodada}` : 'Detalhes'}
        aberto={drawId !== null && !anulando}
        aoFechar={aoFechar}
        largura="max-w-2xl"
      >
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {!s || !detalhe ? (
          !erro && <Carregando />
        ) : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-start gap-4">
              <Foto url={s.ganhador_foto_url} nome={s.ganhador_nome} tamanho="h-16 w-16" />
              <div className="min-w-0 flex-1">
                <p className="text-lg font-semibold text-slate-900">{s.ganhador_nome}</p>
                <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-sm">
                  <dt className="text-slate-500">Matrícula</dt>
                  <dd className="font-mono">{s.ganhador_matricula}</dd>
                  <dt className="text-slate-500">Pulseira</dt>
                  <dd className="font-mono">{s.ganhador_pulseira ?? '—'}</dd>
                  <dt className="text-slate-500">Setor</dt>
                  <dd>{s.ganhador_setor || '—'}</dd>
                </dl>
              </div>
              <div className="flex flex-col items-end gap-1">
                <Etiqueta status={s.status} />
                <SituacaoEntrega s={s} />
              </div>
            </div>

            <div className="flex gap-3 rounded-lg border border-slate-200 p-3">
              <div className="h-20 w-20 shrink-0 overflow-hidden rounded bg-slate-100">
                <ImagemPremio url={s.premio_imagem_url} nome={s.premio_nome} className="h-full w-full text-slate-400" />
              </div>
              <dl className="grid flex-1 grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
                <dt className="text-slate-500">Prêmio</dt>
                <dd className="font-medium">
                  {s.premio_nome} · unidade {s.unidade_numero}
                </dd>
                <dt className="text-slate-500">Evento</dt>
                <dd>{s.evento_nome ?? '—'}</dd>
                <dt className="text-slate-500">Bloco</dt>
                <dd>{rotuloBloco(s)}</dd>
                <dt className="text-slate-500">Sorteado em</dt>
                <dd>
                  {formatar(s.criado_em, fuso)} por {s.criado_por}
                </dd>
                <dt className="text-slate-500">Elegíveis</dt>
                <dd>
                  {s.elegiveis_total} (posição sorteada: {detalhe.indice_sorteado + 1})
                </dd>
                {s.entregue_em && (
                  <>
                    <dt className="text-slate-500">Entrega</dt>
                    <dd>
                      {formatar(s.entregue_em, fuso)} por {s.entregue_por}
                    </dd>
                  </>
                )}
                {s.status === 'anulado' && (
                  <>
                    <dt className="text-slate-500">Anulação</dt>
                    <dd className="text-rose-700">
                      {formatar(s.anulado_em, fuso)} por {s.anulado_por} — {s.motivo_anulacao}
                    </dd>
                  </>
                )}
              </dl>
            </div>

            {s.status === 'valido' && (pode('confirmar_entrega') || pode('anular_resultado')) && (
              <div className="flex flex-wrap gap-2">
                {pode('confirmar_entrega') && (
                  <button
                    type="button"
                    className={s.entregue ? 'btn-neutro' : 'btn-primario'}
                    onClick={() => void alternarEntrega(s)}
                  >
                    {s.entregue ? 'Desfazer entrega' : 'Confirmar entrega'}
                  </button>
                )}
                {pode('anular_resultado') && (
                  <button type="button" className="btn-perigo ml-auto" onClick={() => setAnulando(true)}>
                    Anular
                  </button>
                )}
              </div>
            )}

            {detalhe.historico_da_unidade.length > 1 && (
              <section>
                <h3 className="mb-2 text-sm font-semibold text-slate-900">
                  Histórico desta unidade (anulações e resorteios)
                </h3>
                <ol className="space-y-1 text-sm">
                  {detalhe.historico_da_unidade.map((h) => (
                    <li
                      key={h.id}
                      className={`flex flex-wrap items-center gap-2 rounded px-2 py-1 ${
                        h.id === s.id ? 'bg-slate-100' : ''
                      }`}
                    >
                      <span className="text-xs text-slate-400">Rodada {h.rodada}</span>
                      <span className="font-medium">{h.ganhador_nome}</span>
                      <Etiqueta status={h.status} />
                      {h.motivo_anulacao && <span className="text-xs text-rose-700">{h.motivo_anulacao}</span>}
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {detalhe.auditoria.length > 0 && (
              <section>
                <h3 className="text-sm font-semibold text-slate-900">Auditoria</h3>
                <ListaAuditoria registros={detalhe.auditoria} fuso={fuso} />
              </section>
            )}
          </div>
        )}
      </Modal>

      <ModalAnulacao
        aberto={anulando}
        sorteio={s ?? null}
        eventId={s?.evento_id ?? 0}
        aoFechar={() => setAnulando(false)}
        aoConcluir={async () => {
          setAnulando(false)
          if (s) await carregar(s.id)
          await aoAlterar()
        }}
      />
    </>
  )
}
