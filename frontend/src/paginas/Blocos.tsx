import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ErroApi, requisitar } from '../api'
import { useAuth } from '../auth'
import { Capacidade, CartaoBloco, EtiquetaBloco, numeroBloco } from '../componentes/blocos'
import Icone, { type NomeIcone } from '../componentes/Icone'
import { Aviso, Carregando, ImagemPremio, Modal, Vazio } from '../componentes/ui'
import type {
  Bloco,
  BlocoDetalhe,
  BlocosResumo,
  Distribuicao,
  PreviaDistribuicao,
  StatusUnidade,
  UnidadeBloco,
} from '../types'
import { usePainel } from './PainelLayout'
import { misturarAleatorio } from '../misturar'

const SEM_BLOCO = 'sem'

const SITUACAO_UNIDADE: Record<StatusUnidade, { texto: string; classe: string }> = {
  disponivel: { texto: 'Aguardando sorteio', classe: 'bg-slate-100 text-slate-700' },
  sorteado: { texto: 'Sorteada', classe: 'bg-marca-50 text-marca-700' },
  entregue: { texto: 'Sorteada e entregue', classe: 'bg-emerald-50 text-emerald-700' },
  removido: { texto: 'Prêmio excluído', classe: 'bg-slate-100 text-slate-500' },
}

function mensagem(e: unknown, padrao: string): string {
  return e instanceof Error ? e.message : padrao
}

function Indicador({ icone, rotulo, valor, detalhe }: { icone: NomeIcone; rotulo: string; valor: number; detalhe: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-borda bg-white p-3 shadow-suave sm:p-4">
      <span className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-marca-50 text-marca-600 sm:flex">
        <Icone nome={icone} className="h-6 w-6" />
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-bold leading-none tabular-nums text-slate-900">{valor}</p>
        <p className="mt-1 truncate text-sm font-medium text-slate-700">{rotulo}</p>
        <p className="truncate text-xs text-slate-500">{detalhe}</p>
      </div>
    </div>
  )
}

/** Gerenciamento de Blocos: indicadores, distribuição, cartões e organização manual. */
export default function Blocos() {
  const { evento, recarregarEvento } = usePainel()
  const { pode } = useAuth()
  // Admin distribui, cria, edita, reordena e exclui; o sorteador conduz (iniciar, pausar, finalizar).
  const configura = pode('configurar_blocos')
  const conduz = pode('controlar_sorteio')
  // Excluir bloco (em qualquer situação, inclusive com sorteios): só o admin.
  const exclui = pode('excluir_blocos')
  const navegar = useNavigate()
  const base = `/api/events/${evento.id}/blocos`

  const [resumo, setResumo] = useState<BlocosResumo | null>(null)
  const [capacidade, setCapacidade] = useState(evento.capacidade_bloco_padrao)
  // Intercala os prêmios na sequência (vale para distribuir e para remanescentes).
  const [misturar, setMisturar] = useState(true)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [ocupado, setOcupado] = useState(false)

  const [previa, setPrevia] = useState<{ tipo: 'distribuir' | 'remanescentes'; dados: PreviaDistribuicao } | null>(null)
  const [previaNosBlocos, setPreviaNosBlocos] = useState<PreviaNosBlocos | null>(null)
  const [editando, setEditando] = useState<Bloco | 'novo' | null>(null)
  const [excluindo, setExcluindo] = useState<Bloco | null>(null)
  const [detalhe, setDetalhe] = useState<BlocoDetalhe | null>(null)
  const [finalizando, setFinalizando] = useState<Bloco | null>(null)
  const [reabrindo, setReabrindo] = useState<Bloco | null>(null)
  const [organizando, setOrganizando] = useState(false)

  const carregar = useCallback(async () => {
    try {
      setResumo(await requisitar<BlocosResumo>(base))
      setErro('')
    } catch (e) {
      setErro(mensagem(e, 'Falha ao carregar os blocos'))
    }
  }, [base])

  useEffect(() => {
    void carregar()
  }, [carregar])

  async function executar(acao: () => Promise<unknown>, sucesso = '') {
    setOcupado(true)
    setErro('')
    setAviso('')
    try {
      await acao()
      await carregar()
      if (sucesso) setAviso(sucesso)
      return true
    } catch (e) {
      setErro(mensagem(e, 'Operação não concluída'))
      // Algo mudou no servidor (outro usuário): mostra o estado atual.
      if (e instanceof ErroApi && e.status === 409) await carregar()
      return false
    } finally {
      setOcupado(false)
    }
  }

  async function abrirPrevia(tipo: 'distribuir' | 'remanescentes') {
    setOcupado(true)
    setErro('')
    setAviso('')
    try {
      const caminho = tipo === 'distribuir' ? `${base}/distribuir/previa` : `${base}/remanescentes/previa`
      const dados = await requisitar<PreviaDistribuicao>(caminho, { metodo: 'POST', corpo: { capacidade } })
      setPrevia({ tipo, dados })
    } catch (e) {
      setErro(mensagem(e, 'Não foi possível calcular a prévia'))
    } finally {
      setOcupado(false)
    }
  }

  async function confirmarPrevia() {
    if (!previa) return
    const { tipo, dados } = previa
    setPrevia(null)
    if (tipo === 'distribuir') {
      const ok = await executar(
        () => requisitar(`${base}/distribuir`, { metodo: 'POST', corpo: { capacidade: dados.capacidade, misturar } }),
        `Distribuição concluída: ${dados.unidades} unidade(s) em ${dados.blocos.length} bloco(s).`,
      )
      if (ok) await recarregarEvento()
    } else {
      await executar(
        () =>
          requisitar(`${base}/remanescentes`, { metodo: 'POST', corpo: { capacidade: dados.capacidade, misturar } }),
        `${dados.blocos.length} bloco(s) de remanescentes criado(s).`,
      )
    }
  }

  async function abrirPreviaNosBlocos() {
    setOcupado(true)
    setErro('')
    setAviso('')
    try {
      setPreviaNosBlocos(await requisitar<PreviaNosBlocos>(`${base}/distribuir-nos-blocos/previa`, { metodo: 'POST' }))
    } catch (e) {
      setErro(mensagem(e, 'Não foi possível calcular a prévia'))
    } finally {
      setOcupado(false)
    }
  }

  async function confirmarNosBlocos() {
    if (!previaNosBlocos) return
    const dados = previaNosBlocos
    setPreviaNosBlocos(null)
    await executar(
      () => requisitar(`${base}/distribuir-nos-blocos`, { metodo: 'POST', corpo: { misturar } }),
      `Distribuição nos blocos criados concluída: ${dados.unidades - dados.sobra} unidade(s) em ${dados.blocos.filter((b) => b.unidades > 0).length} bloco(s)` +
        (dados.sobra > 0 ? `; ${dados.sobra} ficaram sem bloco.` : '.'),
    )
  }

  async function iniciar(bloco: Bloco) {
    const ok = await executar(() => requisitar(`${base}/${bloco.id}/iniciar`, { metodo: 'POST' }))
    if (ok) navegar('../sorteio')
  }

  async function mover(bloco: Bloco, delta: -1 | 1) {
    if (!resumo) return
    const planejados = resumo.blocos.filter((b) => b.status === 'PLANEJADO').map((b) => b.id)
    const i = planejados.indexOf(bloco.id)
    const j = i + delta
    if (i < 0 || j < 0 || j >= planejados.length) return
    ;[planejados[i], planejados[j]] = [planejados[j], planejados[i]]
    await executar(() => requisitar(`${base}/reordenar`, { metodo: 'POST', corpo: { blocos: planejados } }))
  }

  if (resumo === null) return erro ? <Aviso tipo="erro">{erro}</Aviso> : <Carregando />

  const planejadosIds = resumo.blocos.filter((b) => b.status === 'PLANEJADO').map((b) => b.id)
  const distribuidas = resumo.unidades_total - resumo.unidades_sem_bloco - resumo.sorteadas_sem_bloco

  if (organizando) {
    return (
      <Organizador
        base={base}
        aoSair={async (salvou) => {
          setOrganizando(false)
          await carregar()
          if (salvou) setAviso('Organização salva.')
        }}
      />
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600">
          Crie, organize e acompanhe os blocos de sorteio. Os números contam <strong>unidades</strong>: 10 Air
          Fryers e 5 liquidificadores são 15 unidades.
        </p>
        {configura && (
          <button type="button" className="btn-primario" disabled={ocupado} onClick={() => setEditando('novo')}>
            <Icone nome="mais" className="h-4 w-4" />
            Novo bloco
          </button>
        )}
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {aviso && <Aviso tipo="sucesso">{aviso}</Aviso>}
      {resumo.sorteadas_sem_bloco > 0 && (
        <Aviso tipo="info">
          {resumo.sorteadas_sem_bloco} unidade(s) já sorteada(s) estão fora dos blocos (sorteadas antes da criação dos
          blocos ou de um bloco excluído). Elas permanecem no histórico e não entram na distribuição.
        </Aviso>
      )}

      {/* ------------------------------------------------ indicadores */}
      <section aria-label="Indicadores" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Indicador icone="premios" rotulo="Prêmios cadastrados" valor={resumo.unidades_total} detalhe="unidades no evento" />
        <Indicador icone="blocos" rotulo="Prêmios distribuídos" valor={distribuidas} detalhe="unidades em blocos" />
        <Indicador icone="entregas" rotulo="Prêmios sem bloco" valor={resumo.unidades_sem_bloco} detalhe="disponíveis para distribuir" />
        <Indicador icone="painel" rotulo="Blocos criados" valor={resumo.blocos.length} detalhe={`${planejadosIds.length} planejado(s)`} />
      </section>

      {/* ------------------------------------------------ distribuição */}
      {configura && (
        <section className="rounded-xl border border-borda bg-white p-5 shadow-suave">
          <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
            <Icone nome="blocos" className="h-5 w-5 text-marca-600" />
            Distribuição dos prêmios
          </h2>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <div>
              <label className="rotulo" htmlFor="capacidade-padrao">
                Prêmios por bloco
              </label>
              <input
                id="capacidade-padrao"
                type="number"
                min={1}
                max={1000}
                className="campo w-28"
                value={capacidade}
                onChange={(e) => setCapacidade(Math.max(1, Math.min(1000, Number(e.target.value) || 1)))}
              />
            </div>
            <button type="button" className="btn-primario" disabled={ocupado} onClick={() => void abrirPrevia('distribuir')}>
              Distribuir automaticamente
            </button>
            {resumo.blocos.some((b) => b.status === 'PLANEJADO') && (
              <button
                type="button"
                className="btn-neutro"
                disabled={ocupado}
                onClick={() => void abrirPreviaNosBlocos()}
                title="Mantém os blocos planejados que você criou e enche cada um até a capacidade dele"
              >
                <Icone nome="blocos" className="h-4 w-4" />
                Distribuir nos blocos criados
              </button>
            )}
            <button
              type="button"
              className="btn-neutro"
              disabled={ocupado || resumo.blocos.length === 0}
              onClick={() => setOrganizando(true)}
            >
              <Icone nome="editar" className="h-4 w-4" />
              Organizar manualmente
            </button>
            {resumo.unidades_remanescentes > 0 && resumo.modo_blocos && (
              <button type="button" className="btn-neutro" disabled={ocupado} onClick={() => void abrirPrevia('remanescentes')}>
                Criar bloco de remanescentes ({resumo.unidades_remanescentes})
              </button>
            )}
          </div>
          <label className="mt-3 flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-marca-600"
              checked={misturar}
              onChange={(e) => setMisturar(e.target.checked)}
            />
            <span>
              <strong>Misturar os prêmios</strong> — intercala os prêmios na sequência, sem repetir o mesmo prêmio
              seguido sempre que possível. Desmarcado, segue a ordem do cadastro de prêmios.
            </span>
          </label>
          <p className="mt-3 text-xs text-slate-500">
            Você confere a prévia antes de confirmar. Ex.: 107 unidades com 25 por bloco geram blocos de 25, 25, 25, 25
            e 7. A distribuição refaz apenas os blocos ainda não iniciados; prêmios já sorteados nunca mudam de bloco.
          </p>
        </section>
      )}

      {/* ------------------------------------------------ cartões */}
      {resumo.blocos.length === 0 ? (
        <Vazio
          titulo="Nenhum bloco criado"
          descricao="Use a distribuição automática ou crie um bloco. Sem blocos, o sorteio funciona no modo simples, prêmio a prêmio."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {resumo.blocos.map((bloco) => {
            const posicao = planejadosIds.indexOf(bloco.id)
            return (
              <CartaoBloco
                key={bloco.id}
                bloco={bloco}
                destaque={bloco.id === resumo.bloco_ativo_id}
                topo={
                  configura && posicao >= 0 && planejadosIds.length > 1 ? (
                    <div className="flex gap-1">
                      <button
                        type="button"
                        className="btn-icone h-7 w-7"
                        disabled={ocupado || posicao === 0}
                        onClick={() => void mover(bloco, -1)}
                        aria-label={`Mover ${bloco.nome} para antes`}
                        title="Mover para antes"
                      >
                        <Icone nome="acima" className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        className="btn-icone h-7 w-7"
                        disabled={ocupado || posicao === planejadosIds.length - 1}
                        onClick={() => void mover(bloco, 1)}
                        aria-label={`Mover ${bloco.nome} para depois`}
                        title="Mover para depois"
                      >
                        <Icone nome="abaixo" className="h-4 w-4" />
                      </button>
                    </div>
                  ) : undefined
                }
              >
                <button
                  type="button"
                  className="btn-neutro px-3 py-1.5"
                  onClick={async () => {
                    try {
                      setDetalhe(await requisitar<BlocoDetalhe>(`${base}/${bloco.id}`))
                    } catch (e) {
                      setErro(mensagem(e, 'Falha ao carregar os prêmios do bloco'))
                    }
                  }}
                >
                  Ver prêmios
                </button>
                {configura && (
                  <button
                    type="button"
                    className="btn-neutro px-2.5 py-1.5"
                    onClick={() => setEditando(bloco)}
                    aria-label={`Editar ${bloco.nome}`}
                    title="Editar bloco"
                  >
                    <Icone nome="editar" className="h-4 w-4" />
                  </button>
                )}
                {conduz && (bloco.status === 'PLANEJADO' || bloco.status === 'PAUSADO') && (
                  <button
                    type="button"
                    className="btn-primario px-3 py-1.5"
                    disabled={ocupado || bloco.restantes === 0 || resumo.bloco_ativo_id !== null}
                    title={
                      resumo.bloco_ativo_id !== null
                        ? 'Outro bloco está em andamento'
                        : bloco.restantes === 0
                          ? 'Bloco sem prêmios disponíveis: não pode ser iniciado'
                          : undefined
                    }
                    onClick={() => void iniciar(bloco)}
                  >
                    {bloco.status === 'PAUSADO' ? 'Continuar' : 'Iniciar'}
                  </button>
                )}
                {conduz && bloco.status === 'EM_ANDAMENTO' && (
                  <>
                    <button type="button" className="btn-primario px-3 py-1.5" onClick={() => navegar('../sorteio')}>
                      Ir para o sorteio
                    </button>
                    <button
                      type="button"
                      className="btn-neutro px-3 py-1.5"
                      disabled={ocupado}
                      onClick={() => void executar(() => requisitar(`${base}/${bloco.id}/pausar`, { metodo: 'POST' }))}
                    >
                      Pausar
                    </button>
                  </>
                )}
                {conduz && (bloco.status === 'EM_ANDAMENTO' || bloco.status === 'PAUSADO') && (
                  <button
                    type="button"
                    className={bloco.restantes === 0 ? 'btn-primario px-3 py-1.5' : 'btn-neutro px-3 py-1.5'}
                    disabled={ocupado}
                    onClick={() => setFinalizando(bloco)}
                  >
                    Finalizar
                  </button>
                )}
                {conduz && bloco.status === 'FINALIZADO' && bloco.restantes > 0 && (
                  <button
                    type="button"
                    className="btn-neutro px-3 py-1.5"
                    disabled={ocupado}
                    title="Volta o bloco para pausado para sortear os prêmios que faltam"
                    onClick={() => setReabrindo(bloco)}
                  >
                    Reabrir
                  </button>
                )}
                {exclui && (
                  // Só o ícone: cabe na mesma linha dos outros botões.
                  <button
                    type="button"
                    className="btn ml-auto shrink-0 border border-rose-200 bg-white px-2.5 py-1.5 text-rose-700 hover:bg-rose-50"
                    disabled={ocupado}
                    onClick={() => setExcluindo(bloco)}
                    aria-label={`Excluir ${bloco.nome}`}
                    title="Excluir bloco"
                  >
                    <Icone nome="excluir" className="h-4 w-4" />
                  </button>
                )}
              </CartaoBloco>
            )
          })}
        </div>
      )}

      {/* ------------------------------------------------ modais */}
      <ModalPrevia
        previa={previa}
        aoFechar={() => setPrevia(null)}
        aoConfirmar={() => void confirmarPrevia()}
      />
      <ModalPreviaNosBlocos
        previa={previaNosBlocos}
        misturar={misturar}
        aoFechar={() => setPreviaNosBlocos(null)}
        aoConfirmar={() => void confirmarNosBlocos()}
      />

      <ModalBloco
        alvo={editando}
        base={base}
        capacidadePadrao={resumo.capacidade_padrao}
        proximoNumero={Math.max(0, ...resumo.blocos.map((b) => b.numero)) + 1}
        aoFechar={() => setEditando(null)}
        aoConcluir={async (texto) => {
          setEditando(null)
          await carregar()
          setAviso(texto)
        }}
      />

      <Modal titulo="Excluir bloco" aberto={excluindo !== null} aoFechar={() => setExcluindo(null)}>
        {excluindo && (
          <div className="space-y-4">
            <p className="font-semibold text-slate-900">Tem certeza de que deseja excluir este bloco?</p>
            <dl className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 text-sm">
              <dt className="text-slate-500">Bloco</dt>
              <dd className="font-medium text-slate-900">
                {numeroBloco(excluindo.numero)} — {excluindo.nome}
              </dd>
              <dt className="text-slate-500">Situação</dt>
              <dd className="font-medium text-slate-900">
                <EtiquetaBloco status={excluindo.status} />
              </dd>
              <dt className="text-slate-500">Já sorteados</dt>
              <dd className="font-medium text-slate-900">{excluindo.sorteadas}</dd>
              <dt className="text-slate-500">Voltam para “sem bloco”</dt>
              <dd className="font-medium text-slate-900">{excluindo.restantes}</dd>
            </dl>
            <Aviso tipo="info">
              Nenhum prêmio é excluído. Os que ainda não foram sorteados ficam disponíveis para uma nova distribuição.
              {excluindo.sorteadas > 0 &&
                ' Os prêmios já sorteados e seus ganhadores continuam no Histórico e no relatório, com o nome deste bloco.'}
            </Aviso>
            {excluindo.status === 'EM_ANDAMENTO' && (
              <Aviso tipo="atencao">Este bloco está em andamento: o sorteio dele para ao excluir.</Aviso>
            )}
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-neutro" onClick={() => setExcluindo(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn-perigo"
                disabled={ocupado}
                onClick={() => {
                  const alvo = excluindo
                  setExcluindo(null)
                  void executar(
                    () => requisitar(`${base}/${alvo.id}`, { metodo: 'DELETE' }),
                    `${alvo.nome} excluído; ${alvo.restantes} unidade(s) voltaram para “sem bloco”.`,
                  )
                }}
              >
                <Icone nome="excluir" className="h-4 w-4" />
                Excluir bloco
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal titulo="Reabrir bloco" aberto={reabrindo !== null} aoFechar={() => setReabrindo(null)}>
        {reabrindo && (
          <div className="space-y-4">
            <p className="font-semibold text-slate-900">Reabrir {reabrindo.nome}?</p>
            <dl className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 text-sm">
              <dt className="text-slate-500">Já sorteados</dt>
              <dd className="font-medium text-slate-900">{reabrindo.sorteadas}</dd>
              <dt className="text-slate-500">Prêmios que faltam</dt>
              <dd className="font-medium text-slate-900">{reabrindo.restantes}</dd>
            </dl>
            <Aviso tipo="info">
              O bloco volta para <strong>pausado</strong> e pode ser continuado na tela de Sorteio. Os resultados já
              sorteados não mudam. A reabertura fica registrada na auditoria.
            </Aviso>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-neutro" onClick={() => setReabrindo(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn-primario"
                disabled={ocupado}
                onClick={() => {
                  const alvo = reabrindo
                  setReabrindo(null)
                  void executar(
                    () => requisitar(`${base}/${alvo.id}/reabrir`, { metodo: 'POST' }),
                    `${alvo.nome} reaberto. Use “Continuar” para voltar a sortear.`,
                  )
                }}
              >
                Reabrir bloco
              </button>
            </div>
          </div>
        )}
      </Modal>

      <ModalFinalizar
        bloco={finalizando}
        aoFechar={() => setFinalizando(null)}
        aoConfirmar={async (bloco) => {
          setFinalizando(null)
          await executar(
            () =>
              requisitar(`${base}/${bloco.id}/finalizar`, {
                metodo: 'POST',
                corpo: { confirmar_pendentes: bloco.restantes > 0 },
              }),
            `${bloco.nome} finalizado.`,
          )
        }}
      />

      <Modal
        titulo={detalhe ? `${numeroBloco(detalhe.bloco.numero)} — ${detalhe.bloco.nome}` : ''}
        aberto={detalhe !== null}
        aoFechar={() => setDetalhe(null)}
        largura="max-w-2xl"
      >
        {detalhe && <DetalheBloco detalhe={detalhe} />}
      </Modal>
    </div>
  )
}

// ------------------------------------------------------------------ modais
interface PreviaNosBlocos {
  unidades: number
  blocos: { numero: number; nome: string; unidades: number; capacidade: number }[]
  sobra: number
}

function ModalPreviaNosBlocos({
  previa,
  misturar,
  aoFechar,
  aoConfirmar,
}: {
  previa: PreviaNosBlocos | null
  misturar: boolean
  aoFechar: () => void
  aoConfirmar: () => void
}) {
  return (
    <Modal titulo="Prévia: distribuir nos blocos criados" aberto={previa !== null} aoFechar={aoFechar}>
      {previa && (
        <div className="space-y-4">
          <p className="text-sm text-slate-700">
            <strong>{previa.unidades}</strong> unidade(s) entram nos blocos planejados, na ordem, até a capacidade de
            cada um{misturar ? ', com os prêmios misturados' : ''}.
          </p>
          <ul className="max-h-64 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
            {previa.blocos.map((b) => (
              <li key={b.numero} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 truncate">
                  <span className="font-semibold text-marca-600">{numeroBloco(b.numero)}</span> · {b.nome}
                </span>
                <span className={`shrink-0 tabular-nums ${b.unidades < b.capacidade ? 'text-amber-700' : 'text-slate-700'}`}>
                  {b.unidades}/{b.capacidade} unidade(s)
                </span>
              </li>
            ))}
          </ul>
          {previa.sobra > 0 && (
            <Aviso tipo="atencao">
              {previa.sobra} unidade(s) não cabem na capacidade dos blocos e ficarão <strong>sem bloco</strong>. Aumente a
              capacidade, crie outro bloco ou use “Distribuir automaticamente”.
            </Aviso>
          )}
          <p className="text-xs text-slate-500">
            Os blocos continuam com o mesmo nome, descrição e capacidade. Blocos iniciados, pausados ou finalizados e
            unidades já sorteadas não mudam.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-neutro" onClick={aoFechar}>
              Cancelar
            </button>
            <button type="button" className="btn-primario" onClick={aoConfirmar}>
              Confirmar distribuição
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function ModalPrevia({
  previa,
  aoFechar,
  aoConfirmar,
}: {
  previa: { tipo: 'distribuir' | 'remanescentes'; dados: PreviaDistribuicao } | null
  aoFechar: () => void
  aoConfirmar: () => void
}) {
  const dados = previa?.dados
  const distribuir = previa?.tipo === 'distribuir'
  return (
    <Modal
      titulo={distribuir ? 'Prévia da distribuição' : 'Prévia dos blocos de remanescentes'}
      aberto={previa !== null}
      aoFechar={aoFechar}
    >
      {dados && (
        <div className="space-y-4">
          <p className="text-sm text-slate-700">
            <strong>{dados.unidades}</strong> unidade(s) em <strong>{dados.blocos.length}</strong> bloco(s), até{' '}
            {dados.capacidade} por bloco.
          </p>
          <ul className="max-h-64 divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
            {dados.blocos.map((b) => (
              <li key={b.numero} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 truncate">
                  <span className="font-semibold text-marca-600">{numeroBloco(b.numero)}</span> · {b.nome}
                </span>
                <span className="shrink-0 tabular-nums text-slate-700">{b.unidades} unidade(s)</span>
              </li>
            ))}
          </ul>
          {dados.planejados_refeitos.length > 0 && (
            <Aviso tipo="atencao">
              Os {dados.planejados_refeitos.length} bloco(s) ainda não iniciado(s) serão recriados ({dados.planejados_refeitos.join(', ')}).
              Nomes, descrições e ajustes manuais neles serão perdidos.
            </Aviso>
          )}
          <p className="text-xs text-slate-500">
            Blocos iniciados, pausados ou finalizados e unidades já sorteadas não mudam.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-neutro" onClick={aoFechar}>
              Cancelar
            </button>
            <button type="button" className="btn-primario" onClick={aoConfirmar}>
              {distribuir ? 'Confirmar distribuição' : 'Criar blocos'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function ModalBloco({
  alvo,
  base,
  capacidadePadrao,
  proximoNumero,
  aoFechar,
  aoConcluir,
}: {
  alvo: Bloco | 'novo' | null
  base: string
  capacidadePadrao: number
  proximoNumero: number
  aoFechar: () => void
  aoConcluir: (mensagem: string) => Promise<void>
}) {
  const [nome, setNome] = useState('')
  const [descricao, setDescricao] = useState('')
  const [capacidade, setCapacidade] = useState(capacidadePadrao)
  const [erro, setErro] = useState('')
  const [salvando, setSalvando] = useState(false)
  const novo = alvo === 'novo'
  const bloco = alvo !== 'novo' ? alvo : null

  useEffect(() => {
    setErro('')
    setNome(bloco?.nome ?? '')
    setDescricao(bloco?.descricao ?? '')
    setCapacidade(bloco?.capacidade ?? capacidadePadrao)
  }, [alvo, bloco, capacidadePadrao])

  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    setErro('')
    setSalvando(true)
    try {
      if (novo) {
        await requisitar(base, {
          metodo: 'POST',
          corpo: { nome: nome.trim() || null, capacidade, descricao: descricao.trim() || null },
        })
        await aoConcluir('Bloco criado.')
      } else if (bloco) {
        await requisitar(`${base}/${bloco.id}`, {
          metodo: 'PATCH',
          corpo: {
            nome,
            descricao,
            capacidade: bloco.status === 'FINALIZADO' ? undefined : capacidade,
          },
        })
        await aoConcluir('Bloco atualizado.')
      }
    } catch (erroSalvar) {
      setErro(mensagem(erroSalvar, 'Falha ao salvar'))
    } finally {
      setSalvando(false)
    }
  }

  const numero = bloco?.numero ?? proximoNumero

  return (
    <Modal titulo={novo ? 'Novo bloco' : 'Editar bloco'} aberto={alvo !== null} aoFechar={aoFechar}>
      <form onSubmit={salvar} className="space-y-4">
        <p className="flex items-center gap-2 text-sm text-slate-600">
          <span className="etiqueta shrink-0 whitespace-nowrap bg-marca-50 text-marca-700">{numeroBloco(numero)}</span>
          {novo ? 'Situação inicial: Planejado. Entra no fim da sequência (reordene nos cartões).' : bloco && <EtiquetaBloco status={bloco.status} />}
        </p>
        <div>
          <label className="rotulo" htmlFor="bloco-nome">
            Nome do bloco
          </label>
          <input
            id="bloco-nome"
            className="campo"
            maxLength={120}
            required={!novo}
            autoFocus
            placeholder={novo ? `Ex.: Bloco ${String(numero).padStart(2, '0')} — Prêmios Especiais (vazio: "Bloco ${String(numero).padStart(2, '0')}")` : undefined}
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </div>
        <div>
          <label className="rotulo" htmlFor="bloco-descricao">
            Descrição (opcional)
          </label>
          <textarea
            id="bloco-descricao"
            className="campo"
            rows={2}
            maxLength={500}
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
          />
        </div>
        <div>
          <label className="rotulo" htmlFor="bloco-capacidade">
            Capacidade máxima (unidades)
          </label>
          <input
            id="bloco-capacidade"
            type="number"
            min={Math.max(1, bloco?.total ?? 1)}
            max={1000}
            className="campo w-32"
            disabled={bloco?.status === 'FINALIZADO'}
            value={capacidade}
            onChange={(e) => setCapacidade(Math.max(1, Math.min(1000, Number(e.target.value) || 1)))}
          />
          {bloco && (
            <p className="mt-1 text-xs text-slate-500">
              O bloco tem {bloco.total} unidade(s); a capacidade não pode ficar abaixo disso. Para mudar as unidades,
              use “Organizar manualmente”.
            </p>
          )}
        </div>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn-primario" disabled={salvando}>
            {salvando ? 'Salvando...' : novo ? 'Criar bloco' : 'Salvar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export function ModalFinalizar({
  bloco,
  aoFechar,
  aoConfirmar,
}: {
  bloco: Bloco | null
  aoFechar: () => void
  aoConfirmar: (bloco: Bloco) => void | Promise<void>
}) {
  return (
    <Modal titulo="Finalizar bloco" aberto={bloco !== null} aoFechar={aoFechar}>
      {bloco && (
        <div className="space-y-4">
          {bloco.restantes > 0 ? (
            <Aviso tipo="atencao">
              O {bloco.nome} ainda tem <strong>{bloco.restantes}</strong> prêmio(s) sem sorteio. Depois de finalizar,
              eles poderão ir para um bloco de remanescentes.
            </Aviso>
          ) : (
            <p className="text-sm text-slate-600">
              Todos os {bloco.total} prêmios do {bloco.nome} foram sorteados. Confira se nenhum ganhador ausente
              precisa ser anulado antes de encerrar.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-neutro" onClick={aoFechar}>
              Cancelar
            </button>
            <button type="button" className="btn-primario" onClick={() => void aoConfirmar(bloco)}>
              {bloco.restantes > 0 ? 'Finalizar com pendências' : 'Finalizar bloco'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function DetalheBloco({ detalhe }: { detalhe: BlocoDetalhe }) {
  const [busca, setBusca] = useState('')
  const anulados = detalhe.resultados.filter((r) => r.status === 'anulado')
  const termo = busca.trim().toLowerCase()
  const visiveis = detalhe.unidades
    .map((u, indice) => ({ u, ordem: indice + 1 }))
    .filter(({ u }) => !termo || u.premio_nome.toLowerCase().includes(termo))
  const aguardando = detalhe.unidades.filter((u) => u.status === 'disponivel').length
  return (
    <div className="space-y-4">
      {detalhe.bloco.descricao && <p className="text-sm text-slate-600">{detalhe.bloco.descricao}</p>}
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <EtiquetaBloco status={detalhe.bloco.status} />
        <span>
          {detalhe.bloco.total}/{detalhe.bloco.capacidade} unidades · {aguardando} aguardando ·{' '}
          {detalhe.bloco.sorteadas} sorteada(s)
        </span>
        {detalhe.bloco.finalizado_por && <span>· finalizado por {detalhe.bloco.finalizado_por}</span>}
      </div>
      {detalhe.unidades.length === 0 ? (
        <Vazio titulo="Bloco sem prêmios" descricao="Use “Organizar manualmente” para colocar unidades neste bloco." />
      ) : (
        <>
          <input
            type="search"
            className="campo"
            placeholder="Pesquisar produto..."
            aria-label="Pesquisar produto no bloco"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          <ol className="max-h-[50vh] divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200">
            {visiveis.map(({ u, ordem }) => {
              const situacao = SITUACAO_UNIDADE[u.status]
              return (
                <li key={u.id} className="flex items-center gap-3 p-2">
                  <span className="w-7 text-right text-xs font-semibold text-slate-400" title="Ordem do sorteio">
                    {ordem}º
                  </span>
                  <div className="h-10 w-10 shrink-0 overflow-hidden rounded bg-slate-100">
                    <ImagemPremio url={u.premio_imagem_url} nome={u.premio_nome} className="h-full w-full text-slate-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-900">{u.premio_nome}</p>
                    <p className="truncate text-xs text-slate-500">
                      Unidade {u.numero} de {u.quantidade_premio}
                      {u.ganhador_nome ? ` · ${u.ganhador_nome}` : ''}
                    </p>
                  </div>
                  <span className={`etiqueta shrink-0 ${situacao.classe}`}>{situacao.texto}</span>
                </li>
              )
            })}
            {visiveis.length === 0 && <li className="p-3 text-center text-sm text-slate-500">Nenhum produto encontrado.</li>}
          </ol>
        </>
      )}
      {anulados.length > 0 && (
        <p className="text-xs text-slate-500">
          {anulados.length} resultado(s) anulado(s) neste bloco permanecem no histórico.
        </p>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ organizador
type Colunas = Record<string, UnidadeBloco[]>
type Situacao = 'todas' | 'disponivel' | 'sorteada'

function Organizador({ base, aoSair }: { base: string; aoSair: (salvou: boolean) => void }) {
  const [original, setOriginal] = useState<Distribuicao | null>(null)
  const [colunas, setColunas] = useState<Colunas>({})
  const [capacidades, setCapacidades] = useState<Record<string, number>>({})
  const [selecionadas, setSelecionadas] = useState<number[]>([])
  const [arrastando, setArrastando] = useState<number | null>(null)
  const [destino, setDestino] = useState('')
  const [busca, setBusca] = useState('')
  const [filtroBloco, setFiltroBloco] = useState('todos')
  const [situacao, setSituacao] = useState<Situacao>('todas')
  const [erro, setErro] = useState('')
  const [conflito, setConflito] = useState(false)
  const [salvando, setSalvando] = useState(false)

  const preparar = useCallback((dados: Distribuicao) => {
    setOriginal(dados)
    const novas: Colunas = { [SEM_BLOCO]: dados.sem_bloco }
    const caps: Record<string, number> = {}
    for (const { bloco, unidades } of dados.blocos) {
      novas[String(bloco.id)] = unidades
      caps[String(bloco.id)] = bloco.capacidade
    }
    setColunas(novas)
    setCapacidades(caps)
    setSelecionadas([])
    setConflito(false)
  }, [])

  const recarregar = useCallback(() => {
    setErro('')
    requisitar<Distribuicao>(`${base}/distribuicao`)
      .then(preparar)
      .catch((e) => setErro(mensagem(e, 'Falha ao carregar a distribuição')))
  }, [base, preparar])

  useEffect(() => {
    recarregar()
  }, [recarregar])

  const blocos = useMemo(() => new Map(original?.blocos.map((b) => [String(b.bloco.id), b.bloco]) ?? []), [original])

  // Colunas: "sem bloco", blocos planejados e finalizados que ainda tenham
  // prêmios disponíveis para liberar. Blocos iniciados ficam congelados.
  const editaveis = useMemo(
    () => [
      SEM_BLOCO,
      ...[...blocos.values()]
        .filter(
          (b) =>
            b.status === 'PLANEJADO' ||
            (b.status === 'FINALIZADO' && (colunas[String(b.id)] ?? []).some((u) => u.status === 'disponivel')),
        )
        .map((b) => String(b.id)),
    ],
    [blocos, colunas],
  )
  const congelados = [...blocos.values()].filter((b) => b.status === 'EM_ANDAMENTO' || b.status === 'PAUSADO')
  const visiveis = filtroBloco === 'todos' ? editaveis : editaveis.filter((c) => c === filtroBloco)

  const recebe = (chave: string) => chave === SEM_BLOCO || blocos.get(chave)?.status === 'PLANEJADO'
  const movel = (u: UnidadeBloco) => u.status === 'disponivel'
  const nomeColuna = (c: string) =>
    c === SEM_BLOCO ? 'Sem bloco' : `${numeroBloco(blocos.get(c)!.numero)} — ${blocos.get(c)!.nome}`

  // Alterações pendentes (para avisar antes de sair).
  const alterado = useMemo(() => {
    if (!original) return false
    const antes: Colunas = { [SEM_BLOCO]: original.sem_bloco }
    for (const { bloco, unidades } of original.blocos) antes[String(bloco.id)] = unidades
    const mudouUnidades = Object.keys(colunas).some(
      (c) => (colunas[c] ?? []).map((u) => u.id).join(',') !== (antes[c] ?? []).map((u) => u.id).join(','),
    )
    const mudouCapacidade = original.blocos.some((b) => capacidades[String(b.bloco.id)] !== b.bloco.capacidade)
    return mudouUnidades || mudouCapacidade
  }, [original, colunas, capacidades])

  useEffect(() => {
    if (!alterado) return
    const avisar = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', avisar)
    return () => window.removeEventListener('beforeunload', avisar)
  }, [alterado])

  function localizar(unidadeId: number): string | null {
    return Object.keys(colunas).find((c) => colunas[c].some((u) => u.id === unidadeId)) ?? null
  }

  /** Move uma ou várias unidades para `alvo` (na posição dada, ou no fim). */
  function mover(ids: number[], alvo: string, posicao: number | null) {
    if (!recebe(alvo)) return
    setColunas((atual) => {
      const novas: Colunas = {}
      const movidas: UnidadeBloco[] = []
      for (const [chave, lista] of Object.entries(atual)) {
        novas[chave] = lista.filter((u) => {
          if (ids.includes(u.id) && movel(u)) {
            movidas.push(u)
            return false
          }
          return true
        })
      }
      // Mantém a ordem da seleção.
      movidas.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id))
      const destinoLista = [...(novas[alvo] ?? [])]
      const indice = posicao === null ? destinoLista.length : Math.max(0, Math.min(posicao, destinoLista.length))
      destinoLista.splice(indice, 0, ...movidas)
      novas[alvo] = destinoLista
      return novas
    })
  }

  function deslocar(unidadeId: number, delta: -1 | 1) {
    const coluna = localizar(unidadeId)
    if (!coluna || !recebe(coluna)) return
    const indice = colunas[coluna].findIndex((u) => u.id === unidadeId)
    mover([unidadeId], coluna, Math.max(0, indice + delta))
  }

  function alternar(id: number) {
    setSelecionadas((atual) => (atual.includes(id) ? atual.filter((x) => x !== id) : [...atual, id]))
  }

  /** Dado: embaralha a sequência do bloco sem repetir o mesmo prêmio seguido (quando possível). */
  function misturarBloco(chave: string) {
    if (!recebe(chave) || chave === SEM_BLOCO) return
    setColunas((atual) => ({ ...atual, [chave]: misturarAleatorio(atual[chave] ?? [], (u) => u.prize_id) }))
  }

  /** Exporta a organização como está na tela (inclui o que ainda não foi salvo). */
  function exportar() {
    if (!original) return
    const situacaoUnidade: Record<string, string> = {
      disponivel: 'Aguardando sorteio',
      sorteado: 'Sorteada',
      entregue: 'Sorteada e entregue',
      removido: 'Prêmio excluído',
    }
    const situacaoBloco: Record<string, string> = {
      PLANEJADO: 'Planejado',
      EM_ANDAMENTO: 'Em andamento',
      PAUSADO: 'Pausado',
      FINALIZADO: 'Finalizado',
    }
    const linhas: (string | number)[][] = [
      ['Bloco', 'Nome do bloco', 'Situação do bloco', 'Posição', 'Prêmio', 'Unidade', 'Situação da unidade'],
    ]
    for (const { bloco } of original.blocos) {
      ;(colunas[String(bloco.id)] ?? []).forEach((u, i) =>
        linhas.push([
          numeroBloco(bloco.numero),
          bloco.nome,
          situacaoBloco[bloco.status] ?? bloco.status,
          i + 1,
          u.premio_nome,
          `${u.numero} de ${u.quantidade_premio}`,
          situacaoUnidade[u.status] ?? u.status,
        ]),
      )
    }
    ;(colunas[SEM_BLOCO] ?? []).forEach((u, i) =>
      linhas.push(['Sem bloco', '', '', i + 1, u.premio_nome, `${u.numero} de ${u.quantidade_premio}`, situacaoUnidade[u.status] ?? u.status]),
    )
    // Ponto e vírgula + BOM: abre direto no Excel em português.
    const celula = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`
    const csv = '﻿' + linhas.map((l) => l.map(celula).join(';')).join('\r\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `organizacao-blocos-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  const termo = busca.trim().toLowerCase()
  const passaFiltro = (u: UnidadeBloco) =>
    (!termo || u.premio_nome.toLowerCase().includes(termo)) &&
    (situacao === 'todas' || (situacao === 'disponivel' ? u.status === 'disponivel' : u.status !== 'disponivel'))

  const excessos = editaveis.filter((c) => c !== SEM_BLOCO).filter((c) => (colunas[c]?.length ?? 0) > (capacidades[c] ?? 0))

  async function salvar() {
    if (!original) return
    setSalvando(true)
    setErro('')
    try {
      const itens = editaveis
        .filter((c) => c !== SEM_BLOCO)
        .map((c) => ({
          bloco_id: Number(c),
          unidades: colunas[c].map((u) => u.id),
          capacidade: capacidades[c] !== blocos.get(c)?.capacidade ? capacidades[c] : undefined,
        }))
      if (itens.length === 0) {
        aoSair(false)
        return
      }
      await requisitar(`${base}/distribuicao`, {
        metodo: 'PUT',
        corpo: { blocos: itens, versao: original.versao },
      })
      aoSair(true)
    } catch (e) {
      setErro(mensagem(e, 'Falha ao salvar a organização'))
      setConflito(e instanceof ErroApi && e.status === 409)
    } finally {
      setSalvando(false)
    }
  }

  function sair() {
    if (alterado && !confirm('Há alterações não salvas. Sair e descartar?')) return
    aoSair(false)
  }

  if (!original) return erro ? <Aviso tipo="erro">{erro}</Aviso> : <Carregando texto="Carregando distribuição..." />

  const opcoesDestino = editaveis.filter(recebe)
  const unica = selecionadas.length === 1 ? selecionadas[0] : null

  return (
    <div className={`space-y-3 ${selecionadas.length > 0 ? 'pb-28 lg:pb-0' : ''}`}>
      <div className="rounded-xl border border-borda bg-white p-4 shadow-suave">
        <div className="flex flex-wrap items-center gap-2">
          <div className="mr-auto min-w-0">
            <h2 className="text-base font-bold text-slate-900">Organizar prêmios manualmente</h2>
            <p className="text-xs text-slate-500">
              Cada unidade se move sozinha. Arraste entre os blocos, ou toque nas unidades e escolha o destino. Nada é
              gravado até “Salvar organização”.
            </p>
          </div>
          <button type="button" className="btn-neutro" onClick={sair}>
            <Icone nome="voltar" className="h-4 w-4" />
            Voltar
          </button>
          <button type="button" className="btn-neutro" disabled={!alterado || salvando} onClick={() => preparar(original)}>
            Cancelar alterações
          </button>
          <button
            type="button"
            className="btn-primario"
            disabled={salvando || excessos.length > 0 || !alterado}
            onClick={() => void salvar()}
          >
            {salvando ? 'Salvando...' : 'Salvar organização'}
          </button>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
          <input
            type="search"
            className="campo"
            placeholder="Pesquisar produto..."
            aria-label="Pesquisar produto"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          <select className="campo" aria-label="Filtrar por bloco" value={filtroBloco} onChange={(e) => setFiltroBloco(e.target.value)}>
            <option value="todos">Todos os blocos</option>
            {editaveis.map((c) => (
              <option key={c} value={c}>
                {nomeColuna(c)}
              </option>
            ))}
          </select>
          <select className="campo" aria-label="Filtrar por situação" value={situacao} onChange={(e) => setSituacao(e.target.value as Situacao)}>
            <option value="todas">Todas as situações</option>
            <option value="disponivel">Aguardando sorteio</option>
            <option value="sorteada">Já sorteadas</option>
          </select>
          <button
            type="button"
            className="btn-neutro sm:col-span-3 lg:col-span-1"
            onClick={exportar}
            title="Baixa uma planilha (CSV) com todos os blocos e a sequência dos prêmios, como está na tela"
          >
            <Icone nome="baixar" className="h-4 w-4" />
            Exportar
          </button>
        </div>

        {selecionadas.length > 0 && (
          // Celular/tablet: barra presa no rodapé, à mão enquanto se rola a lista.
          <div className="fixed inset-x-3 bottom-3 z-40 flex flex-wrap items-center gap-2 rounded-lg border border-marca-200 bg-marca-50 p-2 text-sm shadow-lg lg:static lg:mt-3 lg:border-0 lg:shadow-none">
            <span className="font-semibold text-marca-800">{selecionadas.length} unidade(s) selecionada(s)</span>
            <label className="sr-only" htmlFor="mover-para">
              Mover para
            </label>
            <select id="mover-para" className="campo w-auto py-1" value={destino} onChange={(e) => setDestino(e.target.value)}>
              <option value="">Mover para...</option>
              {opcoesDestino.map((c) => (
                <option key={c} value={c}>
                  {nomeColuna(c)}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn-primario px-3 py-1"
              disabled={!destino}
              onClick={() => {
                mover(selecionadas, destino, null)
                setSelecionadas([])
                setDestino('')
              }}
            >
              Mover
            </button>
            {unica !== null && (
              <>
                <button type="button" className="btn-neutro px-2 py-1" onClick={() => deslocar(unica, -1)} aria-label="Subir na ordem do bloco">
                  <Icone nome="acima" className="h-4 w-4" />
                </button>
                <button type="button" className="btn-neutro px-2 py-1" onClick={() => deslocar(unica, 1)} aria-label="Descer na ordem do bloco">
                  <Icone nome="abaixo" className="h-4 w-4" />
                </button>
              </>
            )}
            <button type="button" className="ml-auto text-xs font-medium text-slate-600 underline" onClick={() => setSelecionadas([])}>
              Limpar seleção
            </button>
          </div>
        )}
      </div>

      {erro && (
        <Aviso tipo="erro">
          {erro}
          {conflito && (
            <button type="button" className="mt-2 block font-semibold underline" onClick={recarregar}>
              Recarregar a organização atual
            </button>
          )}
        </Aviso>
      )}
      {excessos.length > 0 && (
        <Aviso tipo="atencao">
          Capacidade excedida em {excessos.map((c) => blocos.get(c)?.nome).join(', ')}. Aumente a capacidade no topo do
          bloco ou retire unidades para salvar.
        </Aviso>
      )}
      {congelados.length > 0 && (
        <p className="text-xs text-slate-500">
          Não exibidos (já iniciados, não podem ser reorganizados): {congelados.map((b) => b.nome).join(', ')}.
        </p>
      )}

      {/* Celular e tablet: colunas empilhadas (sem rolagem lateral). Computador: lado a
          lado, dividindo a largura; cada coluna rola por dentro, então a rolagem lateral
          (só com muitos blocos) fica logo abaixo e nenhuma coluna parece cortada. */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:overflow-x-auto lg:pb-3">
        {visiveis.map((chave) => {
          const bloco = blocos.get(chave)
          const itens = colunas[chave] ?? []
          const filtrados = itens.filter(passaFiltro)
          const cap = capacidades[chave] ?? 0
          const acima = bloco ? itens.length > cap : false
          const selecionaveis = filtrados.filter(movel).map((u) => u.id)
          return (
            <section
              key={chave}
              aria-label={bloco ? bloco.nome : 'Sem bloco'}
              onDragOver={(e) => {
                if (recebe(chave)) e.preventDefault()
              }}
              onDrop={(e) => {
                e.preventDefault()
                if (arrastando !== null) {
                  const grupo = selecionadas.includes(arrastando) ? selecionadas : [arrastando]
                  mover(grupo, chave, null)
                  setSelecionadas([])
                }
                setArrastando(null)
              }}
              className={`flex w-full flex-col rounded-xl border bg-slate-50 lg:max-h-[75vh] ${
                chave === SEM_BLOCO && itens.length === 0
                  ? 'lg:w-52 lg:flex-none'
                  : 'lg:w-auto lg:min-w-[15rem] lg:flex-1 lg:basis-0'
              } ${acima ? 'border-rose-400' : chave === SEM_BLOCO ? 'border-marca-200' : 'border-slate-200'}`}
            >
              <header className="space-y-1.5 border-b border-slate-200 p-3">
                {bloco ? (
                  <>
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-marca-600">{numeroBloco(bloco.numero)}</p>
                      <EtiquetaBloco status={bloco.status} />
                    </div>
                    <p className="truncate text-sm font-semibold text-slate-900">{bloco.nome}</p>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                      <span className={acima ? 'font-semibold text-rose-600' : 'font-semibold text-slate-900'}>{itens.length}</span>
                      <span>/</span>
                      {bloco.status === 'PLANEJADO' ? (
                        <input
                          type="number"
                          min={1}
                          max={1000}
                          aria-label={`Capacidade do ${bloco.nome}`}
                          className="w-16 rounded border border-slate-300 px-1 py-0.5"
                          value={cap}
                          onChange={(e) =>
                            setCapacidades((c) => ({ ...c, [chave]: Math.max(1, Math.min(1000, Number(e.target.value) || 1)) }))
                          }
                        />
                      ) : (
                        <span>{cap}</span>
                      )}
                      <Capacidade total={itens.length} capacidade={cap} />
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm font-semibold text-slate-900">Sem bloco</p>
                    <p className="text-xs text-slate-500">{itens.length} unidade(s) disponível(is) para distribuir</p>
                  </>
                )}
                <div className="flex items-center justify-between gap-2">
                  {selecionaveis.length > 0 ? (
                    <button
                      type="button"
                      className="text-xs font-semibold text-marca-700 hover:underline"
                      onClick={() => setSelecionadas((atual) => [...new Set([...atual, ...selecionaveis])])}
                    >
                      Selecionar {termo ? 'as encontradas' : 'todas'} ({selecionaveis.length})
                    </button>
                  ) : (
                    <span />
                  )}
                  {bloco && recebe(chave) && itens.length > 1 && (
                    <button
                      type="button"
                      className="btn-icone h-8 w-8 text-marca-700"
                      onClick={() => misturarBloco(chave)}
                      aria-label={`Misturar os prêmios do ${bloco.nome}`}
                      title="Misturar os prêmios deste bloco (sem repetir o mesmo prêmio seguido, quando possível)"
                    >
                      <Icone nome="dado" className="h-5 w-5" />
                    </button>
                  )}
                </div>
              </header>
              <ol className="flex min-h-20 flex-1 flex-col gap-1.5 p-2 lg:overflow-y-auto">
                {filtrados.map((u) => {
                  const pode = movel(u)
                  const marcada = selecionadas.includes(u.id)
                  const indice = itens.indexOf(u)
                  return (
                    <li
                      key={u.id}
                      draggable={pode}
                      onDragStart={(e) => {
                        e.dataTransfer.setData('text/plain', String(u.id))
                        e.dataTransfer.effectAllowed = 'move'
                        setArrastando(u.id)
                      }}
                      onDragEnd={() => setArrastando(null)}
                      onDragOver={(e) => {
                        if (recebe(chave)) e.preventDefault()
                      }}
                      onDrop={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        if (arrastando !== null && arrastando !== u.id) {
                          const grupo = selecionadas.includes(arrastando) ? selecionadas : [arrastando]
                          mover(grupo, chave, indice)
                          setSelecionadas([])
                        }
                        setArrastando(null)
                      }}
                    >
                      <button
                        type="button"
                        disabled={!pode}
                        onClick={() => alternar(u.id)}
                        aria-pressed={marcada}
                        title={pode ? 'Toque para selecionar; arraste para mover' : 'Unidade já sorteada: não muda de bloco'}
                        className={`flex w-full items-center gap-2 rounded-lg border bg-white p-1.5 text-left transition ${
                          marcada ? 'border-marca-500 bg-marca-50 ring-1 ring-marca-400' : 'border-slate-200 hover:border-slate-300'
                        } ${pode ? 'cursor-grab' : 'cursor-not-allowed opacity-60'} ${arrastando === u.id ? 'opacity-40' : ''}`}
                      >
                        <span
                          aria-hidden
                          className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                            marcada ? 'border-marca-600 bg-marca-600 text-white' : 'border-slate-300'
                          }`}
                        >
                          {marcada && <Icone nome="check" className="h-3 w-3" />}
                        </span>
                        <div className="h-9 w-9 shrink-0 overflow-hidden rounded bg-slate-100">
                          <ImagemPremio url={u.premio_imagem_url} nome={u.premio_nome} className="h-full w-full text-slate-400" />
                        </div>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-xs font-medium text-slate-900">{u.premio_nome}</span>
                          <span className="block text-[11px] text-slate-500">
                            Un. {u.numero}/{u.quantidade_premio}
                            {bloco ? ` · ${indice + 1}º` : ''}
                            {u.status !== 'disponivel' ? ' · sorteada' : ''}
                          </span>
                        </span>
                      </button>
                    </li>
                  )
                })}
                {filtrados.length === 0 && (
                  <li className="rounded-lg border border-dashed border-slate-300 p-3 text-center text-xs text-slate-400">
                    {itens.length > 0 ? 'Nenhuma unidade no filtro' : recebe(chave) ? 'Solte unidades aqui' : 'Vazio'}
                  </li>
                )}
              </ol>
            </section>
          )
        })}
      </div>
    </div>
  )
}
