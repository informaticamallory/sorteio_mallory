import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { requisitar } from '../api'
import { useAuth } from '../auth'
import { BarraProgresso, EtiquetaBloco } from '../componentes/blocos'
import Icone from '../componentes/Icone'
import { Aviso, ImagemPremio } from '../componentes/ui'
import type {
  BlocoDetalhe,
  BlocosResumo,
  CredenciamentoResumo,
  PaginaSorteios,
  TelaoEstado,
} from '../types'
import { usePainel } from './PainelLayout'

const ATUALIZAR_MS = 10_000

const ESTADO_TELAO: Record<string, string> = {
  aguardando: 'Tela de espera',
  premio: 'Apresentando prêmio',
  sorteando: 'Sorteando',
  resultado: 'Mostrando ganhador',
  encerramento: 'Encerramento',
  carrossel_ganhadores: 'Apresentando ganhadores',
}

function hora(data: string, fuso: string): string {
  return new Date(`${data}Z`).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: fuso })
}

/** Painel operacional do evento: números do momento e o que precisa de atenção. */
export default function VisaoGeral() {
  const { evento, resumo, recarregarResumo } = usePainel()
  const { pode } = useAuth()
  const [blocos, setBlocos] = useState<BlocosResumo | null>(null)
  const [ativo, setAtivo] = useState<BlocoDetalhe | null>(null)
  const [ultimos, setUltimos] = useState<PaginaSorteios | null>(null)
  const [pendentes, setPendentes] = useState<PaginaSorteios | null>(null)
  const [credenciamento, setCredenciamento] = useState<CredenciamentoResumo | null>(null)
  const [telao, setTelao] = useState<TelaoEstado | null>(null)
  const [erro, setErro] = useState('')

  const carregar = useCallback(async () => {
    const base = `/api/events/${evento.id}`
    const filtro = `event_id=${evento.id}&status=valido`
    try {
      const [lista, ult, pend, cred, estado] = await Promise.all([
        requisitar<BlocosResumo>(`${base}/blocos`),
        requisitar<PaginaSorteios>(`/api/sorteios?${filtro}&por_pagina=8&ordenar=data&direcao=desc`),
        requisitar<PaginaSorteios>(`/api/sorteios?${filtro}&entrega=pendente&por_pagina=6&ordenar=data&direcao=asc`),
        requisitar<CredenciamentoResumo>(`${base}/credenciamento/resumo`),
        // O organizador acompanha, mas não controla o telão.
        pode('controlar_telao') ? requisitar<TelaoEstado>(`${base}/telao/estado`) : Promise.resolve(null),
        recarregarResumo(),
      ])
      setBlocos(lista)
      setUltimos(ult)
      setPendentes(pend)
      setCredenciamento(cred)
      setTelao(estado)
      setAtivo(
        lista.bloco_ativo_id ? await requisitar<BlocoDetalhe>(`${base}/blocos/${lista.bloco_ativo_id}`) : null,
      )
      setErro('')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao atualizar a visão geral')
    }
  }, [evento.id, recarregarResumo, pode])

  useEffect(() => {
    void carregar()
    const id = window.setInterval(() => void carregar(), ATUALIZAR_MS)
    return () => window.clearInterval(id)
  }, [carregar])

  const sorteados = resumo ? resumo.unidades_sorteadas + resumo.unidades_entregues : null
  const proxima = ativo?.unidades
    .filter((u) => u.status === 'disponivel')
    .sort((a, b) => (a.ordem_bloco ?? 0) - (b.ordem_bloco ?? 0))[0]
  const proximoBloco = blocos?.blocos.find((b) => b.status === 'PLANEJADO' || b.status === 'PAUSADO')

  const indicadores: { rotulo: string; valor: string; detalhe?: string }[] = [
    {
      rotulo: 'Presentes',
      valor: resumo ? String(resumo.participantes_presentes) : '—',
      detalhe: resumo ? `de ${resumo.participantes_total}` : undefined,
    },
    { rotulo: 'Elegíveis agora', valor: resumo ? String(resumo.participantes_elegiveis) : '—' },
    {
      rotulo: 'Prêmios sorteados',
      valor: sorteados !== null ? String(sorteados) : '—',
      detalhe: resumo ? `de ${resumo.unidades_total}` : undefined,
    },
    { rotulo: 'Restantes', valor: resumo ? String(resumo.unidades_disponiveis) : '—' },
    { rotulo: 'Entregas pendentes', valor: resumo ? String(resumo.unidades_sorteadas) : '—' },
    {
      rotulo: 'Cadastros feitos',
      valor: credenciamento ? String(credenciamento.com_conta) : '—',
      detalhe: credenciamento ? `de ${credenciamento.participantes}` : undefined,
    },
  ]

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* Faixa de indicadores */}
      <section className="cartao grid grid-cols-2 divide-borda sm:grid-cols-3 lg:grid-cols-6 lg:divide-x" aria-label="Indicadores">
        {indicadores.map((i) => (
          <div key={i.rotulo} className="border-b border-borda px-4 py-3 lg:border-b-0">
            <p className="text-xs text-slate-500">{i.rotulo}</p>
            <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">
              {i.valor}
              {i.detalhe && <span className="ml-1 text-xs font-normal text-slate-500">{i.detalhe}</span>}
            </p>
          </div>
        ))}
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* Próximo sorteio */}
          <section className="cartao">
            <header className="flex items-center justify-between border-b border-borda px-4 py-2.5">
              <h2 className="titulo-secao">Próximo sorteio</h2>
              {pode('controlar_sorteio') && (
                <Link to="../sorteio" className="btn-sutil h-8">
                  Ir para o sorteio
                  <Icone nome="avancar" />
                </Link>
              )}
            </header>
            <div className="space-y-3 p-4">
              {ativo ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-900">{ativo.bloco.nome}</span>
                      <EtiquetaBloco status={ativo.bloco.status} />
                    </div>
                    <span className="text-sm tabular-nums text-slate-600">
                      {ativo.bloco.sorteadas} de {ativo.bloco.total} sorteados
                    </span>
                  </div>
                  <BarraProgresso percentual={ativo.bloco.percentual} rotulo={`Progresso do ${ativo.bloco.nome}`} />
                  {proxima ? (
                    <div className="flex items-center gap-3 rounded-md border border-borda p-2.5">
                      <div className="h-11 w-11 shrink-0 overflow-hidden rounded bg-slate-50">
                        <ImagemPremio url={proxima.premio_imagem_url} nome={proxima.premio_nome} className="h-full w-full text-slate-400" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs text-slate-500">Próximo prêmio</p>
                        <p className="truncate font-medium text-slate-900">{proxima.premio_nome}</p>
                        <p className="text-xs text-slate-500">
                          Unidade {proxima.numero} de {proxima.quantidade_premio}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-600">
                      Todos os prêmios deste bloco foram sorteados. Finalize o bloco para apresentar os ganhadores.
                    </p>
                  )}
                </>
              ) : blocos?.modo_blocos ? (
                <p className="text-sm text-slate-600">
                  Nenhum bloco em andamento.
                  {proximoBloco ? ` Próximo: ${proximoBloco.nome} (${proximoBloco.total} prêmios).` : ' Todos os blocos foram finalizados.'}
                </p>
              ) : (
                <p className="text-sm text-slate-600">
                  Este evento não usa blocos: o sorteio segue prêmio a prêmio.
                  {resumo ? ` ${resumo.unidades_disponiveis} unidade(s) disponível(is).` : ''}
                </p>
              )}
              {telao && (
                <p className="flex items-center gap-1.5 text-xs text-slate-500">
                  <Icone nome="telao" className="h-3.5 w-3.5" />
                  Telão: {ESTADO_TELAO[telao.estado] ?? telao.estado}
                </p>
              )}
            </div>
          </section>

          {/* Últimos ganhadores */}
          <section className="cartao">
            <header className="flex items-center justify-between border-b border-borda px-4 py-2.5">
              <h2 className="titulo-secao">Últimos ganhadores</h2>
              <Link to="../historico" className="btn-sutil h-8">
                Histórico
                <Icone nome="avancar" />
              </Link>
            </header>
            {ultimos && ultimos.itens.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th className="w-14">Rodada</th>
                      <th>Ganhador</th>
                      <th className="hidden sm:table-cell">Prêmio</th>
                      <th className="hidden md:table-cell">Bloco</th>
                      <th className="hidden md:table-cell">Hora</th>
                      <th>Entrega</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ultimos.itens.map((s) => (
                      <tr key={s.id}>
                        <td className="tabular-nums text-slate-500">{s.rodada}</td>
                        <td>
                          <p className="font-medium text-slate-900">{s.ganhador_nome}</p>
                          <p className="text-xs text-slate-500 sm:hidden">{s.premio_nome}</p>
                        </td>
                        <td className="hidden text-slate-700 sm:table-cell">{s.premio_nome}</td>
                        <td className="hidden tabular-nums text-slate-600 md:table-cell">
                          {s.bloco_numero ? String(s.bloco_numero).padStart(2, '0') : '—'}
                        </td>
                        <td className="hidden tabular-nums text-slate-600 md:table-cell">
                          {hora(s.criado_em, evento.fuso_horario)}
                        </td>
                        <td>
                          {s.entregue ? (
                            <span className="etiqueta bg-emerald-50 text-emerald-700">Entregue</span>
                          ) : (
                            <span className="etiqueta bg-amber-50 text-amber-800">Pendente</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="px-4 py-6 text-sm text-slate-500">Nenhum sorteio realizado ainda.</p>
            )}
          </section>
        </div>

        <div className="space-y-4">
          {/* Pendências de entrega */}
          <section className="cartao">
            <header className="flex items-center justify-between border-b border-borda px-4 py-2.5">
              <h2 className="titulo-secao">
                Pendências de entrega
                {pendentes ? <span className="ml-1.5 font-normal text-slate-500">{pendentes.total}</span> : null}
              </h2>
              {pode('pesquisar_colaboradores') && (
                <Link to="../entregas" className="btn-sutil h-8">
                  Entregas
                  <Icone nome="avancar" />
                </Link>
              )}
            </header>
            {pendentes && pendentes.itens.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {pendentes.itens.map((s) => (
                  <li key={s.id} className="px-4 py-2">
                    <p className="truncate text-sm font-medium text-slate-900">{s.ganhador_nome}</p>
                    <p className="truncate text-xs text-slate-500">
                      {s.premio_nome}
                      {s.ganhador_pulseira ? ` · pulseira ${s.ganhador_pulseira}` : ''}
                    </p>
                  </li>
                ))}
                {pendentes.total > pendentes.itens.length && (
                  <li className="px-4 py-2">
                    <Link to="../historico?entrega=pendente&status=valido" className="text-xs font-medium text-marca-700 hover:underline">
                      Ver todas as {pendentes.total}
                    </Link>
                  </li>
                )}
              </ul>
            ) : (
              <p className="px-4 py-6 text-sm text-slate-500">Nenhuma entrega pendente.</p>
            )}
          </section>

          {/* Blocos */}
          {blocos && blocos.blocos.length > 0 && (
            <section className="cartao">
              <header className="flex items-center justify-between border-b border-borda px-4 py-2.5">
                <h2 className="titulo-secao">Blocos</h2>
                <Link to="../blocos" className="btn-sutil h-8">
                  Ver
                  <Icone nome="avancar" />
                </Link>
              </header>
              <ul className="divide-y divide-slate-100">
                {blocos.blocos.map((b) => (
                  <li key={b.id} className="flex items-center justify-between gap-2 px-4 py-2">
                    <span className="truncate text-sm text-slate-900">{b.nome}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="text-xs tabular-nums text-slate-500">
                        {b.sorteadas}/{b.total}
                      </span>
                      <EtiquetaBloco status={b.status} />
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
