import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Icone, { type NomeIcone } from './Icone'
import LogoMallory from './LogoMallory'

/**
 * Pecas visuais da identidade Mallory (preto, branco e laranja), usadas nas
 * telas publicas: login e Recepcao.
 */

/** Botao escuro do cabecalho (Inicio, Trocar evento). */
export const CLASSE_BOTAO_CABECALHO =
  'rec-foco inline-flex h-9 items-center gap-1 rounded-md border border-white/25 bg-mallory-grafite px-3 text-sm font-medium text-white hover:border-white/50 focus-visible:ring-offset-mallory-preto'

export function CabecalhoMallory({
  secao,
  icone,
  evento,
  mostrarSecao = true,
  children,
}: {
  secao: string
  icone: NomeIcone
  /** Nome do evento ativo, quando a tela pertence a um evento (aparece inteiro). */
  evento?: string
  /** false: sem o rótulo da seção (a própria tela já tem um título grande). */
  mostrarSecao?: boolean
  /** Acoes a direita (Inicio, Trocar evento...). */
  children?: ReactNode
}) {
  return (
    <header className="relative overflow-hidden bg-mallory-preto text-white">
      {/* Detalhe curvo laranja no canto direito. */}
      <svg
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-1/2 w-1/3 lg:h-full lg:w-[46%] lg:max-w-[520px]"
        viewBox="0 0 520 80"
        preserveAspectRatio="none"
      >
        <path d="M520 30 C 420 70, 300 78, 170 80 L 520 80 Z" fill="#E65300" opacity="0.9" />
        <path d="M520 46 C 440 74, 360 80, 260 80 L 520 80 Z" fill="#F16425" />
      </svg>

      <div className="relative mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6 sm:py-4">
        <Link to="/login" className="rec-foco rounded focus-visible:ring-offset-mallory-preto" title="Tela inicial">
          <LogoMallory className="h-10 w-auto md:h-14" />
        </Link>
        {/* Celular: logo + acoes na 1a linha, secao na 2a, evento na 3a.
            Tablet: evento em linha propria. A partir de 1024 px: tudo numa linha. */}
        {mostrarSecao && (
          <>
            <span aria-hidden className="hidden h-8 w-0.5 rounded bg-mallory-laranja sm:block" />
            <span className="order-2 flex items-center gap-2 text-base font-semibold sm:order-none sm:text-lg">
              <Icone nome={icone} className="h-5 w-5 text-mallory-laranja sm:h-6 sm:w-6" />
              {secao}
            </span>
          </>
        )}
        {evento && (
          <>
            <span aria-hidden className={`hidden h-7 w-px bg-white/25 ${mostrarSecao ? 'lg:block' : 'sm:block'}`} />
            {/* Nome inteiro: quebra em mais linhas em vez de cortar com "...". */}
            <span className="order-last flex w-full min-w-0 items-start gap-2 pr-[18%] text-sm text-white/90 lg:order-none lg:w-auto lg:flex-1 lg:items-center lg:pr-0 lg:text-base">
              <Icone nome="eventos" className="h-5 w-5 shrink-0 text-white/80" />
              <span className="min-w-0 break-words">{evento}</span>
            </span>
          </>
        )}
        {children && <nav className="order-1 ml-auto flex items-center gap-2 sm:order-none">{children}</nav>}
      </div>
    </header>
  )
}

/** Faixa discreta abaixo do cabecalho, so em eventos de demonstracao. */
export function FaixaDemo() {
  return (
    <div className="border-b border-mallory-borda bg-mallory-claro px-4 py-2 text-center text-sm text-mallory-preto">
      <span className="inline-flex items-center gap-2">
        <Icone nome="info" className="h-4 w-4 shrink-0 text-mallory-acao" />
        Evento de demonstração — dados fictícios
      </span>
    </div>
  )
}

/** Titulo de tela com o detalhe laranja e um subtitulo. */
export function TituloSecao({ titulo, subtitulo }: { titulo: string; subtitulo: string }) {
  return (
    <div>
      <h1 className="text-2xl font-bold leading-tight sm:text-3xl">{titulo}</h1>
      <span aria-hidden className="mt-2 block h-1 w-12 rounded-full bg-mallory-laranja" />
      <p className="mt-3 text-base text-mallory-texto">{subtitulo}</p>
    </div>
  )
}

/** Painel de boas-vindas: "<prefixo> Mallory", com detalhe laranja. */
export function BoasVindasMallory({ prefixo, subtitulo }: { prefixo: string; subtitulo: string }) {
  return (
    <section className="rec-painel px-6 py-8 text-center sm:py-10">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight sm:text-4xl">
        {prefixo} <span className="text-mallory-escuro">Mallory</span>
      </h1>
      <span aria-hidden className="mx-auto mt-3 block h-1 w-16 rounded-full bg-mallory-laranja" />
      <p className="mt-4 text-base text-mallory-texto sm:text-lg">{subtitulo}</p>
    </section>
  )
}

/** Moldura dos cartoes: laranja (destaque) ou branca com canto laranja. */
export function MolduraCartao({ destaque, children }: { destaque: boolean; children: ReactNode }) {
  return (
    <section
      className={`relative flex flex-col overflow-hidden rounded-2xl p-6 shadow-suave sm:p-8 ${
        destaque ? 'bg-gradient-to-br from-[#DD5000] to-[#B84200] text-white' : 'border border-slate-200 bg-white'
      }`}
    >
      {destaque ? (
        <Icone nome="participantes" className="pointer-events-none absolute -right-3 -top-3 h-28 w-28 text-white/10" />
      ) : (
        <svg aria-hidden className="pointer-events-none absolute bottom-0 right-0 h-16 w-16" viewBox="0 0 64 64">
          <path d="M64 8 C 60 40, 40 60, 8 64 L 64 64 Z" fill="#F16425" />
        </svg>
      )}
      {children}
    </section>
  )
}

/** Icone grande + titulo + descricao, com o separador vertical. */
export function TopoCartao(props: { destaque: boolean; icone: NomeIcone; titulo: string; descricao: string }) {
  const { destaque } = props
  return (
    <div className="relative flex items-start gap-5">
      <span
        className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-xl ${
          destaque ? 'bg-white/15 text-white ring-1 ring-white/30' : 'bg-mallory-claro text-mallory-acao'
        }`}
      >
        <Icone nome={props.icone} className="h-9 w-9" />
      </span>
      <div className={`min-w-0 border-l-2 pl-5 ${destaque ? 'border-white/40' : 'border-mallory-laranja'}`}>
        <h2 className={`text-2xl font-bold leading-tight ${destaque ? 'text-white' : 'text-mallory-preto'}`}>
          {props.titulo}
        </h2>
        <p className={`mt-2 text-base ${destaque ? 'text-white' : 'text-mallory-texto'}`}>{props.descricao}</p>
      </div>
    </div>
  )
}

/** Cartao de acao: abre uma tela (onClick) ou navega para uma rota (para). */
export function CartaoAcao(props: {
  variante: 'destaque' | 'claro'
  icone: NomeIcone
  titulo: string
  descricao: string
  acao: string
  onClick?: () => void
  para?: string
  /** Conteudo opcional entre o topo e o botao. */
  children?: ReactNode
}) {
  const destaque = props.variante === 'destaque'
  const classe = `relative mt-auto ${
    destaque
      ? 'rec-btn w-full bg-white text-mallory-preto hover:bg-mallory-claro focus-visible:ring-white focus-visible:ring-offset-[#C44800]'
      : 'rec-btn-contorno w-full'
  }`
  const conteudo = (
    <>
      {props.acao}
      <Icone nome="seta" className="h-5 w-5 text-mallory-acao" />
    </>
  )
  return (
    <MolduraCartao destaque={destaque}>
      <TopoCartao destaque={destaque} icone={props.icone} titulo={props.titulo} descricao={props.descricao} />
      <div className="flex flex-1 flex-col pt-7">
        {props.children && <div className="relative mb-7">{props.children}</div>}
        {props.para ? (
          <Link to={props.para} className={classe}>
            {conteudo}
          </Link>
        ) : (
          <button type="button" onClick={props.onClick} className={classe}>
            {conteudo}
          </button>
        )}
      </div>
    </MolduraCartao>
  )
}

export function RodapeMallory({ secao }: { secao: string }) {
  return (
    <footer className="mx-auto flex w-full max-w-6xl items-center gap-4 px-4 pb-6 text-sm text-mallory-texto sm:px-6">
      <span aria-hidden className="h-px flex-1 bg-gradient-to-r from-transparent to-mallory-laranja/60" />
      <span className="flex items-center gap-3 whitespace-nowrap">
        Sorteios Mallory
        <span aria-hidden className="h-4 w-px bg-mallory-laranja" />
        {secao}
      </span>
      <span aria-hidden className="h-px flex-1 bg-gradient-to-l from-transparent to-mallory-laranja/60" />
    </footer>
  )
}
