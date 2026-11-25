import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { requisitar } from '../api'
import { useAuth } from '../auth'
import Icone, { type NomeIcone } from '../componentes/Icone'
import {
  BoasVindasMallory,
  CabecalhoMallory,
  CartaoAcao,
  CLASSE_BOTAO_CABECALHO,
  FaixaDemo,
  RodapeMallory,
  TituloSecao,
} from '../componentes/Mallory'
import { Aviso, Carregando } from '../componentes/ui'
import type { Atendido, CheckinFeito, EventoRecepcao, PremioConsulta } from '../types'

type Tela = 'inicio' | 'checkin' | 'consulta'

// Evento escolhido neste aparelho (conveniência; sem storage, pergunta de novo).
const CHAVE_EVENTO = 'sorteio.recepcao_evento'

function lerEventoSalvo(): number | null {
  try {
    const valor = Number(localStorage.getItem(CHAVE_EVENTO))
    return Number.isInteger(valor) && valor > 0 ? valor : null
  } catch {
    return null
  }
}

function salvarEvento(id: number | null) {
  try {
    if (id) localStorage.setItem(CHAVE_EVENTO, String(id))
    else localStorage.removeItem(CHAVE_EVENTO)
  } catch {
    /* sem storage */
  }
}

function numero(n: number | null): string {
  return n === null ? '—' : String(n)
}

/**
 * Recepção pública (sem login, qualquer aparelho), na identidade Mallory.
 * Check-in confirma a presença pela matrícula; Consulta mostra o número do
 * sorteio e se a pessoa já foi sorteada (só depois da revelação no telão).
 */
export default function RecepcaoAtendimento() {
  // A tela é pública; com uma conta logada (Recepção, RH, Admin), mostra o atalho do credenciamento.
  const { pode, usuario } = useAuth()
  const [eventos, setEventos] = useState<EventoRecepcao[] | null>(null)
  const [eventoId, setEventoId] = useState<number | null>(lerEventoSalvo)
  const [tela, setTela] = useState<Tela>('inicio')
  const [erro, setErro] = useState('')

  useEffect(() => {
    requisitar<EventoRecepcao[]>('/api/recepcao/eventos', { autenticado: false })
      .then(setEventos)
      .catch((e) => setErro(e instanceof Error ? e.message : 'Falha ao carregar os eventos'))
  }, [])

  // Um único evento: entra direto. Evento salvo que não existe mais: esquece.
  const evento =
    eventos?.find((e) => e.id === eventoId) ?? (eventos?.length === 1 ? eventos[0] : undefined)

  function escolher(id: number | null) {
    salvarEvento(id)
    setEventoId(id)
    setTela('inicio')
  }

  return (
    <div className="flex min-h-full flex-col bg-mallory-fundo text-mallory-preto">
      <CabecalhoMallory secao="Recepção" icone="participantes" evento={evento?.nome}>
        {evento && eventos && eventos.length > 1 && (
          <button type="button" onClick={() => escolher(null)} className={CLASSE_BOTAO_CABECALHO}>
            Trocar evento
          </button>
        )}
        {evento && usuario && pode('acompanhar_credenciamento') ? (
          <Link to={`/eventos/${evento.id}/credenciamento`} className={CLASSE_BOTAO_CABECALHO} title="Voltar ao Credenciamento do evento">
            <Icone nome="voltar" className="h-4 w-4" />
            <span className="hidden sm:inline">Voltar ao evento</span>
          </Link>
        ) : (
          // Equipe logada sem evento aberto aqui (Recepção fechada ou evento não escolhido).
          usuario && pode('visualizar_evento') && (
            <Link to="/eventos" className={CLASSE_BOTAO_CABECALHO} title="Voltar aos eventos">
              <Icone nome="voltar" className="h-4 w-4" />
              <span className="hidden sm:inline">Voltar aos eventos</span>
            </Link>
          )
        )}
        <Link to="/login" className={CLASSE_BOTAO_CABECALHO} title="Tela inicial">
          <Icone nome="inicio" className="h-4 w-4" />
          <span className="hidden sm:inline">Início</span>
        </Link>
      </CabecalhoMallory>
      {evento?.demo && <FaixaDemo />}

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {!eventos && !erro && <Carregando texto="Carregando..." />}
        {eventos && eventos.length === 0 && (
          <Aviso tipo="atencao">
            A Recepção ainda não foi aberta pela organização. Ela é liberada em Configuração, no dia do evento.
          </Aviso>
        )}

        {eventos && eventos.length > 1 && !evento && (
          <section className="rec-painel mx-auto max-w-2xl p-6 sm:p-8">
            <TituloSecao titulo="Escolha o evento" subtitulo="Selecione o evento em que a recepção vai atender." />
            <ul className="mt-6 space-y-3">
              {eventos.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    onClick={() => escolher(e.id)}
                    className="rec-foco flex w-full items-center justify-between gap-3 rounded-xl border-2 border-slate-200 bg-white p-4 text-left transition-colors hover:border-mallory-laranja hover:bg-mallory-claro/50"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-mallory-claro text-mallory-acao">
                        <Icone nome="eventos" className="h-5 w-5" />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold">{e.nome}</span>
                        <span className="block truncate text-sm text-mallory-texto">
                          {e.empresa_nome}
                          {e.demo ? ' · demonstração' : ''}
                        </span>
                      </span>
                    </span>
                    <Icone nome="seta" className="h-5 w-5 shrink-0 text-mallory-acao" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {evento && tela === 'inicio' && (
          <>
            <BoasVindasMallory
              prefixo="Bem-vindo à Recepção"
              subtitulo="Selecione uma opção para iniciar o atendimento."
            />

            <div className="mt-6 grid gap-5 lg:grid-cols-2">
              <CartaoAcao
                variante="destaque"
                icone="cracha"
                titulo="Realizar Check-in"
                descricao="Localize o colaborador pela matrícula e confirme sua presença."
                acao="Iniciar Check-in"
                onClick={() => setTela('checkin')}
              />
              <CartaoAcao
                variante="claro"
                icone="busca"
                titulo="Consultar Participante"
                descricao="Consulte o número do sorteio, presença e prêmios."
                acao="Fazer Consulta"
                onClick={() => setTela('consulta')}
              />
            </div>
          </>
        )}
        {evento && tela === 'checkin' && <Checkin eventoId={evento.id} voltar={() => setTela('inicio')} />}
        {evento && tela === 'consulta' && <Consulta eventoId={evento.id} voltar={() => setTela('inicio')} />}
      </main>

      <RodapeMallory secao="Recepção" />
    </div>
  )
}

// ------------------------------------------------------------------ peças
function Cabecalho({ titulo, subtitulo, voltar }: { titulo: string; subtitulo: string; voltar: () => void }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <TituloSecao titulo={titulo} subtitulo={subtitulo} />
      <button type="button" className="rec-btn-neutro h-11 self-start text-sm" onClick={voltar}>
        <Icone nome="voltar" />
        Voltar ao início
      </button>
    </div>
  )
}

/** Caixa do número do sorteio, em destaque. */
function NumeroSorteio({
  valor,
  matricula = null,
  tamanho = 'grande',
}: {
  valor: number | null
  /** Modo faixa de matrículas: a matrícula é o número da sorte. */
  matricula?: string | null
  tamanho?: 'grande' | 'medio'
}) {
  return (
    <div
      className={`rounded-xl border-2 border-mallory-borda bg-mallory-claro text-center ${
        tamanho === 'grande' ? 'px-6 py-4' : 'px-4 py-2'
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-mallory-texto">
        {matricula ? 'Matrícula (número da sorte)' : 'Número do sorteio'}
      </p>
      <p
        className={`font-bold tabular-nums text-mallory-acao ${
          tamanho === 'grande' ? 'mt-1 text-5xl' : 'text-3xl'
        }`}
      >
        {matricula ?? numero(valor)}
      </p>
    </div>
  )
}

function Etiqueta({ tom, icone, children }: { tom: 'verde' | 'cinza' | 'ambar'; icone?: NomeIcone; children: ReactNode }) {
  const cores = {
    verde: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
    cinza: 'bg-slate-100 text-slate-700 ring-slate-200',
    ambar: 'bg-amber-50 text-amber-900 ring-amber-200',
  }[tom]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ring-1 ring-inset ${cores}`}>
      {icone && <Icone nome={icone} className="h-4 w-4" />}
      {children}
    </span>
  )
}

function Presenca({ presente }: { presente: boolean }) {
  return presente ? (
    <Etiqueta tom="verde" icone="check">
      Presença confirmada
    </Etiqueta>
  ) : (
    <Etiqueta tom="cinza">Sem check-in</Etiqueta>
  )
}

/** Situação no sorteio: prêmios já revelados no telão, ou "não sorteado". */
function Sorteado({ premios }: { premios: PremioConsulta[] }) {
  if (premios.length === 0) {
    return <Etiqueta tom="cinza">Não sorteado</Etiqueta>
  }
  return (
    <>
      {premios.map((p, i) => (
        <Etiqueta key={`${p.premio_nome}-${i}`} tom={p.entregue ? 'verde' : 'ambar'} icone="premios">
          Sorteado: {p.premio_nome}
          {p.bloco_numero ? ` · bloco ${String(p.bloco_numero).padStart(2, '0')}` : ''}
          {p.entregue ? ' · retirado' : ' · aguardando retirada'}
        </Etiqueta>
      ))}
    </>
  )
}

// ------------------------------------------------------------------ check-in
function Checkin({ eventoId, voltar }: { eventoId: number; voltar: () => void }) {
  const [matricula, setMatricula] = useState('')
  const [achado, setAchado] = useState<Atendido | null>(null)
  const [feito, setFeito] = useState<CheckinFeito | null>(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const campo = useRef<HTMLInputElement>(null)
  const proximo = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (feito) proximo.current?.focus()
    else if (!achado) campo.current?.focus()
  }, [achado, feito])

  function recomecar() {
    setMatricula('')
    setAchado(null)
    setFeito(null)
    setErro('')
  }

  async function localizar(e: React.FormEvent) {
    e.preventDefault()
    if (!matricula.trim()) return
    setErro('')
    setOcupado(true)
    try {
      setAchado(
        await requisitar<Atendido>(`/api/recepcao/${eventoId}/localizar`, {
          metodo: 'POST',
          corpo: { matricula: matricula.trim() },
          autenticado: false,
        }),
      )
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao localizar a matrícula')
    } finally {
      setOcupado(false)
    }
  }

  async function confirmar() {
    if (!achado) return
    setErro('')
    setOcupado(true)
    try {
      setFeito(
        await requisitar<CheckinFeito>(`/api/recepcao/${eventoId}/checkin`, {
          metodo: 'POST',
          corpo: { participante_id: achado.id },
          autenticado: false,
        }),
      )
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao confirmar o check-in')
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Cabecalho
        titulo="Check-in de Participantes"
        subtitulo="Digite a matrícula, confira os dados e confirme a presença."
        voltar={voltar}
      />

      {feito ? (
        <section className="rec-painel overflow-hidden text-center" aria-live="polite">
          <div className="h-1.5 bg-emerald-500" />
          <div className="p-6 sm:p-8">
            <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50 text-emerald-700 ring-8 ring-emerald-50/60">
              <Icone nome="check" className="h-9 w-9" />
            </span>
            <h2 className="mt-4 text-2xl font-bold">
              {feito.ja_estava_presente ? 'Check-in já estava confirmado' : 'Check-in confirmado'}
            </h2>
            <p className="mt-1 text-lg text-mallory-texto">{feito.nome}</p>
            <div className="mx-auto mt-6 max-w-xs">
              <NumeroSorteio valor={feito.numero_sorteio} matricula={feito.matricula_da_sorte} />
            </div>
            <button ref={proximo} type="button" className="rec-btn-primario mt-8 w-full" onClick={recomecar}>
              Próximo Check-in
              <Icone nome="seta" className="h-5 w-5" />
            </button>
          </div>
        </section>
      ) : achado ? (
        <section className="rec-painel overflow-hidden">
          <div className="h-1.5 bg-mallory-laranja" />
          <div className="p-6 sm:p-8">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-4">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-mallory-preto text-white">
                  <Icone nome="cracha" className="h-7 w-7" />
                </span>
                <dl className="min-w-0">
                  <dt className="sr-only">Nome</dt>
                  <dd className="text-2xl font-bold leading-tight">{achado.nome}</dd>
                  <dt className="sr-only">Matrícula</dt>
                  <dd className="mt-1 text-base text-mallory-texto">
                    Matrícula <span className="font-semibold text-mallory-preto">{achado.matricula}</span>
                  </dd>
                </dl>
              </div>
              <div className="sm:w-56">
                <NumeroSorteio valor={achado.numero_sorteio} matricula={achado.matricula_da_sorte} />
              </div>
            </div>

            <div className="mt-6 flex flex-wrap gap-2">
              <Presenca presente={achado.presente} />
              {achado.premios.length > 0 && <Sorteado premios={achado.premios} />}
            </div>

            {achado.presente && (
              <div className="mt-4">
                <Aviso tipo="info">O check-in desta pessoa já foi confirmado.</Aviso>
              </div>
            )}
            {!achado.participando && (
              <div className="mt-4">
                <Aviso tipo="atencao">
                  Esta pessoa não está participando do sorteio. Encaminhe à organização.
                </Aviso>
              </div>
            )}
            {erro && (
              <div className="mt-4">
                <Aviso tipo="erro">{erro}</Aviso>
              </div>
            )}

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              <button type="button" className="rec-btn-neutro" onClick={recomecar} disabled={ocupado}>
                Não é esta pessoa
              </button>
              <button type="button" className="rec-btn-primario" onClick={confirmar} disabled={ocupado} autoFocus>
                {ocupado ? 'Confirmando...' : 'Confirmar Check-in'}
                {!ocupado && <Icone nome="check" className="h-5 w-5" />}
              </button>
            </div>
          </div>
        </section>
      ) : (
        <form className="rec-painel p-6 sm:p-8" onSubmit={localizar}>
          <label className="mb-2 block text-base font-semibold" htmlFor="matricula">
            Matrícula do colaborador
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              ref={campo}
              id="matricula"
              className="rec-campo"
              autoComplete="off"
              inputMode="text"
              placeholder="Digite a matrícula"
              value={matricula}
              onChange={(e) => setMatricula(e.target.value)}
              maxLength={60}
              required
            />
            <button type="submit" className="rec-btn-primario h-14 px-7 sm:w-auto" disabled={ocupado}>
              {ocupado ? 'Buscando...' : 'Localizar'}
              {!ocupado && <Icone nome="busca" className="h-5 w-5" />}
            </button>
          </div>
          {erro && (
            <div className="mt-4">
              <Aviso tipo="erro">{erro}</Aviso>
            </div>
          )}
        </form>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ consulta
function Consulta({ eventoId, voltar }: { eventoId: number; voltar: () => void }) {
  const [termo, setTermo] = useState('')
  const [resultado, setResultado] = useState<Atendido[] | null>(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)

  async function consultar(e: React.FormEvent) {
    e.preventDefault()
    const q = termo.trim()
    if (q.length < 2) {
      setErro('Digite ao menos 2 caracteres do nome ou da matrícula.')
      return
    }
    setErro('')
    setOcupado(true)
    try {
      const params = new URLSearchParams({ q })
      setResultado(
        await requisitar<Atendido[]>(`/api/recepcao/${eventoId}/consulta?${params}`, { autenticado: false }),
      )
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha na consulta')
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Cabecalho
        titulo="Consultar Participante"
        subtitulo="Pesquise pelo nome ou pela matrícula."
        voltar={voltar}
      />
      <form className="rec-painel p-6 sm:p-8" onSubmit={consultar}>
        <label className="mb-2 block text-base font-semibold" htmlFor="consulta">
          Nome ou matrícula
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            id="consulta"
            className="rec-campo"
            autoComplete="off"
            autoFocus
            placeholder="Ex.: Maria Souza ou 00025"
            value={termo}
            onChange={(e) => setTermo(e.target.value)}
            maxLength={120}
          />
          <button type="submit" className="rec-btn-primario h-14 px-7 sm:w-auto" disabled={ocupado}>
            {ocupado ? 'Buscando...' : 'Consultar'}
            {!ocupado && <Icone nome="busca" className="h-5 w-5" />}
          </button>
        </div>
        {erro && (
          <div className="mt-4">
            <Aviso tipo="erro">{erro}</Aviso>
          </div>
        )}
      </form>

      {resultado && (
        <section className="mt-6" aria-live="polite">
          {resultado.length === 0 ? (
            <p className="rec-painel p-8 text-center text-base text-mallory-texto">
              Ninguém encontrado com esse nome ou matrícula.
            </p>
          ) : (
            <>
              <p className="mb-3 text-sm text-mallory-texto">
                {resultado.length === 1 ? '1 participante encontrado' : `${resultado.length} participantes encontrados`}
              </p>
              <ul className="space-y-3">
                {resultado.map((p) => (
                  <li
                    key={p.id}
                    className="rec-painel flex flex-col gap-4 border-l-4 border-mallory-laranja p-5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="text-lg font-bold leading-tight">{p.nome}</p>
                      <p className="mt-0.5 text-sm text-mallory-texto">
                        Matrícula <span className="font-semibold text-mallory-preto">{p.matricula}</span>
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Presenca presente={p.presente} />
                        <Sorteado premios={p.premios} />
                      </div>
                    </div>
                    <div className="sm:w-48 sm:shrink-0">
                      <NumeroSorteio valor={p.numero_sorteio} matricula={p.matricula_da_sorte} tamanho="medio" />
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          {resultado.length === 20 && (
            <p className="mt-3 text-sm text-mallory-texto">
              Mostrando os 20 primeiros. Digite mais do nome para refinar.
            </p>
          )}
        </section>
      )}
    </div>
  )
}
