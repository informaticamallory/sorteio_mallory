import { useState, type CSSProperties, type ReactNode } from 'react'
import { ImagemPremio } from './ui'

/*
 * Anúncio do ganhador no telão: faixa "GANHADOR(A) DO SORTEIO", cartão do
 * prêmio à esquerda e cartão do ganhador (foto, nome e número sorteado) à
 * direita, com arcos, brilhos e presentes ao fundo.
 *
 * Todas as cores derivam das cores do evento (--cor-fundo, --cor-primaria,
 * --cor-texto), então trocar as cores na Configuração muda o anúncio.
 */

const OURO = 'var(--cor-primaria)'
const OURO_CLARO = 'color-mix(in srgb, var(--cor-primaria) 45%, white)'
const OURO_ESCURO = 'color-mix(in srgb, var(--cor-primaria) 70%, black)'
const TINTA = 'color-mix(in srgb, var(--cor-fundo) 80%, black)' // texto escuro sobre o dourado
const GRADIENTE_OURO = `linear-gradient(180deg, ${OURO_CLARO} 0%, ${OURO} 48%, ${OURO_ESCURO} 100%)`
const GRADIENTE_OURO_H = `linear-gradient(90deg, ${OURO_ESCURO} 0%, ${OURO_CLARO} 35%, ${OURO} 65%, ${OURO_ESCURO} 100%)`
const BRILHO = `0 0 28px color-mix(in srgb, var(--cor-primaria) 45%, transparent)`

function textoOuro(): CSSProperties {
  return {
    backgroundImage: GRADIENTE_OURO,
    WebkitBackgroundClip: 'text',
    backgroundClip: 'text',
    color: 'transparent',
  }
}

export interface DadosAnuncio {
  nome: string
  fotoUrl: string | null
  numero: number | null | undefined
  /** Modo faixa de matrículas: a matrícula é o número sorteado exibido. */
  matricula?: string | null
  premioNome: string
  premioDescricao?: string | null
  premioImagemUrl: string | null
  /** Ex.: "Unidade 2 de 3" (opcional). */
  detalhePremio?: string | null
}

export default function AnuncioGanhador({
  dados,
  subtitulo = 'DO SORTEIO',
  reduzir,
  rodape,
}: {
  dados: DadosAnuncio
  subtitulo?: string
  reduzir: boolean
  rodape?: ReactNode
}) {
  const numero = dados.matricula
    ? dados.matricula
    : dados.numero === null || dados.numero === undefined
      ? null
      : String(dados.numero).padStart(4, '0')
  const numeroLongo = (numero?.length ?? 0) > 8

  return (
    <div className={`relative z-10 w-full max-w-[1500px] ${reduzir ? '' : 'animate-entra-vencedor'}`}>
      <Faixa subtitulo={subtitulo} />

      <div className="mt-[2.5vh] grid items-stretch gap-[3vw] lg:grid-cols-[1fr_1.25fr]">
        {/* ---------------------------------------------- prêmio */}
        <div className="rounded-[2rem] p-[3px]" style={{ background: GRADIENTE_OURO, boxShadow: BRILHO }}>
          <div className="flex h-full flex-col overflow-hidden rounded-[calc(2rem-3px)] bg-white">
            <div className="relative flex flex-1 items-center justify-center p-[2vh]" style={{ minHeight: '30vh' }}>
              <ImagemPremio
                url={dados.premioImagemUrl}
                nome={dados.premioNome}
                grande
                className="h-[30vh] w-full rounded-xl text-slate-400"
              />
              {dados.detalhePremio && (
                <span
                  className="absolute right-4 top-4 rounded-full px-3 py-1 text-sm font-bold"
                  style={{ background: GRADIENTE_OURO, color: TINTA }}
                >
                  {dados.detalhePremio}
                </span>
              )}
            </div>
            <div className="px-6 py-[1.4vh] text-center" style={{ background: GRADIENTE_OURO_H, color: TINTA }}>
              <p className="break-words text-[clamp(1.4rem,2.3vw,2.7rem)] font-extrabold leading-tight">
                {dados.premioNome}
              </p>
              {dados.premioDescricao && (
                <p className="mt-0.5 line-clamp-2 text-[clamp(0.95rem,1.4vw,1.5rem)] font-medium opacity-90">
                  {dados.premioDescricao}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* ---------------------------------------------- ganhador */}
        <div className="relative pt-[6vh]">
          <div
            className="relative flex h-full flex-col items-center rounded-[2rem] border-[3px] px-[3vw] pb-[3vh] pt-[7vh] text-center"
            style={{
              borderColor: OURO,
              background: 'color-mix(in srgb, var(--cor-fundo) 82%, black)',
              boxShadow: `${BRILHO}, inset 0 0 40px color-mix(in srgb, var(--cor-primaria) 12%, transparent)`,
            }}
          >
            {/* Foto + "PARABÉNS!" sobre a borda do cartão */}
            <div className="absolute -top-[6vh] left-1/2 flex -translate-x-1/2 items-center">
              <Avatar url={dados.fotoUrl} />
              <span
                className="-ml-6 whitespace-nowrap rounded-r-full py-[1vh] pl-10 pr-8 text-[clamp(1.2rem,2vw,2.4rem)] font-extrabold italic tracking-wide"
                style={{ background: GRADIENTE_OURO_H, color: TINTA, boxShadow: BRILHO }}
              >
                PARABÉNS!
              </span>
            </div>

            <h2
              className="line-clamp-2 break-words text-[clamp(2.4rem,4.4vw,5.4rem)] font-extrabold leading-[1.05]"
              style={{ color: 'var(--cor-texto)', textShadow: '0 4px 18px rgba(0,0,0,0.35)' }}
            >
              {dados.nome}
            </h2>

            <div
              className="my-[1.8vh] h-[3px] w-full max-w-xl rounded-full"
              style={{ background: `linear-gradient(90deg, transparent, ${OURO}, transparent)` }}
            />

            {numero && (
              <>
                <p className="text-[clamp(1.1rem,1.8vw,2.1rem)] font-medium" style={{ color: 'var(--cor-texto)' }}>
                  {dados.matricula ? 'Matrícula Sorteada' : 'Número Sorteado'}
                </p>
                <div className="mt-[1.2vh] flex items-center gap-[2vw]">
                  <IconePresente className="h-[9vh] w-[9vh] shrink-0" />
                  <div
                    className="rounded-full border-[3px] px-[3vw] py-[0.6vh]"
                    style={{ borderColor: OURO, background: 'rgba(0,0,0,0.25)', boxShadow: BRILHO }}
                  >
                    <span
                      className={`block ${
                        numeroLongo ? 'break-all text-[clamp(2rem,3.6vw,4.4rem)]' : 'text-[clamp(3.2rem,6.2vw,7.4rem)]'
                      } font-black leading-none tabular-nums tracking-wide`}
                      style={textoOuro()}
                    >
                      {numero}
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {rodape}
    </div>
  )
}

function Faixa({ subtitulo }: { subtitulo: string }) {
  return (
    <div className="flex flex-col items-center">
      <IconePresente className="mb-[-1vh] h-[5vh] w-[5vh]" />
      <div className="relative">
        {/* pontas da faixa */}
        <span
          aria-hidden="true"
          className="absolute -left-[4.5vw] top-[1.6vh] h-[78%] w-[7vw]"
          style={{ background: OURO_ESCURO, clipPath: 'polygon(0 0, 100% 0, 100% 100%, 0 100%, 28% 50%)' }}
        />
        <span
          aria-hidden="true"
          className="absolute -right-[4.5vw] top-[1.6vh] h-[78%] w-[7vw]"
          style={{ background: OURO_ESCURO, clipPath: 'polygon(0 0, 100% 0, 72% 50%, 100% 100%, 0 100%)' }}
        />
        <h1
          className="relative rounded-md px-[4vw] py-[0.8vh] text-[clamp(2rem,3.9vw,4.6rem)] font-black leading-none tracking-wide"
          style={{ background: GRADIENTE_OURO, color: TINTA, boxShadow: BRILHO }}
        >
          GANHADOR(A)
        </h1>
      </div>
      <p
        className="mt-[1vh] flex items-center gap-4 text-[clamp(1.1rem,2vw,2.4rem)] font-semibold tracking-[0.2em]"
        style={{ color: 'var(--cor-texto)' }}
      >
        <span className="h-[3px] w-[4vw] rounded-full" style={{ background: OURO }} />
        {subtitulo}
        <span className="h-[3px] w-[4vw] rounded-full" style={{ background: OURO }} />
      </p>
    </div>
  )
}

function Avatar({ url }: { url: string | null }) {
  const [falhou, setFalhou] = useState(false)
  return (
    <div
      className="relative z-10 h-[12vh] w-[12vh] shrink-0 rounded-full p-[5px]"
      style={{ background: GRADIENTE_OURO, boxShadow: BRILHO }}
    >
      <div
        className="flex h-full w-full items-center justify-center overflow-hidden rounded-full"
        style={{ background: 'var(--cor-fundo)' }}
      >
        {url && !falhou ? (
          <img src={url} alt="" onError={() => setFalhou(true)} className="h-full w-full object-cover" />
        ) : (
          <svg viewBox="0 0 64 64" className="h-[62%] w-[62%]" aria-hidden="true">
            <circle cx="32" cy="22" r="13" fill={OURO} />
            <path d="M8 60c2-14 12-22 24-22s22 8 24 22z" fill={OURO} />
          </svg>
        )}
      </div>
    </div>
  )
}

function IconePresente({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true" fill="none" stroke={OURO} strokeWidth="3.2"
      strokeLinejoin="round" strokeLinecap="round">
      <rect x="10" y="26" width="44" height="32" rx="2" />
      <rect x="6" y="18" width="52" height="10" rx="2" />
      <path d="M32 18v40" />
      <path d="M32 18c-4-9-14-12-16-6s8 6 16 6zM32 18c4-9 14-12 16-6s-8 6-16 6z" />
    </svg>
  )
}

/** Arcos dourados, brilhos e caixas de presente ao fundo do anúncio. */
export function FundoFestivo({ reduzir }: { reduzir: boolean }) {
  const brilhos = [
    [8, 18, 6], [16, 70, 4], [27, 12, 3], [70, 9, 5], [86, 24, 4], [92, 62, 6],
    [12, 42, 3], [80, 80, 3], [45, 6, 3], [60, 92, 4], [35, 88, 3], [96, 40, 3],
  ]
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {/* brilho central suave */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 50% 45%, color-mix(in srgb, var(--cor-destaque) 28%, transparent) 0%, transparent 60%)',
        }}
      />
      {/* arcos laterais */}
      {[
        { left: '-38vh', right: undefined },
        { left: undefined, right: '-38vh' },
      ].map((lado, i) => (
        <div
          key={i}
          className="absolute top-[-12vh] h-[124vh] w-[80vh] rounded-full"
          style={{
            left: lado.left,
            right: lado.right,
            border: `4px solid ${OURO}`,
            boxShadow: `0 0 40px color-mix(in srgb, var(--cor-primaria) 55%, transparent), inset 0 0 30px color-mix(in srgb, var(--cor-primaria) 30%, transparent)`,
            opacity: 0.85,
          }}
        />
      ))}
      {/* brilhos */}
      {brilhos.map(([x, y, t], i) => (
        <svg
          key={i}
          viewBox="0 0 20 20"
          className={reduzir ? '' : 'animate-cintila'}
          style={{
            position: 'absolute',
            left: `${x}%`,
            top: `${y}%`,
            width: `${t * 0.45}vh`,
            height: `${t * 0.45}vh`,
            animationDelay: `${(i % 6) * 0.4}s`,
          }}
        >
          <path d="M10 0 12 8 20 10 12 12 10 20 8 12 0 10 8 8z" fill={OURO_CLARO} />
        </svg>
      ))}
      {/* caixas de presente nos cantos */}
      <CaixaPresente className="absolute -bottom-[3vh] -left-[3vh] h-[24vh] w-[24vh]" />
      <CaixaPresente className="absolute -bottom-[3vh] -right-[3vh] h-[24vh] w-[24vh] -scale-x-100" />
    </div>
  )
}

function CaixaPresente({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className}>
      <defs>
        <linearGradient id="caixa" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F4E7D3" />
          <stop offset="1" stopColor="#C9AE8A" />
        </linearGradient>
      </defs>
      <rect x="18" y="52" width="84" height="64" rx="4" fill="url(#caixa)" />
      <rect x="12" y="40" width="96" height="18" rx="4" fill="#EBDCC4" />
      <rect x="52" y="40" width="16" height="76" style={{ fill: OURO }} />
      <path d="M60 40c-8-18-30-24-34-12s16 12 34 12zM60 40c8-18 30-24 34-12s-16 12-34 12z" style={{ fill: OURO }} />
    </svg>
  )
}
