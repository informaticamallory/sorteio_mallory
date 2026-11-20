import type { ReactNode } from 'react'
import { useEffect } from 'react'
import Icone from './Icone'

export function Aviso({
  tipo = 'info',
  children,
}: {
  tipo?: 'info' | 'erro' | 'sucesso' | 'atencao'
  children: ReactNode
}) {
  const estilos = {
    info: 'border-sky-200 bg-sky-50 text-sky-900',
    erro: 'border-rose-200 bg-rose-50 text-rose-900',
    sucesso: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    atencao: 'border-amber-200 bg-amber-50 text-amber-900',
  }[tipo]
  return (
    <div role={tipo === 'erro' ? 'alert' : 'status'} className={`rounded-md border px-3 py-2.5 text-sm ${estilos}`}>
      {children}
    </div>
  )
}

export function Modal({
  titulo,
  aberto,
  aoFechar,
  children,
  largura = 'max-w-lg',
}: {
  titulo: string
  aberto: boolean
  aoFechar: () => void
  children: ReactNode
  largura?: string
}) {
  useEffect(() => {
    if (!aberto) return
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') aoFechar()
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [aberto, aoFechar])

  if (!aberto) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className={`w-full ${largura} max-h-[92vh] overflow-y-auto rounded-t-lg border border-borda bg-white shadow-lg sm:rounded-lg`}
      >
        <div className="flex items-center justify-between border-b border-borda px-5 py-3">
          <h2 className="text-base font-semibold text-slate-900">{titulo}</h2>
          <button type="button" onClick={aoFechar} aria-label="Fechar" className="btn-icone">
            <Icone nome="fechar" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  )
}

export function Etiqueta({ status }: { status: string }) {
  const mapa: Record<string, { texto: string; classe: string }> = {
    disponivel: { texto: 'Disponível', classe: 'bg-sky-100 text-sky-800' },
    sorteado: { texto: 'Sorteado', classe: 'bg-amber-100 text-amber-800' },
    entregue: { texto: 'Entregue', classe: 'bg-emerald-100 text-emerald-800' },
    valido: { texto: 'Válido', classe: 'bg-emerald-100 text-emerald-800' },
    anulado: { texto: 'Anulado', classe: 'bg-rose-100 text-rose-800' },
    pendente: { texto: 'Pendente', classe: 'bg-amber-100 text-amber-800' },
  }
  const item = mapa[status] ?? { texto: status, classe: 'bg-slate-100 text-slate-700' }
  return <span className={`etiqueta ${item.classe}`}>{item.texto}</span>
}

/** Espaco reservado quando nao ha imagem - evita o icone de imagem quebrada. */
export function ImagemPremio({
  url,
  nome,
  className = '',
  grande = false,
}: {
  url: string | null
  nome: string
  className?: string
  grande?: boolean
}) {
  if (url) {
    return (
      <img
        src={url}
        alt={`Imagem do prêmio ${nome}`}
        loading="lazy"
        className={`object-contain ${className}`}
      />
    )
  }
  return (
    <div
      role="img"
      aria-label={`Prêmio ${nome} sem imagem cadastrada`}
      className={`flex flex-col items-center justify-center gap-2 border border-dashed border-current/30 bg-current/5 ${className}`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        className={grande ? 'h-24 w-24 opacity-50' : 'h-8 w-8 opacity-40'}
        aria-hidden="true"
      >
        <path d="M20 12v9H4v-9" strokeLinecap="round" />
        <path d="M2 7h20v5H2z" />
        <path d="M12 21V7" />
        <path d="M12 7S10.5 3 8 3a2.5 2.5 0 0 0 0 5h4zM12 7s1.5-4 4-4a2.5 2.5 0 0 1 0 5h-4z" />
      </svg>
      <span className={grande ? 'text-xl font-semibold opacity-70' : 'text-[10px] opacity-60'}>
        Sem imagem
      </span>
    </div>
  )
}

export function Vazio({ titulo, descricao }: { titulo: string; descricao?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-5 py-8 text-center">
      <p className="font-medium text-slate-700">{titulo}</p>
      {descricao && <p className="mt-1 text-sm text-slate-500">{descricao}</p>}
    </div>
  )
}

export function Carregando({ texto = 'Carregando...' }: { texto?: string }) {
  return (
    <div className="flex items-center gap-3 px-1 py-6 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-marca-700" />
      {texto}
    </div>
  )
}
