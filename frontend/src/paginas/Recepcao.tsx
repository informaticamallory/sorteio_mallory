import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { baixarArquivo, enviarArquivo, requisitar } from '../api'
import { useAuth } from '../auth'
import Icone, { type NomeIcone } from '../componentes/Icone'
import { Aviso, ImagemPremio, Modal, Vazio } from '../componentes/ui'
import type {
  ColaboradorRecepcao,
  EntregasResumo,
  FiltrosEntregas,
  HistoricoEntrega,
  Pagina,
  Premiado,
  PaginaPremiados,
  PremioGanho,
} from '../types'
import { formatar } from './Historico'
import ModalAnulacao from './ModalAnulacao'
import { usePainel } from './PainelLayout'

const ESPERA_MS = 300
const ATUALIZAR_MS = 20000
/** Conteúdo do QR Code do Cartão da Sorte: evento e número da sorte. */
const QR_SORTE = /^MALLORY-SORTE:(\d+):(\d+)$/

function mensagem(e: unknown, padrao: string): string {
  return e instanceof Error ? e.message : padrao
}

function hojeNoFuso(fuso: string): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: fuso })
}

function bloco(numero: number | null | undefined): string {
  return numero ? `Bloco ${String(numero).padStart(2, '0')}` : 'Sem bloco'
}

/** Pessoa + prêmios a entregar (um ou vários) no atendimento atual. */
interface Atendimento {
  colaborador: Pick<ColaboradorRecepcao, 'id' | 'nome' | 'matricula' | 'pulseira' | 'foto_url' | 'numero_sorteio'>
  premios: Pick<PremioGanho, 'sorteio_id' | 'premio_nome' | 'unidade_numero' | 'bloco_numero'>[]
}

function Indicador({ icone, rotulo, valor, detalhe }: { icone: NomeIcone; rotulo: string; valor: string; detalhe?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-borda bg-white p-3 shadow-suave sm:p-4">
      <span className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-marca-50 text-marca-600 sm:flex">
        <Icone nome={icone} className="h-6 w-6" />
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-bold leading-none tabular-nums text-slate-900">{valor}</p>
        <p className="mt-1 truncate text-sm font-medium text-slate-700">{rotulo}</p>
        {detalhe && <p className="truncate text-xs text-slate-500">{detalhe}</p>}
      </div>
    </div>
  )
}

function Foto({ url, nome, tamanho = 'h-20 w-20' }: { url: string | null; nome: string; tamanho?: string }) {
  return (
    <div className={`${tamanho} shrink-0 overflow-hidden rounded-xl bg-slate-100`}>
      {url ? (
        <img src={url} alt={`Foto de ${nome}`} className="h-full w-full object-cover" />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-2xl font-semibold text-slate-400">
          {nome.slice(0, 1)}
        </span>
      )}
    </div>
  )
}

function Situacao({ entregue }: { entregue: boolean }) {
  return entregue ? (
    <span className="etiqueta shrink-0 bg-emerald-50 text-emerald-700">
      <Icone nome="check" className="h-3.5 w-3.5" /> Entregue
    </span>
  ) : (
    <span className="etiqueta shrink-0 bg-marca-50 text-marca-700">Pendente</span>
  )
}

/** Central de Entregas: indicadores, busca rápida, confirmação (uma ou várias), filtros e histórico. */
export default function Recepcao() {
  const { evento } = usePainel()
  const { pode } = useAuth()
  const base = `/api/events/${evento.id}/recepcao`
  const podeEntregar = pode('confirmar_entrega')
  const podeDesfazer = pode('desfazer_entrega')
  const podeAnular = pode('anular_resultado') // só admin
  // Nº da sorte só vale no modo padrão; na faixa de matrículas fica em branco.
  const modoNumero = evento.modo_sorteio === 'numero_sorte'

  const [resumo, setResumo] = useState<EntregasResumo | null>(null)
  const [texto, setTexto] = useState('')
  // QR Code lido (câmera ou leitor USB): a busca usa o conteúdo bruto e o
  // campo mostra só "QR nº ..." para o atendente.
  const [qr, setQr] = useState<{ bruto: string; numero: number } | null>(null)
  const [resultado, setResultado] = useState<ColaboradorRecepcao[] | null>(null)
  // Pessoa encontrada pelo QR mas sem prêmio (a busca normal só lista ganhadores).
  const [semPremio, setSemPremio] = useState<ColaboradorRecepcao[]>([])
  const [buscando, setBuscando] = useState(false)
  const [ativo, setAtivo] = useState(0)
  const [selecionados, setSelecionados] = useState<Record<number, number[]>>({})
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [atendimento, setAtendimento] = useState<Atendimento | null>(null)
  const [desfazendo, setDesfazendo] = useState<{ sorteio_id: number; premio: string; nome: string } | null>(null)
  // Foto da entrega tirada depois (ou trocada) e a foto aberta em tamanho grande.
  const [fotografando, setFotografando] = useState<{ sorteio_id: number; premio: string; nome: string; trocar: boolean } | null>(null)
  const [vendoFoto, setVendoFoto] = useState<{ url: string; legenda: string } | null>(null)
  const [anulando, setAnulando] = useState<{
    id: number
    rodada: number
    ganhador_nome: string
    premio_nome: string
    entregue: boolean
  } | null>(null)
  const [lendoQr, setLendoQr] = useState(false)
  const [versao, setVersao] = useState(0) // força recarga de lista e histórico
  const sequencia = useRef(0)
  const campo = useRef<HTMLInputElement | null>(null)

  const carregarResumo = useCallback(async () => {
    try {
      setResumo(await requisitar<EntregasResumo>(`${base}/resumo`))
    } catch {
      /* indicadores voltam na próxima atualização */
    }
  }, [base])

  useEffect(() => {
    void carregarResumo()
    const id = window.setInterval(() => void carregarResumo(), ATUALIZAR_MS)
    return () => window.clearInterval(id)
  }, [carregarResumo])

  /** Valor completo vindo do scanner da câmera. */
  function aplicarTexto(valor: string) {
    const lido = QR_SORTE.exec(valor.trim())
    if (lido) {
      setQr({ bruto: valor.trim(), numero: Number(lido[2]) })
      setTexto(`QR nº ${lido[2]}`)
    } else {
      setQr(null)
      setTexto(valor)
    }
  }

  const buscar = useCallback(async () => {
    // O leitor USB digita caractere a caractere: o QR completo só é
    // reconhecido aqui, depois da espera da busca.
    if (!qr) {
      const lido = QR_SORTE.exec(texto.trim())
      if (lido) {
        setQr({ bruto: texto.trim(), numero: Number(lido[2]) })
        setTexto(`QR nº ${lido[2]}`)
        return
      }
    }
    const termo = qr ? qr.bruto : texto.trim()
    if (termo.length < 2) {
      setResultado(null)
      setSemPremio([])
      return
    }
    const minha = ++sequencia.current
    setBuscando(true)
    try {
      const params = new URLSearchParams({ q: termo, somente_ganhadores: qr ? 'false' : 'true' })
      const lista = await requisitar<ColaboradorRecepcao[]>(`${base}/busca?${params.toString()}`)
      if (minha === sequencia.current) {
        setResultado(lista.filter((c) => c.premios.length > 0))
        setSemPremio(qr ? lista.filter((c) => c.premios.length === 0) : [])
        setAtivo(0)
        setErro('')
      }
    } catch (e) {
      if (minha === sequencia.current) {
        setResultado(null)
        setSemPremio([])
        setErro(mensagem(e, 'Falha na busca'))
      }
    } finally {
      if (minha === sequencia.current) setBuscando(false)
    }
  }, [base, texto, qr])

  useEffect(() => {
    const espera = window.setTimeout(() => void buscar(), ESPERA_MS)
    return () => window.clearTimeout(espera)
  }, [buscar])

  async function aposOperacao(texto: string) {
    setAviso(texto)
    setSelecionados({})
    setVersao((v) => v + 1)
    await Promise.all([buscar(), carregarResumo()])
    campo.current?.focus()
  }

  function alternar(colaborador: number, sorteio: number) {
    setSelecionados((atual) => {
      const lista = atual[colaborador] ?? []
      return { ...atual, [colaborador]: lista.includes(sorteio) ? lista.filter((x) => x !== sorteio) : [...lista, sorteio] }
    })
  }

  function abrirAtendimento(c: ColaboradorRecepcao, ids: number[]) {
    const premios = c.premios.filter((p) => ids.includes(p.sorteio_id) && !p.entregue)
    if (premios.length === 0) return
    setAviso('')
    setAtendimento({ colaborador: c, premios })
  }

  function teclado(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!resultado || resultado.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setAtivo((i) => Math.min(i + 1, resultado.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setAtivo((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && podeEntregar) {
      e.preventDefault()
      const c = resultado[ativo]
      if (c) abrirAtendimento(c, c.premios.filter((p) => !p.entregue).map((p) => p.sorteio_id))
    }
  }

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------ indicadores */}
      <section aria-label="Indicadores de entregas" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Indicador icone="premios" rotulo="Prêmios sorteados" valor={resumo ? String(resumo.sorteados) : '—'} detalhe="resultados válidos" />
        <Indicador icone="check" rotulo="Prêmios entregues" valor={resumo ? String(resumo.entregues) : '—'} />
        <Indicador icone="entregas" rotulo="Entregas pendentes" valor={resumo ? String(resumo.pendentes) : '—'} detalhe="aguardando retirada" />
        <Indicador icone="relatorio" rotulo="Percentual de entregas" valor={resumo ? `${resumo.percentual}%` : '—'} detalhe="entregues ÷ sorteados" />
      </section>

      {/* ------------------------------------------------ busca */}
      <section className="rounded-xl border border-borda bg-white p-4 shadow-suave sm:p-5">
        <label htmlFor="busca-entregas" className="flex items-center gap-2 text-base font-bold text-slate-900">
          <Icone nome="busca" className="h-5 w-5 text-marca-600" />
          Localizar ganhador
        </label>
        <div className="mt-3 flex gap-2">
          <div className="relative flex-1">
            <input
              id="busca-entregas"
              ref={campo}
              type="search"
              autoFocus
              autoComplete="off"
              className="campo h-14 pr-10 text-lg"
              placeholder="Nome, matrícula ou número da sorte"
              value={texto}
              onChange={(e) => {
                setQr(null)
                setTexto(e.target.value)
              }}
              onKeyDown={teclado}
              aria-describedby="busca-ajuda"
            />
            {buscando && (
              <span
                aria-label="Buscando"
                className="absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 animate-spin rounded-full border-2 border-slate-300 border-t-marca-600"
              />
            )}
          </div>
          <button
            type="button"
            className="inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-marca-600 text-white shadow-sm transition hover:bg-marca-700 focus:outline-none focus-visible:ring-4 focus-visible:ring-marca-200 active:scale-95"
            onClick={() => setLendoQr(true)}
            title="Escanear QR Code do Cartão da Sorte"
            aria-label="Escanear QR Code do Cartão da Sorte"
          >
            <Icone nome="scanner" className="h-7 w-7" />
          </button>
        </div>
        <p id="busca-ajuda" className="mt-2 text-xs text-slate-500">
          Sem acento e sem diferença de maiúsculas; matrícula com ou sem zeros. Use ↑ ↓ para escolher e Enter para entregar
          os pendentes. Leitor de QR Code (USB) também funciona: ele digita aqui. O QR Code não prova identidade: confira a
          pessoa.
        </p>
      </section>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {aviso && <Aviso tipo="sucesso">{aviso}</Aviso>}

      {semPremio.map((c) => (
        <section
          key={c.id}
          role="status"
          aria-label="Resultado da leitura do QR Code"
          className="flex flex-wrap items-center gap-4 rounded-xl border border-amber-200 bg-amber-50 p-4"
        >
          <Foto url={c.foto_url} nome={c.nome} tamanho="h-16 w-16" />
          <div className="min-w-0 flex-1">
            <p className="text-lg font-bold text-slate-900">{c.nome}</p>
            <p className="text-sm text-slate-600">
              Matrícula <span className="font-mono">{c.matricula}</span>
              {modoNumero && c.numero_sorteio != null && <> · nº da sorte <span className="font-mono">{c.numero_sorteio}</span></>}
              {c.pulseira && <> · pulseira <span className="font-mono">{c.pulseira}</span></>}
            </p>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-amber-800">
              <Icone nome="info" className="h-4 w-4" />
              Não tem prêmios neste evento{c.participando ? '' : ' (participação suspensa)'}.
            </p>
          </div>
        </section>
      ))}

      {resultado !== null &&
        (resultado.length === 0 ? (
          semPremio.length > 0 ? null : qr ? (
            <Vazio
              titulo={`Nenhum participante com o nº ${qr.numero}`}
              descricao="O QR Code foi lido, mas o número não existe neste evento. Confira o cartão ou busque pelo nome."
            />
          ) : (
            <Vazio titulo="Nenhum ganhador encontrado" descricao="Confira o nome, a matrícula, a pulseira ou o número da sorte." />
          )
        ) : (
          <ul className="space-y-3" aria-label="Ganhadores encontrados">
            {resultado.map((c, indice) => {
              const pendentes = c.premios.filter((p) => !p.entregue)
              const marcados = selecionados[c.id] ?? []
              return (
                <li
                  key={c.id}
                  className={`rounded-xl border bg-white p-4 shadow-suave ${indice === ativo ? 'border-marca-400 ring-2 ring-marca-200' : 'border-borda'}`}
                >
                  <div className="flex flex-wrap gap-4">
                    <Foto url={c.foto_url} nome={c.nome} tamanho="h-24 w-24" />
                    <div className="min-w-0 flex-1">
                      <p className="text-lg font-bold text-slate-900">{c.nome}</p>
                      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
                        <dt className="text-slate-500">Matrícula</dt>
                        <dd className="font-mono">{c.matricula}</dd>
                        <dt className="text-slate-500">Setor</dt>
                        <dd>{c.setor || '—'}</dd>
                        <dt className="text-slate-500">Nº da sorte</dt>
                        <dd className="font-mono">{(modoNumero && c.numero_sorteio) || '—'}</dd>
                      </dl>
                      <p className="mt-1 text-sm">
                        {pendentes.length > 0 ? (
                          <span className="font-semibold text-marca-700">{pendentes.length} prêmio(s) pendente(s)</span>
                        ) : (
                          <span className="font-semibold text-emerald-700">Todos os prêmios entregues</span>
                        )}
                      </p>
                    </div>
                  </div>

                  <ul className="mt-3 space-y-2">
                    {c.premios.map((p) => (
                      <li
                        key={p.sorteio_id}
                        className={`flex flex-wrap items-center gap-3 rounded-lg border p-2 ${p.entregue ? 'border-slate-200 bg-white' : 'border-marca-200 bg-marca-50/60'}`}
                      >
                        {!p.entregue && podeEntregar && pendentes.length > 1 && (
                          <input
                            type="checkbox"
                            className="h-5 w-5 accent-marca-600"
                            aria-label={`Selecionar ${p.premio_nome} unidade ${p.unidade_numero}`}
                            checked={marcados.includes(p.sorteio_id)}
                            onChange={() => alternar(c.id, p.sorteio_id)}
                          />
                        )}
                        <div className="h-12 w-12 shrink-0 overflow-hidden rounded bg-white">
                          <ImagemPremio url={p.premio_imagem_url} nome={p.premio_nome} className="h-full w-full text-slate-400" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold text-slate-900">{p.premio_nome}</p>
                          <p className="text-xs text-slate-500">
                            {bloco(p.bloco_numero)} · unidade {p.unidade_numero}
                            {p.quantidade_premio ? ` de ${p.quantidade_premio}` : ''}
                            {p.sorteado_em ? ` · sorteado em ${formatar(p.sorteado_em, evento.fuso_horario)}` : ''}
                          </p>
                          {p.entregue && (
                            <p className="text-xs text-emerald-700">
                              Entregue por {p.entregue_por} em {formatar(p.entregue_em, evento.fuso_horario)}
                            </p>
                          )}
                          {p.entregue && p.foto_entrega_url && (
                            <p className="text-xs text-slate-500">
                              Foto por {p.foto_entrega_por ?? '—'} em {formatar(p.foto_entrega_em ?? null, evento.fuso_horario)}
                            </p>
                          )}
                        </div>
                        {p.entregue && p.foto_entrega_url && (
                          <button
                            type="button"
                            className="h-12 w-12 shrink-0 overflow-hidden rounded-lg border-2 border-emerald-500"
                            title="Ver a foto da entrega"
                            onClick={() =>
                              setVendoFoto({
                                url: p.foto_entrega_url as string,
                                legenda: `${p.premio_nome} · ${c.nome}`,
                              })
                            }
                          >
                            <img src={p.foto_entrega_url} alt="Foto da entrega" className="h-full w-full object-cover" />
                          </button>
                        )}
                        <Situacao entregue={p.entregue} />
                        {p.entregue && podeEntregar && (
                          <button
                            type="button"
                            className="btn-neutro h-8 px-3 text-xs"
                            onClick={() =>
                              setFotografando({
                                sorteio_id: p.sorteio_id,
                                premio: p.premio_nome,
                                nome: c.nome,
                                trocar: !!p.foto_entrega_url,
                              })
                            }
                          >
                            <Icone nome="camera" className="h-4 w-4" />
                            {p.foto_entrega_url ? 'Trocar foto' : 'Foto da entrega'}
                          </button>
                        )}
                        {p.entregue
                          ? podeDesfazer && (
                              <button
                                type="button"
                                className="text-xs font-medium text-slate-600 underline"
                                onClick={() => setDesfazendo({ sorteio_id: p.sorteio_id, premio: p.premio_nome, nome: c.nome })}
                              >
                                Desfazer entrega
                              </button>
                            )
                          : (podeEntregar || podeAnular) && (
                              <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row">
                                {podeAnular && (
                                  <button
                                    type="button"
                                    className="btn-neutro text-rose-700 hover:bg-rose-50"
                                    title="Ganhador não veio ou desistiu: anula o resultado e a unidade volta para novo sorteio"
                                    onClick={() =>
                                      setAnulando({
                                        id: p.sorteio_id,
                                        rodada: p.rodada,
                                        ganhador_nome: c.nome,
                                        premio_nome: p.premio_nome,
                                        entregue: false,
                                      })
                                    }
                                  >
                                    Anular sorteio
                                  </button>
                                )}
                                {podeEntregar && (
                                  <button
                                    type="button"
                                    className="btn-primario"
                                    onClick={() => abrirAtendimento(c, [p.sorteio_id])}
                                  >
                                    Confirmar entrega
                                  </button>
                                )}
                              </div>
                            )}
                      </li>
                    ))}
                  </ul>
                  {podeEntregar && pendentes.length > 1 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="btn-primario h-11 flex-1 sm:flex-none"
                        disabled={marcados.length === 0}
                        onClick={() => abrirAtendimento(c, marcados)}
                      >
                        Confirmar selecionados ({marcados.length})
                      </button>
                      <button
                        type="button"
                        className="btn-neutro h-11"
                        onClick={() => abrirAtendimento(c, pendentes.map((p) => p.sorteio_id))}
                      >
                        Entregar todos os pendentes ({pendentes.length})
                      </button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        ))}

      <ListaPremiados
        base={base}
        fuso={evento.fuso_horario}
        versao={versao}
        aoAtender={(item) => setTexto(item.matricula)}
      />

      {pode('consultar_atendimentos') && (
        <HistoricoAtendimentos base={base} fuso={evento.fuso_horario} versao={versao} podeExportar={pode('exportar_resultados')} />
      )}

      <ModalEntrega
        atendimento={atendimento}
        base={base}
        modoNumero={modoNumero}
        aoFechar={() => setAtendimento(null)}
        aoConcluir={async (texto) => {
          setAtendimento(null)
          await aposOperacao(texto)
        }}
      />
      <ModalDesfazer
        alvo={desfazendo}
        eventId={evento.id}
        aoFechar={() => setDesfazendo(null)}
        aoConcluir={async (texto) => {
          setDesfazendo(null)
          await aposOperacao(texto)
        }}
      />
      <ModalFotoEntrega
        alvo={fotografando}
        base={base}
        aoFechar={() => setFotografando(null)}
        aoConcluir={async (texto) => {
          setFotografando(null)
          await aposOperacao(texto)
        }}
      />
      <Modal titulo="Foto da entrega" aberto={vendoFoto !== null} aoFechar={() => setVendoFoto(null)}>
        {vendoFoto && (
          <div className="space-y-2">
            <img src={vendoFoto.url} alt="Foto da entrega" className="mx-auto max-h-[70vh] rounded-lg object-contain" />
            <p className="text-center text-sm text-slate-600">{vendoFoto.legenda}</p>
          </div>
        )}
      </Modal>
      <ModalAnulacao
        aberto={anulando !== null}
        sorteio={anulando}
        eventId={evento.id}
        aoFechar={() => setAnulando(null)}
        aoConcluir={async () => {
          const alvo = anulando
          setAnulando(null)
          await aposOperacao(
            alvo
              ? `Sorteio de ${alvo.premio_nome} para ${alvo.ganhador_nome} anulado. A unidade voltou para ser sorteada de novo.`
              : 'Sorteio anulado.',
          )
        }}
      />
      {lendoQr && (
        <LeitorQr
          aoLer={(valor) => {
            setLendoQr(false)
            aplicarTexto(valor)
            campo.current?.focus()
          }}
          aoFechar={() => setLendoQr(false)}
        />
      )}
    </div>
  )
}

// ------------------------------------------------------------------ confirmação
function ModalEntrega({
  atendimento,
  base,
  modoNumero,
  aoFechar,
  aoConcluir,
}: {
  atendimento: Atendimento | null
  base: string
  modoNumero: boolean
  aoFechar: () => void
  aoConcluir: (mensagem: string) => Promise<void>
}) {
  const [pulseira, setPulseira] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)
  // Foto opcional da entrega (câmera do celular ou arquivo).
  const [foto, setFoto] = useState<File | null>(null)
  const [previaFoto, setPreviaFoto] = useState<string | null>(null)

  useEffect(() => {
    setPulseira('')
    setErro('')
    setFoto(null)
  }, [atendimento])

  useEffect(() => {
    if (!foto) {
      setPreviaFoto(null)
      return
    }
    const url = URL.createObjectURL(foto)
    setPreviaFoto(url)
    return () => URL.revokeObjectURL(url)
  }, [foto])

  if (!atendimento) return null
  const { colaborador, premios } = atendimento
  const temPulseira = colaborador.pulseira !== null

  async function confirmar(e: React.FormEvent) {
    e.preventDefault()
    setEnviando(true)
    setErro('')
    try {
      // A foto sobe antes; se falhar, nada é registrado e dá para tentar de novo ou tirar a foto.
      const fotoUrl = foto ? (await enviarArquivo<{ url: string }>('/api/uploads/imagem', foto)).url : null
      // Uma transação: ou todas as unidades, ou nenhuma (o backend revalida tudo).
      await requisitar(`${base}/entregar`, {
        metodo: 'POST',
        corpo: {
          sorteios: premios.map((p) => p.sorteio_id),
          pulseira_conferida: temPulseira ? pulseira.trim() : null,
          foto_url: fotoUrl,
        },
      })
      await aoConcluir(
        premios.length === 1
          ? `${premios[0].premio_nome} entregue a ${colaborador.nome}.`
          : `${premios.length} prêmios entregues a ${colaborador.nome}.`,
      )
    } catch (erroEntrega) {
      setErro(mensagem(erroEntrega, 'Falha ao registrar a entrega'))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal titulo={premios.length > 1 ? 'Conferir e entregar prêmios' : 'Conferir e entregar'} aberto aoFechar={aoFechar}>
      <form onSubmit={confirmar} className="space-y-4">
        <div className="flex gap-3">
          <Foto url={colaborador.foto_url} nome={colaborador.nome} />
          <div className="min-w-0">
            <p className="text-lg font-bold text-slate-900">{colaborador.nome}</p>
            <p className="text-sm text-slate-500">
              Matrícula <span className="font-mono">{colaborador.matricula}</span>
              {modoNumero && colaborador.numero_sorteio ? ` · nº da sorte ${colaborador.numero_sorteio}` : ''}
            </p>
          </div>
        </div>
        <div>
          <p className="rotulo">Resumo da entrega ({premios.length} unidade(s))</p>
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
            {premios.map((p) => (
              <li key={p.sorteio_id} className="flex justify-between gap-2 px-3 py-2">
                <span className="font-medium text-slate-900">{p.premio_nome}</span>
                <span className="shrink-0 text-slate-500">
                  {bloco(p.bloco_numero)} · un. {p.unidade_numero}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {temPulseira ? (
          <div>
            <label className="rotulo" htmlFor="pulseira-apresentada">
              Pulseira apresentada
            </label>
            <input
              id="pulseira-apresentada"
              className="campo h-12 font-mono text-lg uppercase"
              required
              autoFocus
              autoComplete="off"
              value={pulseira}
              onChange={(e) => setPulseira(e.target.value)}
              placeholder="Digite o número da pulseira"
            />
            <p className="mt-1 text-xs text-slate-500">
              O sistema confere com a pulseira cadastrada; se não bater, nada é registrado.
            </p>
          </div>
        ) : null}

        <div>
          <p className="rotulo">Foto da entrega (opcional)</p>
          {previaFoto ? (
            <div className="flex items-center gap-3">
              <img src={previaFoto} alt="Foto da entrega" className="h-20 w-20 rounded-lg border border-slate-200 object-cover" />
              <button type="button" className="text-sm font-medium text-rose-700 underline" onClick={() => setFoto(null)}>
                Remover foto
              </button>
            </div>
          ) : (
            <label className="btn-neutro inline-flex cursor-pointer">
              <Icone nome="camera" className="h-4 w-4" />
              Tirar ou escolher foto
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="sr-only"
                onChange={(e) => setFoto(e.target.files?.[0] ?? null)}
              />
            </label>
          )}
          <p className="mt-1 text-xs text-slate-500">Fica guardada no histórico da entrega.</p>
        </div>

        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" className="btn-neutro h-11" onClick={aoFechar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn-primario h-12 text-base uppercase tracking-wide"
            disabled={enviando || (temPulseira && !pulseira.trim())}
          >
            <Icone nome="check" className="h-5 w-5" />
            {enviando ? 'Registrando...' : premios.length > 1 ? `Confirmar ${premios.length} entregas` : 'Confirmar entrega'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ModalDesfazer({
  alvo,
  eventId,
  aoFechar,
  aoConcluir,
}: {
  alvo: { sorteio_id: number; premio: string; nome: string } | null
  eventId: number
  aoFechar: () => void
  aoConcluir: (mensagem: string) => Promise<void>
}) {
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    setMotivo('')
    setErro('')
  }, [alvo])

  if (!alvo) return null

  async function confirmar(e: React.FormEvent) {
    e.preventDefault()
    if (!alvo) return
    setEnviando(true)
    setErro('')
    try {
      await requisitar(`/api/events/${eventId}/sorteios/${alvo.sorteio_id}/entrega`, {
        metodo: 'POST',
        corpo: { entregue: false, motivo: motivo.trim() },
      })
      await aoConcluir(`Entrega de ${alvo.premio} para ${alvo.nome} desfeita. O registro original foi mantido.`)
    } catch (e) {
      setErro(mensagem(e, 'Falha ao desfazer'))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal titulo="Desfazer entrega" aberto aoFechar={aoFechar}>
      <form onSubmit={confirmar} className="space-y-4">
        <Aviso tipo="atencao">
          Desfazer a entrega de <strong>{alvo.premio}</strong> para <strong>{alvo.nome}</strong>? O prêmio volta a ficar
          pendente e o histórico guarda a entrega original, quem desfez e o motivo.
        </Aviso>
        <div>
          <label className="rotulo" htmlFor="motivo-desfazer">
            Justificativa (obrigatória)
          </label>
          <textarea
            id="motivo-desfazer"
            className="campo"
            rows={3}
            minLength={5}
            maxLength={500}
            required
            autoFocus
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: entregue para a pessoa errada"
          />
        </div>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn-perigo" disabled={enviando || motivo.trim().length < 5}>
            {enviando ? 'Desfazendo...' : 'Desfazer entrega'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

/** Foto tirada depois da entrega (ou troca da atual). Fica no registro da entrega. */
function ModalFotoEntrega({
  alvo,
  base,
  aoFechar,
  aoConcluir,
}: {
  alvo: { sorteio_id: number; premio: string; nome: string; trocar: boolean } | null
  base: string
  aoFechar: () => void
  aoConcluir: (mensagem: string) => Promise<void>
}) {
  const [foto, setFoto] = useState<File | null>(null)
  const [previa, setPrevia] = useState<string | null>(null)
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    setFoto(null)
    setErro('')
  }, [alvo])

  useEffect(() => {
    if (!foto) {
      setPrevia(null)
      return
    }
    const url = URL.createObjectURL(foto)
    setPrevia(url)
    return () => URL.revokeObjectURL(url)
  }, [foto])

  if (!alvo) return null

  async function salvar() {
    if (!alvo || !foto) return
    setEnviando(true)
    setErro('')
    try {
      const { url } = await enviarArquivo<{ url: string }>('/api/uploads/imagem', foto)
      await requisitar(`${base}/entregas/${alvo.sorteio_id}/foto`, { metodo: 'POST', corpo: { foto_url: url } })
      await aoConcluir(`Foto da entrega de ${alvo.premio} para ${alvo.nome} registrada.`)
    } catch (e) {
      setErro(mensagem(e, 'Falha ao registrar a foto'))
    } finally {
      setEnviando(false)
    }
  }

  const escolher = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFoto(e.target.files?.[0] ?? null)
    e.target.value = ''
  }

  return (
    <Modal titulo={alvo.trocar ? 'Trocar foto da entrega' : 'Foto da entrega'} aberto aoFechar={aoFechar}>
      <div className="space-y-4">
        <p className="text-sm text-slate-600">
          {alvo.premio} · <strong className="text-slate-900">{alvo.nome}</strong>
        </p>
        {previa ? (
          <div className="space-y-2 text-center">
            <img src={previa} alt="Prévia da foto" className="mx-auto max-h-72 rounded-lg border border-slate-200 object-contain" />
            <button type="button" className="text-sm font-medium text-rose-700 underline" onClick={() => setFoto(null)}>
              Tirar outra
            </button>
          </div>
        ) : (
          <div className="space-y-2 rounded-xl border-2 border-dashed border-slate-300 p-4 text-center">
            <Icone nome="camera" className="mx-auto h-8 w-8 text-slate-400" />
            <label className="btn-primario flex w-full cursor-pointer justify-center">
              Abrir câmera
              <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={escolher} />
            </label>
            <label className="btn-neutro flex w-full cursor-pointer justify-center">
              Escolher da galeria
              <input type="file" accept="image/*" className="sr-only" onChange={escolher} />
            </label>
          </div>
        )}
        <p className="text-xs text-slate-500">
          JPG ou PNG, até 5 MB. Fica registrada com quem tirou e quando
          {alvo.trocar ? '; a foto anterior continua no registro.' : '.'}
        </p>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="button" className="btn-primario" disabled={!foto || enviando} onClick={() => void salvar()}>
            {enviando ? 'Salvando...' : 'Salvar foto'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ------------------------------------------------------------------ lista com filtros
function ListaPremiados({
  base,
  fuso,
  versao,
  aoAtender,
}: {
  base: string
  fuso: string
  versao: number
  aoAtender: (item: Premiado) => void
}) {
  const [opcoes, setOpcoes] = useState<FiltrosEntregas | null>(null)
  const [situacao, setSituacao] = useState('pendentes')
  const [blocoId, setBlocoId] = useState('')
  const [premioId, setPremioId] = useState('')
  const [periodo, setPeriodo] = useState('')
  const [de, setDe] = useState('')
  const [ate, setAte] = useState('')
  const [operadorId, setOperadorId] = useState('')
  const [pagina, setPagina] = useState(1)
  const [dados, setDados] = useState<PaginaPremiados | null>(null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    requisitar<FiltrosEntregas>(`${base}/filtros`).then(setOpcoes).catch(() => setOpcoes(null))
  }, [base, versao])

  // Operador = quem entregou: não existe nos pendentes, então o filtro some ali.
  const comOperador = situacao !== 'pendentes'

  const parametros = useMemo(() => {
    const p = new URLSearchParams({ situacao, pagina: String(pagina), por_pagina: '12' })
    if (blocoId) p.set('bloco_id', blocoId)
    if (premioId) p.set('premio_id', premioId)
    if (operadorId && situacao !== 'pendentes') p.set('operador_id', operadorId)
    if (periodo === 'hoje') {
      const hoje = hojeNoFuso(fuso)
      p.set('de', hoje)
      p.set('ate', hoje)
    } else if (periodo === 'data' && de) {
      p.set('de', de)
      p.set('ate', de)
    } else if (periodo === 'intervalo') {
      if (de) p.set('de', de)
      if (ate) p.set('ate', ate)
    }
    return p.toString()
  }, [situacao, pagina, blocoId, premioId, operadorId, periodo, de, ate, fuso])

  useEffect(() => {
    let vivo = true
    requisitar<PaginaPremiados>(`${base}/premiados?${parametros}`)
      .then((d) => vivo && (setDados(d), setErro('')))
      .catch((e) => vivo && setErro(mensagem(e, 'Falha ao carregar a lista')))
    return () => {
      vivo = false
    }
  }, [base, parametros, versao])

  useEffect(() => setPagina(1), [situacao, blocoId, premioId, operadorId, periodo, de, ate])

  function limpar() {
    setBlocoId('')
    setPremioId('')
    setPeriodo('')
    setDe('')
    setAte('')
    setOperadorId('')
  }

  function mudarSituacao(valor: string) {
    setSituacao(valor)
    if (valor === 'pendentes') setOperadorId('')
  }

  function mudarPeriodo(valor: string) {
    setPeriodo(valor)
    if (!valor || valor === 'hoje') {
      setDe('')
      setAte('')
    }
  }

  const filtrosAtivos = [blocoId, premioId, periodo, comOperador ? operadorId : ''].filter(Boolean).length
  const contagem = dados?.contagem
  // O período vale sobre a data da entrega na aba "Entregues" e do sorteio nas demais.
  const rotuloData = situacao === 'entregues' ? 'Data da entrega' : 'Data do sorteio'
  const quando = situacao === 'entregues' ? 'Entrega' : 'Sorteio'

  return (
    <section className="rounded-xl border border-borda bg-white p-4 shadow-suave sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
          <Icone nome="premios" className="h-5 w-5 text-marca-600" />
          Prêmios sorteados
        </h2>
        <div role="tablist" aria-label="Situação" className="flex w-full gap-0.5 rounded-lg bg-slate-100 p-1 sm:w-auto">
          {SITUACOES.map(([valor, rotulo]) => {
            const ativo = situacao === valor
            const n = contagem?.[valor]
            return (
              <button
                key={valor}
                type="button"
                role="tab"
                aria-selected={ativo}
                onClick={() => mudarSituacao(valor)}
                className={`flex-1 whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors sm:flex-none ${
                  ativo
                    ? 'bg-white font-semibold text-marca-700 shadow-sm ring-1 ring-marca-200'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {rotulo}
                {n !== undefined && (
                  <span className={`ml-1.5 tabular-nums ${ativo ? 'text-marca-600' : 'text-slate-400'}`}>{n}</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {/* Celular: chips lado a lado em colunas iguais (2x2 quando há Operador). */}
        <div className={`grid w-full gap-2 sm:flex sm:w-auto sm:flex-wrap ${comOperador ? 'grid-cols-2' : 'grid-cols-3'}`}>
          <FiltroChip rotulo="Bloco" valor={blocoId} aoMudar={setBlocoId} opcoes={opcoes?.blocos ?? []} />
          <FiltroChip rotulo="Prêmio" valor={premioId} aoMudar={setPremioId} opcoes={opcoes?.premios ?? []} />
          <FiltroChip
            rotulo="Data"
            descricao={rotuloData}
            valor={periodo}
            aoMudar={mudarPeriodo}
            opcoes={[
              { id: 'hoje', nome: `${quando}: hoje` },
              { id: 'data', nome: `${quando}: dia` },
              { id: 'intervalo', nome: `${quando}: intervalo` },
            ]}
          />
          {comOperador && (
            <FiltroChip rotulo="Operador" valor={operadorId} aoMudar={setOperadorId} opcoes={opcoes?.operadores ?? []} />
          )}
        </div>
        {(periodo === 'data' || periodo === 'intervalo') && (
          <span className="flex items-center gap-1.5">
            <input
              type="date"
              className="campo h-8 w-auto rounded-full px-3"
              aria-label={periodo === 'data' ? 'Dia' : 'De'}
              value={de}
              onChange={(e) => setDe(e.target.value)}
            />
            {periodo === 'intervalo' && (
              <>
                <span className="text-xs text-slate-500">até</span>
                <input
                  type="date"
                  className="campo h-8 w-auto rounded-full px-3"
                  aria-label="Até"
                  value={ate}
                  onChange={(e) => setAte(e.target.value)}
                />
              </>
            )}
          </span>
        )}
        {filtrosAtivos > 0 && (
          <button type="button" className="px-1 text-sm font-semibold text-marca-700 hover:underline" onClick={limpar}>
            Limpar
          </button>
        )}
        <span className="ml-auto text-xs text-slate-500">
          {dados ? `${dados.total} resultado${dados.total === 1 ? '' : 's'}` : '...'}
        </span>
      </div>

      {erro && <div className="mt-3"><Aviso tipo="erro">{erro}</Aviso></div>}
      {dados && dados.itens.length === 0 && (
        <p className="mt-6 text-center text-sm text-slate-500">
          {situacao === 'pendentes' && filtrosAtivos === 0 ? 'Nenhuma entrega pendente. 🎉' : 'Nenhum prêmio com esses filtros.'}
        </p>
      )}
      {dados && dados.itens.length > 0 && (
        <div className="mt-3">
          <div
            className={`hidden gap-3 px-2 pb-1.5 text-xs font-medium text-slate-400 lg:grid ${COLUNAS}`}
            aria-hidden="true"
          >
            <span />
            <span>Ganhador</span>
            <span>Prêmio</span>
            <span>Bloco</span>
            <span>{situacao === 'entregues' ? 'Entrega' : 'Sorteio'}</span>
            <span />
          </div>
          <ul className="divide-y divide-slate-200 border-y border-slate-200">
            {dados.itens.map((item) => (
              <LinhaPremiado key={item.sorteio_id} item={item} fuso={fuso} aoAtender={aoAtender} />
            ))}
          </ul>
        </div>
      )}
      {dados && dados.paginas > 1 && (
        <Paginacao pagina={dados.pagina} paginas={dados.paginas} aoMudar={setPagina} />
      )}
    </section>
  )
}

const SITUACOES = [
  ['pendentes', 'Pendentes'],
  ['entregues', 'Entregues'],
  ['todos', 'Todos'],
] as const

/** Colunas da lista no computador: foto, ganhador, prêmio, bloco, data, situação. */
const COLUNAS = 'lg:grid-cols-[2.75rem_minmax(0,1.6fr)_minmax(0,1.3fr)_5rem_6.5rem_7rem]'

/** Filtro em forma de chip: um select nativo (bom no toque) que fica laranja quando ativo. */
function FiltroChip({
  rotulo,
  descricao,
  valor,
  opcoes,
  aoMudar,
}: {
  rotulo: string
  /** Nome completo para leitores de tela (o chip mostra o rótulo curto). */
  descricao?: string
  valor: string
  opcoes: { id: number | string; nome: string }[]
  aoMudar: (valor: string) => void
}) {
  const ativo = valor !== ''
  const nome = descricao ?? rotulo
  return (
    // Celular: ocupa a coluna da grade; computador: do tamanho do texto.
    <span
      className={`relative flex min-w-0 items-center rounded-full border text-sm transition-colors sm:inline-flex sm:max-w-full ${
        ativo ? 'border-marca-300 bg-marca-50 text-marca-800' : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400'
      }`}
      title={nome}
    >
      <select
        aria-label={nome}
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
        className={`w-full min-w-0 flex-1 cursor-pointer appearance-none truncate rounded-full bg-transparent py-1.5 pl-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-marca-400 sm:w-auto sm:max-w-[15rem] sm:flex-none sm:[field-sizing:content] ${
          ativo ? 'pr-1 font-medium' : 'pr-8'
        }`}
      >
        <option value="">{rotulo}</option>
        {opcoes.map((o) => (
          <option key={o.id} value={String(o.id)}>
            {o.nome}
          </option>
        ))}
      </select>
      {ativo ? (
        <button
          type="button"
          aria-label={`Remover filtro: ${nome}`}
          onClick={() => aoMudar('')}
          className="mr-1 shrink-0 rounded-full p-1 text-marca-700 hover:bg-marca-100"
        >
          <Icone nome="fechar" className="h-3.5 w-3.5" />
        </button>
      ) : (
        <Icone nome="abaixo" className="pointer-events-none absolute right-2.5 h-4 w-4 text-slate-400" />
      )}
    </span>
  )
}

/** "25/11, 14:47" no fuso do evento (o backend grava UTC). */
function dataCurta(data: string | null, fuso: string): string {
  if (!data) return '—'
  return new Date(`${data}Z`).toLocaleString('pt-BR', {
    timeZone: fuso,
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function LinhaPremiado({
  item,
  fuso,
  aoAtender,
}: {
  item: Premiado
  fuso: string
  aoAtender: (item: Premiado) => void
}) {
  const identificacao = [item.matricula, item.setor].filter(Boolean).join(' · ')
  const premio = `${item.premio_nome} · un. ${item.unidade_numero}`
  const quando = dataCurta(item.entregue ? item.entregue_em : item.sorteado_em, fuso)
  return (
    <li>
      <button
        type="button"
        onClick={() => aoAtender(item)}
        className={`grid w-full grid-cols-[2.75rem_minmax(0,1fr)_auto] items-center gap-3 px-2 py-2.5 text-left transition-colors hover:bg-marca-50/50 ${COLUNAS}`}
        title="Abrir o atendimento deste ganhador"
      >
        <Foto url={item.foto_url} nome={item.nome} tamanho="h-11 w-11" />
        <span className="min-w-0">
          <span className="block truncate font-semibold text-slate-900">{item.nome}</span>
          <span className="block truncate text-xs text-slate-500 lg:hidden">
            {premio} · {bloco(item.bloco_numero)}
          </span>
          <span className="block truncate text-xs text-slate-400 lg:text-slate-500">
            {identificacao}
            <span className="lg:hidden"> · {quando}</span>
          </span>
          {item.entregue && item.entregue_por && (
            <span className="block truncate text-xs text-slate-400">Entregue por {item.entregue_por}</span>
          )}
        </span>
        <span className="hidden min-w-0 truncate text-sm text-slate-700 lg:block">{premio}</span>
        <span className="hidden text-sm text-slate-600 lg:block">{bloco(item.bloco_numero)}</span>
        <span className="hidden text-sm tabular-nums text-slate-600 lg:block">{quando}</span>
        <span className="flex items-center justify-end gap-1">
          {item.entregue && item.tem_foto_entrega && (
            <span title="Entrega com foto" className="text-emerald-600">
              <Icone nome="camera" className="h-4 w-4" />
              <span className="sr-only">Entrega com foto</span>
            </span>
          )}
          <Situacao entregue={item.entregue} />
          <Icone nome="avancar" className="hidden h-4 w-4 text-slate-300 lg:block" />
        </span>
      </button>
    </li>
  )
}

function Paginacao({ pagina, paginas, aoMudar }: { pagina: number; paginas: number; aoMudar: (p: number) => void }) {
  return (
    <div className="mt-3 flex items-center justify-center gap-2 text-sm">
      <button type="button" className="btn-neutro px-3 py-1.5" disabled={pagina <= 1} onClick={() => aoMudar(pagina - 1)}>
        Anterior
      </button>
      <span className="text-slate-600">
        Página {pagina} de {paginas}
      </span>
      <button type="button" className="btn-neutro px-3 py-1.5" disabled={pagina >= paginas} onClick={() => aoMudar(pagina + 1)}>
        Próxima
      </button>
    </div>
  )
}

// ------------------------------------------------------------------ histórico
function HistoricoAtendimentos({
  base,
  fuso,
  versao,
  podeExportar,
}: {
  base: string
  fuso: string
  versao: number
  podeExportar: boolean
}) {
  const [opcoes, setOpcoes] = useState<FiltrosEntregas | null>(null)
  const [acao, setAcao] = useState('todas')
  const [de, setDe] = useState('')
  const [ate, setAte] = useState('')
  const [operadorId, setOperadorId] = useState('')
  const [blocoId, setBlocoId] = useState('')
  const [premioId, setPremioId] = useState('')
  const [pagina, setPagina] = useState(1)
  const [dados, setDados] = useState<Pagina<HistoricoEntrega> | null>(null)
  const [detalhe, setDetalhe] = useState<HistoricoEntrega | null>(null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    requisitar<FiltrosEntregas>(`${base}/filtros`).then(setOpcoes).catch(() => setOpcoes(null))
  }, [base, versao])

  const filtros = useMemo(() => {
    const p = new URLSearchParams({ acao })
    if (de) p.set('de', de)
    if (ate) p.set('ate', ate)
    if (operadorId) p.set('operador_id', operadorId)
    if (blocoId) p.set('bloco_id', blocoId)
    if (premioId) p.set('premio_id', premioId)
    return p.toString()
  }, [acao, de, ate, operadorId, blocoId, premioId])

  useEffect(() => setPagina(1), [filtros])

  useEffect(() => {
    let vivo = true
    requisitar<Pagina<HistoricoEntrega>>(`${base}/historico?${filtros}&pagina=${pagina}&por_pagina=10`)
      .then((d) => vivo && (setDados(d), setErro('')))
      .catch((e) => vivo && setErro(mensagem(e, 'Falha ao carregar o histórico')))
    return () => {
      vivo = false
    }
  }, [base, filtros, pagina, versao])

  return (
    <section className="rounded-xl border border-borda bg-white p-4 shadow-suave sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
          <Icone nome="historico" className="h-5 w-5 text-marca-600" />
          Histórico de atendimentos
        </h2>
        {podeExportar && (
          <button
            type="button"
            className="btn-neutro px-3 py-1.5"
            onClick={() => void baixarArquivo(`${base}/historico/export.csv?${filtros}`, 'entregas.csv')}
          >
            <Icone nome="baixar" className="h-4 w-4" />
            Exportar CSV
          </button>
        )}
      </div>
      <details className="mt-3 rounded-lg border border-slate-200 p-3">
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">Filtros do histórico</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <select className="campo" aria-label="Situação do atendimento" value={acao} onChange={(e) => setAcao(e.target.value)}>
            <option value="todas">Todas</option>
            <option value="confirmadas">Entregas confirmadas</option>
            <option value="desfeitas">Entregas desfeitas</option>
          </select>
          <input type="date" className="campo" aria-label="De" value={de} onChange={(e) => setDe(e.target.value)} />
          <input type="date" className="campo" aria-label="Até" value={ate} onChange={(e) => setAte(e.target.value)} />
          <select className="campo" aria-label="Operador" value={operadorId} onChange={(e) => setOperadorId(e.target.value)}>
            <option value="">Todos os operadores</option>
            {opcoes?.operadores.map((o) => (
              <option key={o.id} value={o.id}>
                {o.nome}
              </option>
            ))}
          </select>
          <select className="campo" aria-label="Bloco" value={blocoId} onChange={(e) => setBlocoId(e.target.value)}>
            <option value="">Todos os blocos</option>
            {opcoes?.blocos.map((b) => (
              <option key={b.id} value={b.id}>
                {b.nome}
              </option>
            ))}
          </select>
          <select className="campo" aria-label="Prêmio" value={premioId} onChange={(e) => setPremioId(e.target.value)}>
            <option value="">Todos os produtos</option>
            {opcoes?.premios.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </div>
      </details>

      {erro && <div className="mt-3"><Aviso tipo="erro">{erro}</Aviso></div>}
      {dados && dados.itens.length === 0 && <p className="mt-4 text-center text-sm text-slate-500">Nenhum atendimento registrado.</p>}
      {/* Celular: cartões empilhados. */}
      {dados && dados.itens.length > 0 && (
        <ul className="mt-3 space-y-2 sm:hidden">
          {dados.itens.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                onClick={() => setDetalhe(h)}
                className="w-full rounded-lg border border-slate-200 p-3 text-left text-sm"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-slate-500">{formatar(h.criado_em, fuso)}</span>
                  {h.acao === 'entrega_registrada' ? (
                    <span className="etiqueta shrink-0 bg-emerald-50 text-emerald-700">Entregue</span>
                  ) : (
                    <span className="etiqueta shrink-0 bg-rose-50 text-rose-700">Entrega desfeita</span>
                  )}
                </span>
                <span className="mt-1 block font-semibold text-slate-900">{h.participante ?? 'Resultado removido'}</span>
                <span className="block text-xs text-slate-500">
                  {h.premio ?? '—'}
                  {h.unidade ? ` (un. ${h.unidade})` : ''} · {bloco(h.bloco_numero)} · por {h.atendente || '—'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {dados && dados.itens.length > 0 && (
        <div className="mt-3 hidden overflow-x-auto sm:block">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="py-2 pr-3">Data e hora</th>
                <th className="py-2 pr-3">Colaborador</th>
                <th className="py-2 pr-3">Prêmio</th>
                <th className="py-2 pr-3">Bloco</th>
                <th className="py-2 pr-3">Situação</th>
                <th className="py-2 pr-3">Operador</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {dados.itens.map((h) => (
                <tr key={h.id}>
                  <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs text-slate-500">{formatar(h.criado_em, fuso)}</td>
                  <td className="py-2 pr-3">
                    <span className="font-medium text-slate-900">{h.participante ?? 'Resultado removido'}</span>
                    <span className="block font-mono text-xs text-slate-500">{h.matricula}</span>
                  </td>
                  <td className="py-2 pr-3">
                    {h.premio}
                    {h.unidade ? <span className="text-slate-500"> (un. {h.unidade})</span> : null}
                  </td>
                  <td className="py-2 pr-3 text-slate-600">{h.bloco_numero ? String(h.bloco_numero).padStart(2, '0') : '—'}</td>
                  <td className="py-2 pr-3">
                    {h.acao === 'entrega_registrada' ? (
                      <span className="etiqueta bg-emerald-50 text-emerald-700">Entregue</span>
                    ) : (
                      <span className="etiqueta bg-rose-50 text-rose-700">Entrega desfeita</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-slate-600">{h.atendente}</td>
                  <td className="py-2 text-right">
                    <button type="button" className="text-xs font-semibold text-marca-700 hover:underline" onClick={() => setDetalhe(h)}>
                      Detalhes
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {dados && dados.paginas > 1 && <Paginacao pagina={dados.pagina} paginas={dados.paginas} aoMudar={setPagina} />}

      <Modal titulo="Detalhes do atendimento" aberto={detalhe !== null} aoFechar={() => setDetalhe(null)}>
        {detalhe && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-slate-500">Ação</dt>
            <dd className="font-medium">{detalhe.acao === 'entrega_registrada' ? 'Entrega confirmada' : 'Entrega desfeita'}</dd>
            <dt className="text-slate-500">Data e hora</dt>
            <dd>{formatar(detalhe.criado_em, fuso)}</dd>
            <dt className="text-slate-500">Colaborador</dt>
            <dd>
              {detalhe.participante ? (
                <>
                  {detalhe.participante} <span className="font-mono text-slate-500">({detalhe.matricula})</span>
                </>
              ) : (
                'Resultado removido (registro anterior à limpeza dos dados de demonstração)'
              )}
            </dd>
            <dt className="text-slate-500">Prêmio</dt>
            <dd>
              {detalhe.premio}
              {detalhe.unidade ? ` — unidade ${detalhe.unidade}` : ''} · {bloco(detalhe.bloco_numero)}
            </dd>
            <dt className="text-slate-500">Operador</dt>
            <dd>{detalhe.atendente}</dd>
            <dt className="text-slate-500">Pulseira conferida</dt>
            <dd className="font-mono">{detalhe.pulseira_conferida ?? '—'}</dd>
            {detalhe.foto_url && (
              <>
                <dt className="text-slate-500">Foto da entrega</dt>
                <dd>
                  <a href={detalhe.foto_url} target="_blank" rel="noreferrer" title="Abrir a foto em tamanho maior">
                    <img src={detalhe.foto_url} alt="Foto da entrega" className="max-h-56 rounded-lg border border-slate-200 object-contain" />
                  </a>
                </dd>
              </>
            )}
            {detalhe.motivo && (
              <>
                <dt className="text-slate-500">Justificativa</dt>
                <dd>{detalhe.motivo}</dd>
              </>
            )}
            <dt className="text-slate-500">Situação atual</dt>
            <dd className="capitalize">{detalhe.situacao_atual ?? '—'}</dd>
            <dt className="text-slate-500">Identificador</dt>
            <dd className="font-mono text-xs">
              registro {detalhe.id} · resultado {detalhe.sorteio_id ?? '—'}
            </dd>
          </dl>
        )}
      </Modal>
    </section>
  )
}

// ------------------------------------------------------------------ leitor de QR (câmera)
type DetectorNativo = { detect: (v: CanvasImageSource) => Promise<{ rawValue: string }[]> }

/** Câmera ao vivo só é liberada pelo navegador em HTTPS ou em localhost. */
function cameraAoVivoDisponivel(): boolean {
  return typeof window !== 'undefined' && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia
}

/** Leitor nativo do navegador (Android, macOS); no Windows não existe e usamos o jsQR. */
function criarDetectorNativo(): DetectorNativo | null {
  const D = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => DetectorNativo }).BarcodeDetector
  if (!D) return null
  try {
    return new D({ formats: ['qr_code'] })
  } catch {
    return null
  }
}

/** Decodifica o QR Code de uma imagem/quadro desenhado num canvas (funciona em qualquer navegador). */
async function decodificarCanvas(canvas: HTMLCanvasElement): Promise<string | null> {
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx || !canvas.width || !canvas.height) return null
  const { default: jsQR } = await import('jsqr')
  const dados = ctx.getImageData(0, 0, canvas.width, canvas.height)
  return jsQR(dados.data, dados.width, dados.height, { inversionAttempts: 'attemptBoth' })?.data || null
}

function desenhar(canvas: HTMLCanvasElement, fonte: CanvasImageSource, largura: number, altura: number, maximo: number) {
  const escala = Math.min(1, maximo / Math.max(largura, altura))
  canvas.width = Math.max(1, Math.round(largura * escala))
  canvas.height = Math.max(1, Math.round(altura * escala))
  canvas.getContext('2d', { willReadFrequently: true })?.drawImage(fonte, 0, 0, canvas.width, canvas.height)
}

function LeitorQr({ aoLer, aoFechar }: { aoLer: (valor: string) => void; aoFechar: () => void }) {
  const video = useRef<HTMLVideoElement | null>(null)
  const arquivo = useRef<HTMLInputElement | null>(null)
  const [erro, setErro] = useState('')
  const [lendoFoto, setLendoFoto] = useState(false)
  const [cameraFalhou, setCameraFalhou] = useState(false)
  const [pronta, setPronta] = useState(false)
  const [temLanterna, setTemLanterna] = useState(false)
  const [lanternaAcesa, setLanternaAcesa] = useState(false)
  const trilha = useRef<MediaStreamTrack | null>(null)
  const aoVivo = cameraAoVivoDisponivel()
  const mostrarVideo = aoVivo && !cameraFalhou
  // A câmera abre uma vez; o retorno muda a cada renderização do pai.
  const retorno = useRef(aoLer)
  retorno.current = aoLer
  const fechar = useRef(aoFechar)
  fechar.current = aoFechar

  // Tela cheia: Esc fecha e a página de trás não rola.
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') fechar.current()
    }
    const antes = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', tecla)
    return () => {
      document.body.style.overflow = antes
      window.removeEventListener('keydown', tecla)
    }
  }, [])

  function encontrado(valor: string) {
    try {
      navigator.vibrate?.(80)
    } catch {
      /* sem vibração */
    }
    retorno.current(valor)
  }

  async function alternarLanterna() {
    const t = trilha.current
    if (!t) return
    try {
      await t.applyConstraints({ advanced: [{ torch: !lanternaAcesa } as MediaTrackConstraintSet] })
      setLanternaAcesa(!lanternaAcesa)
    } catch {
      setTemLanterna(false)
    }
  }

  useEffect(() => {
    if (!aoVivo) return
    let fluxo: MediaStream | null = null
    let ativo = true
    let quadro = 0
    const nativo = criarDetectorNativo()
    const canvas = document.createElement('canvas')
    navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
      .then(async (s) => {
        fluxo = s
        if (!ativo || !video.current) {
          s.getTracks().forEach((t) => t.stop())
          return
        }
        video.current.srcObject = s
        await video.current.play().catch(() => undefined)
        const t = s.getVideoTracks()[0] ?? null
        trilha.current = t
        const capacidades = (t?.getCapabilities?.() ?? {}) as { torch?: boolean }
        setTemLanterna(!!capacidades.torch)
        setPronta(true)
        const procurar = async () => {
          const v = video.current
          if (!ativo || !v) return
          try {
            let valor: string | null = null
            if (v.videoWidth) {
              if (nativo) {
                valor = (await nativo.detect(v)).find((a) => a.rawValue)?.rawValue || null
              } else {
                desenhar(canvas, v, v.videoWidth, v.videoHeight, 800)
                valor = await decodificarCanvas(canvas)
              }
            }
            if (valor && ativo) {
              encontrado(valor)
              return
            }
          } catch {
            /* quadro ainda sem imagem */
          }
          quadro = window.setTimeout(() => void procurar(), 150)
        }
        void procurar()
      })
      .catch(() => {
        if (!ativo) return
        setCameraFalhou(true)
        setErro('Não foi possível abrir a câmera. Libere o acesso à câmera no navegador ou fotografe o QR Code.')
      })
    return () => {
      ativo = false
      window.clearTimeout(quadro)
      trilha.current = null
      fluxo?.getTracks().forEach((t) => t.stop())
    }
  }, [aoVivo])

  async function lerFoto(f: File | undefined) {
    if (!f) return
    setErro('')
    setLendoFoto(true)
    const url = URL.createObjectURL(f)
    try {
      const img = new Image()
      await new Promise<void>((ok, falha) => {
        img.onload = () => ok()
        img.onerror = () => falha(new Error('imagem'))
        img.src = url
      })
      const canvas = document.createElement('canvas')
      // Tenta em tamanho médio e, se falhar, em resolução maior (QR pequeno na foto).
      let valor: string | null = null
      for (const maximo of [1280, 2400]) {
        desenhar(canvas, img, img.naturalWidth, img.naturalHeight, maximo)
        valor = await decodificarCanvas(canvas)
        if (valor) break
      }
      if (valor) encontrado(valor)
      else setErro('Não encontrei um QR Code na foto. Aproxime a câmera, evite reflexo e tente de novo.')
    } catch {
      setErro('Não foi possível abrir a imagem. Tente outra foto.')
    } finally {
      URL.revokeObjectURL(url)
      setLendoFoto(false)
      if (arquivo.current) arquivo.current.value = ''
    }
  }

  const cantos = [
    'left-0 top-0 border-l-4 border-t-4 rounded-tl-2xl',
    'right-0 top-0 border-r-4 border-t-4 rounded-tr-2xl',
    'left-0 bottom-0 border-l-4 border-b-4 rounded-bl-2xl',
    'right-0 bottom-0 border-r-4 border-b-4 rounded-br-2xl',
  ]

  // Portal no <body>: nenhum ancestral com transform/z-index limita a tela cheia.
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Escanear QR Code do Cartão da Sorte"
      className="fixed inset-0 z-[70] flex flex-col bg-black text-white"
    >
      {/* topo */}
      <div className="relative z-10 flex items-center justify-between gap-3 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <div className="flex min-w-0 items-center gap-2">
          <Icone nome="scanner" className="h-6 w-6 text-mallory-laranja" />
          <p className="truncate text-base font-bold">Escanear QR Code</p>
        </div>
        <div className="flex items-center gap-2">
          {mostrarVideo && temLanterna && (
            <button
              type="button"
              onClick={() => void alternarLanterna()}
              aria-pressed={lanternaAcesa}
              aria-label={lanternaAcesa ? 'Apagar lanterna' : 'Acender lanterna'}
              className={`inline-flex h-11 w-11 items-center justify-center rounded-full ${
                lanternaAcesa ? 'bg-mallory-laranja text-white' : 'bg-white/15 hover:bg-white/25'
              }`}
            >
              <Icone nome="lanterna" className="h-5 w-5" />
            </button>
          )}
          <button
            type="button"
            onClick={aoFechar}
            aria-label="Fechar leitor"
            className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
          >
            <Icone nome="fechar" className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* área do scanner */}
      <div className="relative flex flex-1 items-center justify-center overflow-hidden">
        {mostrarVideo && (
          <video ref={video} playsInline muted autoPlay className="absolute inset-0 h-full w-full object-cover" />
        )}
        <div className="relative aspect-square w-[min(72vw,56vh,360px)]">
          {/* escurece tudo fora da moldura */}
          <div aria-hidden className="pointer-events-none absolute inset-0 rounded-2xl shadow-[0_0_0_200vmax_rgba(0,0,0,0.6)]" />
          {cantos.map((c) => (
            <span key={c} aria-hidden className={`absolute h-12 w-12 border-mallory-laranja ${c}`} />
          ))}
          {mostrarVideo && pronta && (
            <span
              aria-hidden
              className="absolute left-4 right-4 h-0.5 animate-varre rounded-full bg-mallory-laranja shadow-[0_0_14px_3px_rgba(241,100,37,0.75)]"
            />
          )}
          {!mostrarVideo && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Icone nome="scanner" className="h-20 w-20 text-white/25" />
            </div>
          )}
        </div>
      </div>

      {/* rodapé */}
      <div className="relative z-10 space-y-3 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 text-center">
        {mostrarVideo && !erro && (
          <p className="text-sm font-medium" aria-live="polite">
            {pronta ? 'Aponte para o QR Code do Cartão da Sorte' : 'Abrindo a câmera…'}
          </p>
        )}
        {!aoVivo && (
          <p className="mx-auto max-w-md text-sm text-white/80">
            O scanner ao vivo precisa de endereço seguro (HTTPS). Por enquanto, fotografe o QR Code: o sistema lê a foto na hora.
          </p>
        )}
        {erro && (
          <p role="alert" className="mx-auto max-w-md rounded-lg bg-red-500/20 px-3 py-2 text-sm text-red-100">
            {erro}
          </p>
        )}
        <input
          ref={arquivo}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => void lerFoto(e.target.files?.[0])}
        />
        {mostrarVideo ? (
          <button
            type="button"
            className="text-xs text-white/60 underline underline-offset-2 hover:text-white"
            disabled={lendoFoto}
            onClick={() => arquivo.current?.click()}
          >
            {lendoFoto ? 'Lendo a foto…' : 'Não está lendo? Fotografar o QR Code'}
          </button>
        ) : (
          <button
            type="button"
            className="mx-auto inline-flex h-12 w-full max-w-sm items-center justify-center gap-2 rounded-xl bg-marca-600 font-semibold text-white hover:bg-marca-700 disabled:opacity-60"
            disabled={lendoFoto}
            onClick={() => arquivo.current?.click()}
          >
            <Icone nome="camera" className="h-5 w-5" />
            {lendoFoto ? 'Lendo a foto…' : 'Fotografar QR Code'}
          </button>
        )}
        <p className="text-[11px] text-white/50">O QR Code só localiza o ganhador. Sempre confira a pessoa antes de entregar.</p>
      </div>
    </div>,
    document.body,
  )
}
