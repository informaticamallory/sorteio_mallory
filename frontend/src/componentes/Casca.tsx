import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { ROTULO_PAPEL, useAuth } from '../auth'
import Icone, { type NomeIcone } from './Icone'
import LogoMallory from './LogoMallory'

export interface ItemMenu {
  para: string
  rotulo: string
  icone: NomeIcone
  /** Link absoluto aberto em outra aba (ex.: telao). */
  externo?: boolean
  /** Ativo apenas na rota exata. */
  fim?: boolean
}

/**
 * Estrutura comum do painel da equipe: menu lateral grafite (fixo no
 * computador, gaveta no celular) e area de trabalho com cabecalho da pagina.
 */
export default function Casca({
  contexto,
  itens,
  titulo,
  subtitulo,
  acoes,
  faixa,
  children,
}: {
  contexto?: ReactNode
  itens: ItemMenu[]
  titulo: string
  subtitulo?: string
  acoes?: ReactNode
  faixa?: ReactNode
  children: ReactNode
}) {
  const [aberto, setAberto] = useState(false)
  const local = useLocation()

  // Fecha a gaveta ao navegar.
  useEffect(() => setAberto(false), [local.pathname])

  return (
    <div className="min-h-full bg-fundo lg:pl-60">
      {/* Barra superior (celular e tablet) */}
      <header className="sticky top-0 z-30 flex h-12 items-center gap-2 bg-mallory-preto px-2 text-white lg:hidden">
        <button
          type="button"
          onClick={() => setAberto(true)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-grafite-300 hover:bg-white/10 hover:text-white"
          aria-label="Abrir menu"
        >
          <Icone nome="menu" className="h-5 w-5" />
        </button>
        <Link to="/" className="shrink-0" title="Sorteios Mallory">
          <LogoMallory className="h-4 w-auto" />
        </Link>
      </header>

      {aberto && (
        <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={() => setAberto(false)} aria-hidden="true" />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-60 flex-col bg-grafite-900 text-grafite-300 transition-transform lg:translate-x-0 ${
          aberto ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Menu principal"
      >
        <div className="flex h-14 items-center justify-between border-b border-white/10 bg-mallory-preto px-4">
          <Link to="/" className="min-w-0" title="Sorteios Mallory">
            <LogoMallory className="h-5 w-auto max-w-full" />
          </Link>
          <button
            type="button"
            onClick={() => setAberto(false)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-white/10 lg:hidden"
            aria-label="Fechar menu"
          >
            <Icone nome="fechar" />
          </button>
        </div>

        {contexto && <div className="border-b border-white/10 px-4 py-3">{contexto}</div>}

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
          {itens.map((item) =>
            item.externo ? (
              <a
                key={item.para}
                href={item.para}
                target="_blank"
                rel="noreferrer"
                className="flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm hover:bg-white/5 hover:text-white"
              >
                <Icone nome={item.icone} />
                <span className="flex-1 truncate">{item.rotulo}</span>
                <Icone nome="externo" className="h-3.5 w-3.5 opacity-60" />
              </a>
            ) : (
              <NavLink
                key={item.para}
                to={item.para}
                end={item.fim}
                className={({ isActive }) =>
                  `relative flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm ${
                    isActive ? 'bg-marca-600 font-semibold text-white shadow-sm' : 'hover:bg-white/5 hover:text-white'
                  }`
                }
              >
                {() => (
                  <>
                    <Icone nome={item.icone} />
                    <span className="truncate">{item.rotulo}</span>
                  </>
                )}
              </NavLink>
            ),
          )}
        </nav>

        <RodapeUsuario />
      </aside>

      {/* Cabeçalho da página: preto com o detalhe curvo laranja (identidade Mallory). */}
      <header className="relative overflow-hidden bg-mallory-preto text-white">
        <svg
          aria-hidden
          className="pointer-events-none absolute bottom-0 right-0 h-full w-1/3 max-w-[420px]"
          viewBox="0 0 520 80"
          preserveAspectRatio="none"
        >
          <path d="M520 30 C 420 70, 300 78, 170 80 L 520 80 Z" fill="#E65300" opacity="0.9" />
          <path d="M520 46 C 440 74, 360 80, 260 80 L 520 80 Z" fill="#F16425" />
        </svg>
        <div className="relative mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-3 px-4 py-4 sm:px-6">
          <div className="min-w-0 pr-[18%] sm:pr-0">
            <h1 className="truncate text-xl font-bold leading-tight text-white">{titulo}</h1>
            {subtitulo && <p className="truncate text-[13px] text-white/75">{subtitulo}</p>}
          </div>
          {acoes && <div className="relative flex flex-wrap items-center gap-2">{acoes}</div>}
        </div>
      </header>

      {faixa}

      <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6">
        <main>{children}</main>
      </div>
    </div>
  )
}

function RodapeUsuario() {
  const { usuario, sair } = useAuth()
  if (!usuario) return null
  return (
    <div className="border-t border-white/10 p-3">
      <p className="truncate text-sm font-medium text-white">{usuario.nome}</p>
      <p className="truncate text-xs text-grafite-400">{ROTULO_PAPEL[usuario.papel]}</p>
      {usuario.tem_cartao && usuario.papel !== 'COLABORADOR' && (
        <Link
          to="/minha-area"
          className="mt-2 flex h-8 items-center gap-1.5 rounded-md px-2 text-xs hover:bg-white/10 hover:text-white"
        >
          <Icone nome="bilhete" className="h-3.5 w-3.5 text-mallory-laranja" />
          Meu Cartão da Sorte
        </Link>
      )}
      <div className="mt-2 flex gap-1">
        <Link
          to="/trocar-senha"
          className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md text-xs hover:bg-white/10 hover:text-white"
        >
          <Icone nome="senha" className="h-3.5 w-3.5" />
          Senha
        </Link>
        <button
          type="button"
          onClick={sair}
          className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md text-xs hover:bg-white/10 hover:text-white"
        >
          <Icone nome="sair" className="h-3.5 w-3.5" />
          Sair
        </button>
      </div>
    </div>
  )
}
