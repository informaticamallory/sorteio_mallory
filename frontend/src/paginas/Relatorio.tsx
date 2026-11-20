import { useCallback, useEffect, useState } from 'react'
import { baixarArquivo, requisitar } from '../api'
import { Aviso, Carregando, Etiqueta, Vazio } from '../componentes/ui'
import type { Sorteio } from '../types'
import { usePainel } from './PainelLayout'
import { formatar } from './Historico'

const FILTROS = [
  { valor: 'todos', rotulo: 'Todos' },
  { valor: 'pendentes', rotulo: 'Pendentes' },
  { valor: 'entregues', rotulo: 'Entregues' },
  { valor: 'anulados', rotulo: 'Anulados' },
]

export default function Relatorio() {
  const { evento, resumo, recarregarResumo } = usePainel()
  const [lista, setLista] = useState<Sorteio[] | null>(null)
  const [filtro, setFiltro] = useState('todos')
  const [erro, setErro] = useState('')

  const carregar = useCallback(async () => {
    try {
      setLista(
        await requisitar<Sorteio[]>(`/api/events/${evento.id}/relatorio?filtro=${filtro}`),
      )
      setErro('')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao carregar o relatório')
    }
  }, [evento.id, filtro])

  useEffect(() => {
    void carregar()
    void recarregarResumo()
  }, [carregar, recarregarResumo])

  async function exportar(formato: 'csv' | 'xlsx') {
    setErro('')
    try {
      await baixarArquivo(
        `/api/events/${evento.id}/relatorio/export.${formato}?filtro=${filtro}`,
        `resultados.${formato}`,
      )
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao exportar')
    }
  }

  const cartoes = resumo
    ? [
        ['Participantes', resumo.participantes_total],
        ['Presentes', resumo.participantes_presentes],
        ['Elegíveis agora', resumo.participantes_elegiveis],
        ['Unidades sorteadas', resumo.unidades_sorteadas + resumo.unidades_entregues],
        ['Unidades disponíveis', resumo.unidades_disponiveis],
        ['Entregues', resumo.unidades_entregues],
        ['Anulações', resumo.sorteios_anulados],
      ]
    : []

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <section className="cartao grid grid-cols-2 divide-borda sm:grid-cols-4 lg:grid-cols-7 lg:divide-x">
        {cartoes.map(([rotulo, valor]) => (
          <div key={String(rotulo)} className="border-b border-borda px-4 py-3 lg:border-b-0">
            <p className="text-xs text-slate-500">{rotulo as string}</p>
            <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-900">{valor as number}</p>
          </div>
        ))}
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1">
          {FILTROS.map((f) => (
            <button
              key={f.valor}
              type="button"
              className={`aba ${filtro === f.valor ? 'aba-ativa' : ''}`}
              onClick={() => setFiltro(f.valor)}
            >
              {f.rotulo}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-neutro" onClick={() => void exportar('csv')}>
            Exportar CSV
          </button>
          <button type="button" className="btn-primario" onClick={() => void exportar('xlsx')}>
            Exportar XLSX
          </button>
        </div>
      </div>

      {lista === null ? (
        <Carregando />
      ) : lista.length === 0 ? (
        <Vazio titulo="Nada a exibir com este filtro" />
      ) : (
        <div className="cartao overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">Rodada</th>
                <th className="px-3 py-2">Prêmio</th>
                <th className="px-3 py-2">Ganhador</th>
                <th className="px-3 py-2">Matrícula</th>
                <th className="px-3 py-2">Setor</th>
                <th className="px-3 py-2">Situação</th>
                <th className="px-3 py-2">Entrega</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {lista.map((s) => (
                <tr key={s.id} className={s.status === 'anulado' ? 'bg-rose-50/50' : ''}>
                  <td className="px-3 py-2 text-slate-500">{s.rodada}</td>
                  <td className="px-3 py-2">
                    {s.premio_nome}
                    <span className="ml-1 text-xs text-slate-400">un. {s.unidade_numero}</span>
                  </td>
                  <td className="px-3 py-2 font-medium">{s.ganhador_nome}</td>
                  <td className="px-3 py-2 font-mono text-xs">{s.ganhador_matricula}</td>
                  <td className="px-3 py-2 text-slate-600">{s.ganhador_setor}</td>
                  <td className="px-3 py-2">
                    <Etiqueta status={s.status} />
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {s.status === 'anulado' ? (
                      <span className="text-rose-700">{s.motivo_anulacao}</span>
                    ) : s.entregue ? (
                      <span className="text-emerald-700">
                        {s.entregue_por} · {formatar(s.entregue_em, evento.fuso_horario)}
                      </span>
                    ) : (
                      <span className="text-amber-700">Pendente</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-slate-400">
        Horários exibidos no fuso {evento.fuso_horario}. Os registros são armazenados em UTC.
      </p>
    </div>
  )
}
