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
import PortalQrCode from '../componentes/PortalQrCode'

/**
 * Cadastro pelo celular numa linha só (situação, link, Copiar link). O QR Code
 * abre ao clicar, para quem pode gerá-lo (Admin e Organizador).
 */
function CadastroPeloCelular() {
  const { evento } = usePainel()
  const { pode } = useAuth()
  const [aberto, setAberto] = useState(false)
  const [copiado, setCopiado] = useState(false)
  const link = `${window.location.origin}/cadastro/${evento.id}`
  const linkCurto = link.replace(/^https?:\/\//, '')
  const podeQr = pode('configurar_evento')

  const agora = Date.now()
  const antes = evento.autocadastro_inicio != null && agora < new Date(evento.autocadastro_inicio).getTime()
  const depois = evento.autocadastro_fim != null && agora > new Date(evento.autocadastro_fim).getTime()
  const situacao = !evento.autocadastro_ativo
    ? { rotulo: 'Desligado', classe: 'bg-slate-100 text-slate-600' }
    : antes || depois
      ? { rotulo: 'Fora do período', classe: 'bg-amber-50 text-amber-800' }
      : { rotulo: 'Aberto', classe: 'bg-emerald-50 text-emerald-700' }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(link)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    } catch {
      window.prompt('Copie o link do cadastro:', link)
    }
  }

  return (
    <section className="cartao px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Icone nome="celular" className="h-5 w-5 shrink-0 text-mallory-laranja" />
        <span className="text-sm font-semibold text-slate-900">Cadastro pelo celular</span>
        <span className={`etiqueta ${situacao.classe}`}>{situacao.rotulo}</span>
        {evento.autocadastro_ativo ? (
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-500" title={link}>
            {linkCurto}
          </span>
        ) : (
          <span className="min-w-0 flex-1 text-xs text-amber-800">
            {podeQr ? 'Ative em Configuração.' : 'Peça a um administrador para ativar.'}
          </span>
        )}
        <div className="flex gap-2">
          {evento.autocadastro_ativo && (
            <button type="button" className="btn-neutro h-8 px-3 text-xs" onClick={() => void copiar()}>
              <Icone nome="copiar" className="h-4 w-4" />
              {copiado ? 'Copiado!' : 'Copiar link'}
            </button>
          )}
          {podeQr && (
            <button
              type="button"
              className="btn-neutro h-8 px-3 text-xs"
              aria-expanded={aberto}
              onClick={() => setAberto((v) => !v)}
            >
              <Icone nome="scanner" className="h-4 w-4" />
              QR Code
              <Icone nome={aberto ? 'acima' : 'abaixo'} className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      {aberto && podeQr && (
        <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
          <PortalQrCode eventoId={evento.id} eventoNome={evento.nome} compacto />
          <p className="text-xs text-slate-500">
            O colaborador informa matrícula, data de nascimento e os 5 primeiros dígitos do CPF. O cadastro não
            confirma presença nem registra pulseira: isso é feito no check-in. Só vale o primeiro cadastro; para
            refazer, um administrador usa “Liberar novo cadastro” depois de conferir o crachá.
          </p>
        </div>
      )}
    </section>
  )
}

const SITUACOES = [
  { valor: 'todos', rotulo: 'Todos' },
  { valor: 'ausentes', rotulo: 'Ainda não chegaram' },
  { valor: 'presentes', rotulo: 'Presentes' },
  // { valor: 'sem_pulseira', rotulo: 'Sem pulseira' },
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

  // Equipe: só confirma e desfaz presença. Liberar novo cadastro é do admin.
  const auxilia = pode('auxiliar_credenciamento')
  const administra = pode('administrar_credenciamento')
  return (
    <div className="space-y-4">
      <CadastroPeloCelular />

      {resumo && (
        <section className="cartao grid grid-cols-2 divide-borda sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
          {[
            ['Cadastrados', resumo.participantes],
            ['Presentes', resumo.presentes],
            ['Ainda não chegaram', resumo.ausentes],
            ['Com pulseira', resumo.com_pulseira],
            // ['Sem pulseira', resumo.sem_pulseira],
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
            placeholder="Nome ou matrícula"
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
                  {/* "Sem pulseira" não aparece mais; só quem tem pulseira mostra o número. */}
                  {p.pulseira && (
                    <span className="etiqueta bg-slate-100 font-mono text-slate-700">Pulseira {p.pulseira}</span>
                  )}
                  {p.tem_conta ? (
                    <span className="etiqueta bg-sky-100 text-sky-800">Cadastro feito</span>
                  ) : (
                    <span className="etiqueta bg-slate-100 text-slate-600">Sem cadastro</span>
                  )}
                  {p.presente ? (
                    <span className="etiqueta bg-emerald-100 text-emerald-800">
                      <Icone nome="check" className="h-3.5 w-3.5" /> Presente
                    </span>
                  ) : (
                    <span className="etiqueta bg-slate-100 text-slate-600">Ainda não chegou</span>
                  )}
                  {!p.participando && <span className="etiqueta bg-rose-100 text-rose-800">Fora do sorteio</span>}
                </div>
              </div>
              {(auxilia || administra) && (
                <div className="flex w-full shrink-0 flex-wrap gap-2 sm:w-auto">
                  {/* Liberar novo cadastro: só o admin. */}
                  {administra && p.tem_conta && (
                    <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => setLiberarDe(p)}>
                      Liberar novo cadastro
                    </button>
                  )}
                  {auxilia &&
                    (p.presente ? (
                      <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => void alternarPresenca(p)}>
                        Desfazer presença
                      </button>
                    ) : (
                      <button type="button" className="btn-primario px-3 py-1.5" onClick={() => void alternarPresenca(p)}>
                        <Icone nome="check" className="h-4 w-4" /> Confirmar presença
                      </button>
                    ))}
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
