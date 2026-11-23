import { useCallback, useEffect, useRef, useState } from 'react'
import { requisitar } from '../api'
import { useAuth } from '../auth'
import { Aviso, Carregando, Modal, Vazio } from '../componentes/ui'
import type {
  Credenciado,
  CredenciamentoResumo,
  PaginaCredenciados,
} from '../types'
import { usePainel } from './PainelLayout'
import Icone from '../componentes/Icone'

const SITUACOES = [
  { valor: 'todos', rotulo: 'Todos' },
  { valor: 'ausentes', rotulo: 'Ainda não chegaram' },
  { valor: 'presentes', rotulo: 'Presentes' },
  { valor: 'sem_pulseira', rotulo: 'Sem pulseira' },
]

export default function Credenciamento() {
  const { evento } = usePainel()
  const { pode } = useAuth()
  const base = `/api/events/${evento.id}/credenciamento`

  const [resumo, setResumo] = useState<CredenciamentoResumo | null>(null)
  const [pagina, setPagina] = useState<PaginaCredenciados | null>(null)
  const [texto, setTexto] = useState('')
  const [situacao, setSituacao] = useState('todos')
  const [numeroPagina, setNumeroPagina] = useState(1)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')
  const [pulseiraDe, setPulseiraDe] = useState<Credenciado | null>(null)
  const [liberarDe, setLiberarDe] = useState<Credenciado | null>(null)
  const sequencia = useRef(0)

  const carregarResumo = useCallback(async () => {
    setResumo(await requisitar<CredenciamentoResumo>(`${base}/resumo`))
  }, [base])

  const carregar = useCallback(async () => {
    const minha = ++sequencia.current
    setCarregando(true)
    try {
      const params = new URLSearchParams({ q: texto.trim(), situacao, pagina: String(numeroPagina) })
      const resposta = await requisitar<PaginaCredenciados>(`${base}/participantes?${params.toString()}`)
      if (minha === sequencia.current) {
        setPagina(resposta)
        setErro('')
      }
    } catch (e) {
      if (minha === sequencia.current) setErro(e instanceof Error ? e.message : 'Falha ao carregar')
    } finally {
      if (minha === sequencia.current) setCarregando(false)
    }
  }, [base, texto, situacao, numeroPagina])

  useEffect(() => {
    const espera = window.setTimeout(() => void carregar(), 300)
    return () => window.clearTimeout(espera)
  }, [carregar])

  useEffect(() => {
    void carregarResumo().catch(() => setResumo(null))
  }, [carregarResumo])

  async function alternarPresenca(p: Credenciado) {
    try {
      await requisitar(`/api/events/${evento.id}/participantes/${p.id}/presenca`, {
        metodo: 'POST',
        corpo: { presente: !p.presente },
      })
      await Promise.all([carregar(), carregarResumo()])
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao registrar presença')
    }
  }

  const auxilia = pode('auxiliar_credenciamento')
  const linkCadastro = `${window.location.origin}/cadastro/${evento.id}`

  return (
    <div className="space-y-4">
      <section className="cartao flex flex-wrap items-center gap-3 p-4">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-900">Autocadastro pelo celular</p>
          {evento.autocadastro_ativo ? (
            <p className="text-sm text-slate-600">
              Aberto em <span className="break-all font-mono text-marca-700">{linkCadastro}</span>
              {evento.autocadastro_confirma_presenca ? ' · confirma a presença ao concluir' : ''}
            </p>
          ) : (
            <p className="text-sm text-amber-800">
              Desligado. {pode('configurar_evento') ?'Ative em Configuração.' : 'Peça a um administrador para ativar.'}
            </p>
          )}
          <p className="mt-1 text-xs text-slate-500">
            O colaborador informa matrícula, nome e sobrenome, pulseira, foto e senha. Só vale o
            primeiro cadastro: para refazer, use “Liberar novo cadastro” depois de conferir o crachá.
          </p>
        </div>
      </section>

      {resumo && (
        <section className="cartao grid grid-cols-2 divide-borda sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
          {[
            ['Cadastrados', resumo.participantes],
            ['Presentes', resumo.presentes],
            ['Ainda não chegaram', resumo.ausentes],
            ['Com pulseira', resumo.com_pulseira],
            ['Sem pulseira', resumo.sem_pulseira],
            ['Cadastro feito', resumo.com_conta],
          ].map(([rotulo, valor]) => (
            <div key={String(rotulo)} className="border-b border-borda px-4 py-3 lg:border-b-0">
              <p className="text-xs text-slate-500">{rotulo as string}</p>
              <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">{valor as number}</p>
            </div>
          ))}
        </section>
      )}

      <section className="cartao grid gap-3 p-4 sm:grid-cols-[1fr_auto]">
        <div>
          <label htmlFor="busca-cred" className="sr-only">
            Buscar
          </label>
          <input
            id="busca-cred"
            type="search"
            autoComplete="off"
            className="campo py-2.5 text-base"
            placeholder="Nome, matrícula ou pulseira"
            value={texto}
            onChange={(e) => {
              setTexto(e.target.value)
              setNumeroPagina(1)
            }}
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {SITUACOES.map((s) => (
            <button
              key={s.valor}
              type="button"
              className={`aba ${situacao === s.valor ? 'aba-ativa' : ''}`}
              onClick={() => {
                setSituacao(s.valor)
                setNumeroPagina(1)
              }}
            >
              {s.rotulo}
            </button>
          ))}
        </div>
      </section>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {pagina === null ? (
        <Carregando />
      ) : pagina.itens.length === 0 ? (
        <Vazio titulo="Ninguém encontrado" />
      ) : (
        <ul className={`space-y-2 transition-opacity ${carregando ? 'opacity-60' : ''}`}>
          {pagina.itens.map((p) => (
            <li key={p.id} className="cartao flex flex-wrap items-center gap-3 p-3">
              <div className="h-12 w-12 shrink-0 overflow-hidden rounded-full bg-slate-200">
                {p.foto_url ? (
                  <img src={p.foto_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span className="flex h-full w-full items-center justify-center font-semibold text-slate-500">
                    {p.nome.slice(0, 1)}
                  </span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-900">{p.nome}</p>
                <p className="text-xs text-slate-500">
                  Matrícula <span className="font-mono">{p.matricula}</span>
                  {evento.modo_sorteio === 'numero_sorte' && p.numero_sorteio ? ` · Nº ${p.numero_sorteio}` : ''}
                  {p.setor ? ` · ${p.setor}` : ''}
                </p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {p.pulseira ? (
                    <span className="etiqueta bg-slate-100 font-mono text-slate-700">Pulseira {p.pulseira}</span>
                  ) : (
                    <span className="etiqueta bg-amber-100 text-amber-800">Sem pulseira</span>
                  )}
                  {p.tem_conta ? (
                    <span className="etiqueta bg-sky-100 text-sky-800">Cadastro feito</span>
                  ) : (
                    <span className="etiqueta bg-slate-100 text-slate-600">Sem cadastro</span>
                  )}
                  {!p.participando && <span className="etiqueta bg-rose-100 text-rose-800">Fora do sorteio</span>}
                </div>
              </div>
              {auxilia && (
                <div className="flex w-full shrink-0 flex-wrap gap-2 sm:w-auto">
                  {p.tem_conta && (
                    <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => setLiberarDe(p)}>
                      Liberar novo cadastro
                    </button>
                  )}
                  <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => setPulseiraDe(p)}>
                    {p.pulseira ? 'Trocar pulseira' : 'Entregar pulseira'}
                  </button>
                  <button
                    type="button"
                    className={p.presente ? 'btn-neutro px-3 py-1.5' : 'btn-primario px-3 py-1.5'}
                    onClick={() => void alternarPresenca(p)}
                  >
                    {p.presente ? <><Icone nome="check" className="h-4 w-4" /> Presente</> : 'Confirmar presença'}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {pagina && pagina.paginas > 1 && (
        <nav className="flex items-center justify-center gap-2" aria-label="Paginação">
          <button
            type="button"
            className="btn-neutro"
            disabled={numeroPagina <= 1}
            onClick={() => setNumeroPagina((n) => n - 1)}
          >
            <Icone nome="voltar" className="h-4 w-4" /> Anterior
          </button>
          <span className="text-sm text-slate-600">
            Página {numeroPagina} de {pagina.paginas}
          </span>
          <button
            type="button"
            className="btn-neutro"
            disabled={numeroPagina >= pagina.paginas}
            onClick={() => setNumeroPagina((n) => n + 1)}
          >
            Próxima <Icone nome="avancar" className="h-4 w-4" />
          </button>
        </nav>
      )}

      <ModalPulseira
        participante={pulseiraDe}
        base={base}
        aoFechar={() => setPulseiraDe(null)}
        aoSalvar={async () => {
          setPulseiraDe(null)
          await Promise.all([carregar(), carregarResumo()])
        }}
      />

      <ModalLiberar
        participante={liberarDe}
        base={base}
        aoFechar={() => setLiberarDe(null)}
        aoConcluir={async () => {
          setLiberarDe(null)
          await Promise.all([carregar(), carregarResumo()])
        }}
      />
    </div>
  )
}

/** Libera a pessoa para refazer o autocadastro (cadastro indevido ou senha esquecida). */
function ModalLiberar({
  participante,
  base,
  aoFechar,
  aoConcluir,
}: {
  participante: Credenciado | null
  base: string
  aoFechar: () => void
  aoConcluir: () => Promise<void>
}) {
  const [motivo, setMotivo] = useState('')
  const [conferido, setConferido] = useState(false)
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    setMotivo('')
    setConferido(false)
    setErro('')
  }, [participante])

  if (!participante) return null

  async function liberar(e: React.FormEvent) {
    e.preventDefault()
    if (!participante) return
    setEnviando(true)
    setErro('')
    try {
      await requisitar(`${base}/participantes/${participante.id}/liberar-cadastro`, {
        metodo: 'POST',
        corpo: { motivo: motivo.trim() },
      })
      await aoConcluir()
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Falha ao liberar o cadastro')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal titulo="Liberar novo cadastro" aberto aoFechar={aoFechar}>
      <form onSubmit={liberar} className="space-y-4">
        <p className="text-sm text-slate-600">
          <strong>{participante.nome}</strong> · matrícula{' '}
          <span className="font-mono">{participante.matricula}</span>
        </p>
        <Aviso tipo="atencao">
          A conta atual sai de todos os aparelhos e a pulseira registrada é liberada. Depois, a própria
          pessoa refaz o cadastro pelo celular (pulseira, foto e nova senha). Prêmios e histórico são
          mantidos.
        </Aviso>
        <div>
          <label className="rotulo" htmlFor="motivo-liberar">
            Motivo (fica registrado)
          </label>
          <input
            id="motivo-liberar"
            className="campo"
            required
            minLength={5}
            maxLength={300}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: esqueceu a senha; cadastro feito por outra pessoa"
          />
        </div>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4"
            checked={conferido}
            onChange={(e) => setConferido(e.target.checked)}
          />
          Conferi o crachá ou documento e é a própria pessoa.
        </label>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn-perigo" disabled={!conferido || motivo.trim().length < 5 || enviando}>
            {enviando ? 'Liberando...' : 'Liberar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ModalPulseira({
  participante,
  base,
  aoFechar,
  aoSalvar,
}: {
  participante: Credenciado | null
  base: string
  aoFechar: () => void
  aoSalvar: () => Promise<void>
}) {
  const [pulseira, setPulseira] = useState('')
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState('')

  useEffect(() => {
    setPulseira('')
    setMotivo('')
    setErro('')
  }, [participante])

  if (!participante) return null
  const troca = participante.pulseira !== null

  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    if (!participante) return
    setErro('')
    try {
      await requisitar(`${base}/participantes/${participante.id}/pulseira`, {
        metodo: 'POST',
        corpo: { pulseira: pulseira.trim(), motivo: troca ? motivo.trim() : null },
      })
      await aoSalvar()
    } catch (erroSalvar) {
      setErro(erroSalvar instanceof Error ? erroSalvar.message : 'Falha ao registrar a pulseira')
    }
  }

  return (
    <Modal titulo={troca ? 'Trocar pulseira' : 'Entregar pulseira'} aberto aoFechar={aoFechar}>
      <form onSubmit={salvar} className="space-y-4">
        <p className="text-sm text-slate-600">
          <strong>{participante.nome}</strong> · matrícula{' '}
          <span className="font-mono">{participante.matricula}</span>
          {troca && (
            <>
              <br />
              Pulseira atual: <span className="font-mono">{participante.pulseira}</span>
            </>
          )}
        </p>
        <div>
          <label className="rotulo" htmlFor="nova-pulseira">
            Número da pulseira
          </label>
          <input
            id="nova-pulseira"
            className="campo font-mono text-lg uppercase"
            required
            autoFocus
            autoComplete="off"
            maxLength={40}
            value={pulseira}
            onChange={(e) => setPulseira(e.target.value)}
          />
        </div>
        {troca && (
          <div>
            <label className="rotulo" htmlFor="motivo-troca">
              Motivo da troca (fica registrado)
            </label>
            <input
              id="motivo-troca"
              className="campo"
              required
              minLength={5}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Ex.: pulseira rasgou"
            />
          </div>
        )}
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn-primario">
            Salvar
          </button>
        </div>
      </form>
    </Modal>
  )
}
