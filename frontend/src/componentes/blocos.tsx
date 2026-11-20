import type { ReactNode } from 'react'
import type { Bloco, StatusBloco } from '../types'

const ROTULO_STATUS: Record<StatusBloco, { texto: string; classe: string }> = {
  PLANEJADO: { texto: 'Planejado', classe: 'bg-slate-100 text-slate-600' },
  EM_ANDAMENTO: { texto: 'Em andamento', classe: 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200' },
  PAUSADO: { texto: 'Pausado', classe: 'bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200' },
  FINALIZADO: { texto: 'Finalizado', classe: 'bg-slate-100 text-slate-700' },
}

export function EtiquetaBloco({ status }: { status: StatusBloco }) {
  const item = ROTULO_STATUS[status]
  return <span className={`etiqueta ${item.classe}`}>{item.texto}</span>
}

export function numeroBloco(numero: number): string {
  return `BLOCO ${String(numero).padStart(2, '0')}`
}

export function BarraProgresso({ percentual, rotulo }: { percentual: number; rotulo: string }) {
  return (
    <div
      role="progressbar"
      aria-label={rotulo}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percentual}
      className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200"
    >
      <div
        className="h-full rounded-full bg-marca-500 transition-[width] duration-300"
        style={{ width: `${percentual}%` }}
      />
    </div>
  )
}

/** Unidades atribuídas / capacidade, com o estado da capacidade. */
export function Capacidade({ total, capacidade }: { total: number; capacidade: number }) {
  const livre = capacidade - total
  const [texto, classe] =
    livre < 0
      ? [`Excedida em ${-livre}`, 'bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200']
      : livre === 0
        ? ['Completo', 'bg-emerald-50 text-emerald-700']
        : [`${livre} livre(s)`, 'bg-slate-100 text-slate-600']
  return <span className={`etiqueta ${classe}`}>{texto}</span>
}

export function CartaoBloco({
  bloco,
  destaque = false,
  topo,
  children,
}: {
  bloco: Bloco
  destaque?: boolean
  /** Controles no canto (ex.: subir/descer na ordem). */
  topo?: ReactNode
  children?: ReactNode
}) {
  return (
    <article
      className={`relative flex flex-col gap-3 overflow-hidden rounded-xl border bg-white p-4 shadow-suave ${
        destaque ? 'border-emerald-400 ring-1 ring-emerald-300' : 'border-borda'
      }`}
    >
      <span aria-hidden className="absolute inset-x-0 top-0 h-1 bg-marca-400" />
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-marca-600">{numeroBloco(bloco.numero)}</p>
          <h3 className="truncate text-base font-bold text-slate-900" title={bloco.nome}>
            {bloco.nome}
          </h3>
          {bloco.descricao && <p className="line-clamp-2 text-xs text-slate-500">{bloco.descricao}</p>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <EtiquetaBloco status={bloco.status} />
          {topo}
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-700">
          <strong className="text-lg tabular-nums text-slate-900">{bloco.total}</strong>
          <span className="text-slate-500">/{bloco.capacidade} unidades</span>
        </p>
        <Capacidade total={bloco.total} capacidade={bloco.capacidade} />
      </div>
      <dl className="grid grid-cols-2 gap-2 text-center">
        <div className="rounded-lg bg-slate-50 py-1.5">
          <dt className="text-[11px] text-slate-500">Sorteados</dt>
          <dd className="font-semibold tabular-nums text-slate-900">{bloco.sorteadas}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 py-1.5">
          <dt className="text-[11px] text-slate-500">Restantes</dt>
          <dd className="font-semibold tabular-nums text-slate-900">{bloco.restantes}</dd>
        </div>
      </dl>

      {/* Progresso: sorteadas sobre as unidades atribuídas (não sobre a capacidade). */}
      <div className="space-y-1">
        <BarraProgresso percentual={bloco.percentual} rotulo={`Progresso do ${bloco.nome}`} />
        <p className="text-right text-xs font-medium text-slate-500">{bloco.percentual}% concluído</p>
      </div>

      {children && <div className="mt-auto flex flex-wrap gap-2">{children}</div>}
    </article>
  )
}
