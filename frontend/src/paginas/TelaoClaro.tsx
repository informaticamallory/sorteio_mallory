import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { usePosicaoCarrossel } from '../carrossel'
import { AVISO_IMAGEM_ILUSTRATIVA } from '../componentes/AnuncioGanhador'
import Confete from '../componentes/Confete'
import { ImagemPremio } from '../componentes/ui'
import { somRufar, somVitoria } from '../som'
import type { SlideCarrossel, TelaoEstado } from '../types'
import type { Conexao } from '../useTelao'

/*
 * Telão no tema "Mallory claro" (modelo da Mallory): fundo cinza claro,
 * laranja #ff5d1d, grafite #606060, fonte Sora. No sorteio, rolos de números
 * giram como caça-níquel e param no número que o servidor JÁ sorteou — a
 * animação só apresenta o resultado gravado; nada aqui escolhe ganhador.
 *
 * Medidas: o modelo tem 2000 x 1125. `u(n)` converte n pixels do modelo numa
 * unidade proporcional à tela (cabe inteira em 16:9 e em qualquer proporção).
 */
const u = (n: number) => `calc(${n} * var(--u))`

// Cores do tema: variaveis CSS preenchidas com as cores do evento (Configuracao).
const LARANJA = 'var(--tc-destaque)'
const CINZA = 'var(--tc-painel)'
const GRAFITE = 'var(--tc-texto)'
// Tons derivados (bordas e detalhes), sempre a partir das cores do evento.
const CINZA_SUAVE = 'color-mix(in srgb, var(--tc-painel) 55%, var(--tc-fundo))'
const CINZA_BORDA = 'color-mix(in srgb, var(--tc-painel) 80%, var(--tc-texto))'

// Revelação em três tempos: rolos param (um a um), nome sozinho, card completo.
const PARADA_POR_ROLO_MS = 350
const POUSO_MS = 700
const NOME_MS = 1800

/** Cores do tema claro configuradas no evento (ou a paleta Mallory). */
export const PALETA_MALLORY = { fundo: '#eeeeee', painel: '#dddddd', destaque: '#ff5d1d', texto: '#606060' }
function coresClaro(estado: TelaoEstado) {
  return { ...PALETA_MALLORY, ...(estado.evento.cores_claro ?? {}) }
}

/** Quanto a revelação do tema claro dura depois do horário de revelação. */
export function duracaoRevelacaoClaro(digitos = 4): number {
  return digitos * PARADA_POR_ROLO_MS + POUSO_MS + NOME_MS
}

export function numeroExibido(numero: number | null | undefined, matricula: string | null | undefined): string | null {
  if (matricula) return matricula
  if (numero === null || numero === undefined) return null
  return String(numero).padStart(4, '0')
}

/** Milissegundos desde a revelação, pelo relógio do servidor (F5 não repete a festa). */
function msDesdeRevelacao(estado: TelaoEstado): number {
  if (!estado.revelar_em) return Number.POSITIVE_INFINITY
  return new Date(estado.servidor_agora).getTime() - new Date(estado.revelar_em).getTime()
}

export default function TelaoClaro({
  estado,
  conexao,
  reduzir,
  somAtivo,
  controlesVisiveis,
  mostrarAtivarSom,
  aoAtivarSom,
  aoAlternarAnimacoes,
  aoTelaCheia,
}: {
  estado: TelaoEstado
  conexao: Conexao
  reduzir: boolean
  somAtivo: boolean
  controlesVisiveis: boolean
  mostrarAtivarSom: boolean
  aoAtivarSom: () => void
  aoAlternarAnimacoes: () => void
  aoTelaCheia: () => void
}) {
  const mostrarCaixas = estado.estado !== 'aguardando' && estado.estado !== 'encerramento'
  const cores = coresClaro(estado)
  return (
    <div
      className="telao-claro relative h-full min-h-full w-full overflow-hidden"
      style={
        {
          '--u': 'min(0.05vw, 0.08889vh)',
          '--tc-fundo': cores.fundo,
          '--tc-painel': cores.painel,
          '--tc-destaque': cores.destaque,
          '--tc-texto': cores.texto,
        } as CSSProperties
      }
    >
      {/* ------------------------------------------------ cabeçalho */}
      <div
        className="absolute z-20 flex items-center rounded-full"
        style={{ left: u(88), top: u(88), height: u(46), padding: `0 ${u(30)}`, gap: u(30), background: CINZA }}
      >
        <MarcaMallory />
        <span style={{ width: 1, height: u(26), background: CINZA_BORDA }} />
        <span style={{ fontSize: u(10.5), letterSpacing: u(3.2), fontWeight: 500 }}>SORTEIOS INTERNOS</span>
      </div>
      {mostrarCaixas && (
        <div className="absolute z-20 flex" style={{ right: u(88), top: u(88), gap: u(22) }}>
          {estado.bloco && <Caixa rotulo="BLOCO" valor={String(estado.bloco.numero).padStart(2, '0')} />}
          {estado.rodada !== null && <Caixa rotulo="RODADA" valor={String(estado.rodada)} />}
        </div>
      )}

      {/* ------------------------------------------------ estados */}
      <main className="absolute inset-0 z-10 flex items-center justify-center">
        {estado.estado === 'aguardando' && <Aguardando estado={estado} reduzir={reduzir} />}
        {estado.estado === 'premio' && <ProximoPremio estado={estado} reduzir={reduzir} />}
        {estado.estado === 'sorteando' && <Sorteando estado={estado} reduzir={reduzir} somAtivo={somAtivo} />}
        {estado.estado === 'resultado' && <Resultado estado={estado} reduzir={reduzir} somAtivo={somAtivo} />}
        {estado.estado === 'carrossel_ganhadores' && <Carrossel estado={estado} reduzir={reduzir} />}
        {estado.estado === 'encerramento' && <Encerramento estado={estado} />}
      </main>

      {/* ------------------------------------------------ controles */}
      <div
        className={`absolute z-20 flex transition-opacity duration-500 ${controlesVisiveis ? 'opacity-100' : 'opacity-0'}`}
        style={{ right: u(88), bottom: u(88), gap: u(28) }}
      >
        <Controle titulo={`Conexão: ${conexao}`}>
          {conexao === 'conectado' ? 'AO VIVO' : conexao === 'reconectando' ? 'RECONECTANDO' : 'OFFLINE'}
        </Controle>
        {mostrarAtivarSom && (
          <Controle titulo="Ativar som" aoClicar={aoAtivarSom}>
            ATIVAR SOM
          </Controle>
        )}
        <Controle titulo="Alternar animações reduzidas" aoClicar={aoAlternarAnimacoes}>
          {reduzir ? 'ANIMAÇÕES OFF' : 'ANIMAÇÕES ON'}
        </Controle>
        <Controle titulo="Tela cheia" aoClicar={aoTelaCheia}>
          TELA CHEIA
        </Controle>
      </div>
    </div>
  )
}

/** Logo laranja da Mallory (arquivo oficial em public/marca); sem ele, o nome em texto. */
function MarcaMallory() {
  const [falhou, setFalhou] = useState(false)
  if (falhou) {
    return <span style={{ color: LARANJA, fontWeight: 800, fontSize: u(30), letterSpacing: u(-1) }}>MALLORY</span>
  }
  return (
    <img
      src="/marca/mallory-laranja.png"
      alt="Mallory"
      onError={() => setFalhou(true)}
      style={{ height: u(30), width: 'auto' }}
    />
  )
}

function Caixa({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center"
      style={{ width: u(126), height: u(126), borderRadius: u(16), background: CINZA }}
    >
      <span style={{ fontSize: u(11.5), fontWeight: 500 }}>{rotulo}</span>
      <span style={{ fontSize: u(60), fontWeight: 800, lineHeight: 1.05, color: LARANJA }}>{valor}</span>
    </div>
  )
}

function Controle({ children, titulo, aoClicar }: { children: ReactNode; titulo: string; aoClicar?: () => void }) {
  const estilo: CSSProperties = {
    height: u(46),
    minWidth: u(140),
    padding: `0 ${u(22)}`,
    gap: u(14),
    fontSize: u(11.5),
    fontWeight: 500,
    background: CINZA,
    color: GRAFITE,
  }
  const conteudo = (
    <>
      <span style={{ color: LARANJA, fontWeight: 700, fontSize: u(16) }}>+</span>
      {children}
    </>
  )
  return aoClicar ? (
    <button type="button" title={titulo} onClick={aoClicar} className="flex items-center rounded-full" style={estilo}>
      {conteudo}
    </button>
  ) : (
    <span title={titulo} className="flex items-center rounded-full" style={estilo}>
      {conteudo}
    </span>
  )
}

/** Quatro pontos do topo do cartão; no sorteio, piscam em sequência. */
function Pontos({ animados }: { animados: boolean }) {
  return (
    <div className="flex justify-center" style={{ gap: u(10) }}>
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className="block rounded-full"
          style={{
            width: u(22),
            height: u(22),
            background: i === 3 ? CINZA_SUAVE : CINZA,
            animation: animados ? `pontos-claro 1.2s ${i * 0.15}s ease-in-out infinite` : undefined,
          }}
        />
      ))}
    </div>
  )
}

/** Cartão central com borda (espera, sorteio, nome revelado). */
function Cartao({
  children,
  largura,
  larguraMaxima,
  laranja = true,
}: {
  children: ReactNode
  largura: number
  /** Com máxima, o cartão cresce do mínimo (`largura`) até ela, conforme o texto. */
  larguraMaxima?: number
  laranja?: boolean
}) {
  return (
    <div
      className="relative flex flex-col items-center justify-center text-center"
      style={{
        ...(larguraMaxima ? { minWidth: u(largura), maxWidth: u(larguraMaxima) } : { width: u(largura) }),
        minHeight: u(282),
        borderRadius: u(24),
        border: `${u(2.5)} solid ${laranja ? LARANJA : CINZA_BORDA}`,
        padding: `${u(36)} ${u(50)}`,
      }}
    >
      {children}
    </div>
  )
}

function LinhaPremio({ estado }: { estado: TelaoEstado }) {
  const premio = estado.premio
  if (!premio) return null
  return (
    <p style={{ marginTop: u(32), fontSize: u(26) }}>
      Prêmio: <span style={{ fontWeight: 600 }}>{premio.nome}</span>
      {premio.unidade_total > 1 && (
        <span style={{ opacity: 0.75 }}>
          {' '}
          · unidade {premio.unidade_numero} de {premio.unidade_total}
        </span>
      )}
    </p>
  )
}

// ------------------------------------------------------------------ estados
function Aguardando({ estado, reduzir }: { estado: TelaoEstado; reduzir: boolean }) {
  // "Bem-vindos!" fica como no modelo; mensagens longas reduzem a fonte e alargam o cartão.
  const tamanho = estado.evento.mensagem_boas_vindas.length
  const fonte = tamanho <= 14 ? 78 : tamanho <= 30 ? 66 : tamanho <= 60 ? 54 : 44
  return (
    <div className={reduzir ? '' : 'animate-sobe-suave'}>
      <Cartao largura={570} larguraMaxima={1300} laranja={false}>
        <Pontos animados={false} />
        <p style={{ marginTop: u(26), color: LARANJA, fontWeight: 700, fontSize: u(fonte), lineHeight: 1.1 }}>
          {estado.evento.mensagem_boas_vindas}
        </p>
        <p style={{ marginTop: u(10), fontSize: u(23) }}>O sorteio começa em instantes</p>
        <span className="block" style={{ marginTop: u(12), width: u(350), height: u(2.5), background: LARANJA }} />
      </Cartao>
    </div>
  )
}

function ProximoPremio({ estado, reduzir }: { estado: TelaoEstado; reduzir: boolean }) {
  const premio = estado.premio
  if (!premio) return null
  return (
    <div className={reduzir ? '' : 'animate-sobe-suave'}>
      <CartaoDividido
        imagemUrl={premio.imagem_url}
        premioNome={premio.nome}
        direita={
          <>
            <p style={{ fontSize: u(23) }}>Próximo prêmio</p>
            <p style={{ fontSize: u(64), fontWeight: 800, lineHeight: 1.08, marginTop: u(8) }}>{premio.nome}</p>
            {premio.descricao && <p style={{ fontSize: u(22), marginTop: u(14), opacity: 0.85 }}>{premio.descricao}</p>}
            {premio.unidade_total > 1 && (
              <span
                className="self-start rounded-full"
                style={{ marginTop: u(28), padding: `${u(10)} ${u(26)}`, background: LARANJA, color: '#fff', fontSize: u(22), fontWeight: 600 }}
              >
                Unidade {premio.unidade_numero} de {premio.unidade_total}
              </span>
            )}
          </>
        }
      />
    </div>
  )
}

/** Rolos girando enquanto o servidor revela (o número ainda não chegou ao telão). */
function Sorteando({ estado, reduzir, somAtivo }: { estado: TelaoEstado; reduzir: boolean; somAtivo: boolean }) {
  const digitos = Math.min(9, Math.max(1, estado.digitos_animacao ?? 4))
  const restante = estado.revelar_em
    ? Math.max(0, new Date(estado.revelar_em).getTime() - new Date(estado.servidor_agora).getTime())
    : 0
  const restanteRef = useRef(restante)
  restanteRef.current = restante
  // O rufar acompanha o horário de revelação (novas mensagens não o reiniciam).
  useEffect(() => {
    if (!somAtivo) return
    return somRufar(restanteRef.current)
  }, [somAtivo, estado.revelar_em])

  return (
    <div className="flex flex-col items-center">
      <Cartao largura={1090}>
        <Pontos animados={!reduzir} />
        <p style={{ marginTop: u(18), fontSize: u(15), letterSpacing: u(4), fontWeight: 500 }}>SORTEANDO O NÚMERO</p>
        {reduzir ? (
          <p style={{ marginTop: u(18), fontSize: u(70), fontWeight: 800, color: LARANJA }}>Sorteando...</p>
        ) : (
          <Rolos valor={null} digitos={digitos} />
        )}
      </Cartao>
      <LinhaPremio estado={estado} />
    </div>
  )
}

/**
 * Rolos de número. `valor` nulo: todos giram. Com valor: cada rolo para no seu
 * dígito, um de cada vez, da esquerda para a direita.
 */
export function Rolos({
  valor,
  digitos,
  atrasoMs = 0,
  cores = { fundo: '#ffffff', borda: CINZA, digito: LARANJA },
}: {
  valor: string | null
  digitos: number
  atrasoMs?: number
  /** Cores do rolo (o clássico usa as cores do evento). Tamanhos em `--u`. */
  cores?: { fundo: string; borda: string; digito: string }
}) {
  const caracteres = valor ? valor.split('') : Array.from({ length: digitos }, () => '')
  const [parados, setParados] = useState(0)
  useEffect(() => {
    if (!valor) {
      setParados(0)
      return
    }
    const ids = caracteres.map((_, i) =>
      window.setTimeout(() => setParados(i + 1), Math.max(0, (i + 1) * PARADA_POR_ROLO_MS - atrasoMs)),
    )
    return () => ids.forEach((id) => window.clearTimeout(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valor, atrasoMs])

  const fita = '01234567890123456789'.split('')
  const largura = caracteres.length > 6 ? 96 : 124
  return (
    <div className="flex justify-center" style={{ marginTop: u(22), gap: u(14) }} aria-live="polite">
      {caracteres.map((c, i) => {
        const parado = valor !== null && i < parados
        return (
          <div
            key={i}
            className="relative overflow-hidden"
            style={{
              width: u(largura),
              height: u(156),
              borderRadius: u(18),
              background: cores.fundo,
              border: `${u(2)} solid ${cores.borda}`,
            }}
          >
            {parado ? (
              <div
                className="rolo-pousa flex h-full items-center justify-center"
                style={{ fontSize: u(116), fontWeight: 800, color: cores.digito, lineHeight: 1 }}
              >
                {c}
              </div>
            ) : (
              <div className="rolo-girando" style={{ animationDuration: `${0.26 + (i % 3) * 0.05}s` }}>
                {fita.map((d, j) => (
                  <div
                    key={j}
                    className="flex items-center justify-center"
                    style={{ height: u(156), fontSize: u(116), fontWeight: 800, color: cores.digito, lineHeight: 1 }}
                  >
                    {d}
                  </div>
                ))}
              </div>
            )}
            {/* Sombra de cima e de baixo, como numa janela de caça-níquel. */}
            <div
              className="pointer-events-none absolute inset-0"
              style={{ background: `linear-gradient(${cores.fundo} 0%, transparent 26%, transparent 74%, ${cores.fundo} 100%)` }}
            />
          </div>
        )
      })}
    </div>
  )
}

export type FaseRevelacao = 'parando' | 'nome' | 'completo'

/**
 * Revelação em três tempos, usada pelos dois temas: os rolos param no número
 * (um a um), o nome aparece sozinho e então o anúncio completo. A fase vem do
 * tempo desde a revelação (relógio do servidor): reconectar no meio não repete
 * tudo. Toca a fanfarra quando o último rolo para.
 */
export function useFaseRevelacao(estado: TelaoEstado, reduzir: boolean, somAtivo: boolean) {
  const ganhador = estado.ganhador
  const numero = ganhador ? numeroExibido(ganhador.numero_sorteio, ganhador.matricula_da_sorte) : null
  const digitos = numero?.length ?? 4
  const decorrido = msDesdeRevelacao(estado)
  const fimParada = digitos * PARADA_POR_ROLO_MS + POUSO_MS
  const fimNome = fimParada + NOME_MS

  const faseInicial: FaseRevelacao =
    reduzir || !numero ? 'completo' : decorrido < fimParada ? 'parando' : decorrido < fimNome ? 'nome' : 'completo'
  const [fase, setFase] = useState<FaseRevelacao>(faseInicial)
  const inicioRef = useRef({ decorrido: Math.max(0, Math.min(decorrido, fimNome)), em: performance.now() })

  useEffect(() => {
    if (fase === 'completo') return
    const passado = inicioRef.current.decorrido + (performance.now() - inicioRef.current.em)
    const proxima = fase === 'parando' ? fimParada : fimNome
    const id = window.setTimeout(() => setFase(fase === 'parando' ? 'nome' : 'completo'), Math.max(0, proxima - passado))
    return () => window.clearTimeout(id)
  }, [fase, fimParada, fimNome])

  const tocado = useRef(false)
  useEffect(() => {
    if (somAtivo && !tocado.current && fase !== 'parando') {
      tocado.current = true
      somVitoria()
    }
  }, [somAtivo, fase])

  return { fase, numero, digitos, atrasoMs: Math.max(0, inicioRef.current.decorrido) }
}

function Resultado({ estado, reduzir, somAtivo }: { estado: TelaoEstado; reduzir: boolean; somAtivo: boolean }) {
  const ganhador = estado.ganhador
  const { fase, numero, digitos, atrasoMs } = useFaseRevelacao(estado, reduzir, somAtivo)

  if (!ganhador) return null

  if (fase === 'parando' && numero) {
    return (
      <div className="flex flex-col items-center">
        <Cartao largura={1090}>
          <Pontos animados />
          <p style={{ marginTop: u(18), fontSize: u(15), letterSpacing: u(4), fontWeight: 500 }}>SORTEANDO O NÚMERO</p>
          <Rolos valor={numero} digitos={digitos} atrasoMs={atrasoMs} />
        </Cartao>
        <LinhaPremio estado={estado} />
      </div>
    )
  }

  if (fase === 'nome') {
    return (
      <div className="flex flex-col items-center animate-sobe-suave">
        <Cartao largura={1090}>
          <Medalha tamanho={144} className="absolute left-1/2 -translate-x-1/2" estilo={{ top: u(-72) }} />
          <p style={{ marginTop: u(70), fontSize: u(72), fontWeight: 800, lineHeight: 1.08 }}>{ganhador.nome}</p>
          {numero && (
            <span className="rounded-full" style={{ marginTop: u(22), padding: `${u(8)} ${u(34)}`, background: LARANJA, color: '#fff', fontSize: u(40), fontWeight: 800 }}>
              {numero}
            </span>
          )}
        </Cartao>
        <LinhaPremio estado={estado} />
      </div>
    )
  }

  const premio = estado.premio
  return (
    <>
      <Confete ativo={!reduzir} reduzido={reduzir} cores={[coresClaro(estado).destaque, coresClaro(estado).texto, coresClaro(estado).painel, '#ffffff']} duracaoMs={2800} quantidade={45} />
      <div className={reduzir ? '' : 'animate-entra-vencedor'}>
        <CartaoVencedor
          nome={ganhador.nome}
          setor={ganhador.setor}
          fotoUrl={ganhador.foto_url}
          numero={numero}
          ehMatricula={!!ganhador.matricula_da_sorte}
          premioNome={premio?.nome ?? ''}
          premioImagemUrl={premio?.imagem_url ?? null}
          detalhe={premio && premio.unidade_total > 1 ? `Unidade ${premio.unidade_numero} de ${premio.unidade_total}` : null}
        />
      </div>
    </>
  )
}

function Medalha({ tamanho, className = '', estilo }: { tamanho: number; className?: string; estilo?: CSSProperties }) {
  return (
    <span
      aria-hidden="true"
      className={`flex items-center justify-center rounded-full ${className}`}
      style={{ width: u(tamanho), height: u(tamanho), background: LARANJA, ...estilo }}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" style={{ width: '58%', height: '58%' }}>
        <path d="M12 3.2l1.6 1.2 2-.2.8 1.8 1.8.8-.2 2 1.2 1.6-1.2 1.6.2 2-1.8.8-.8 1.8-2-.2L12 18l-1.6-1.2-2 .2-.8-1.8-1.8-.8.2-2L4.8 10.8 6 9.2l-.2-2 1.8-.8.8-1.8 2 .2z" />
        <path d="M12 8.2l1.1 2.3 2.5.3-1.8 1.7.5 2.5L12 13.8l-2.3 1.2.5-2.5-1.8-1.7 2.5-.3z" />
        <path d="M8.6 17.4L7 21.6l2.6-.8 1.4 2.1 1-3.9M15.4 17.4L17 21.6l-2.6-.8-1.4 2.1-1-3.9" />
      </svg>
    </span>
  )
}

/** Cartão em duas metades: imagem do prêmio (branco) e informações (cinza). */
function CartaoDividido({
  imagemUrl,
  premioNome,
  direita,
  canto,
}: {
  imagemUrl: string | null
  premioNome: string
  direita: ReactNode
  canto?: ReactNode
}) {
  const [quebrada, setQuebrada] = useState<string | null>(null)
  const comImagem = !!imagemUrl && quebrada !== imagemUrl
  return (
    <div className="relative flex" style={{ width: u(1132), height: u(525) }}>
      <div className="flex flex-1 flex-col overflow-hidden" style={{ background: '#ffffff', borderRadius: `${u(36)} 0 0 ${u(36)}` }}>
        <div className="relative flex-1">
          <ImagemPremio
            url={imagemUrl}
            nome={premioNome}
            grande
            aoFalhar={setQuebrada}
            className="absolute inset-0 h-full w-full text-slate-300"
          />
        </div>
        <div className="text-center" style={{ borderTop: `1px solid ${CINZA_SUAVE}`, padding: `${u(18)} ${u(20)} ${u(comImagem ? 8 : 26)}` }}>
          <p className="truncate" style={{ fontSize: u(26) }}>{premioNome}</p>
          {comImagem && <p style={{ fontSize: u(13), fontStyle: 'italic', opacity: 0.6, marginTop: u(4) }}>{AVISO_IMAGEM_ILUSTRATIVA}</p>}
        </div>
      </div>
      <div className="flex flex-1 flex-col justify-center" style={{ background: CINZA, borderRadius: `0 ${u(36)} ${u(36)} 0`, padding: `${u(40)} ${u(70)} ${u(40)} ${u(88)}` }}>
        {direita}
      </div>
      {canto}
    </div>
  )
}

function CartaoVencedor({
  nome,
  setor,
  fotoUrl,
  numero,
  ehMatricula,
  premioNome,
  premioImagemUrl,
  detalhe,
  rodape,
}: {
  nome: string
  setor: string
  fotoUrl: string | null
  numero: string | null
  ehMatricula: boolean
  premioNome: string
  premioImagemUrl: string | null
  detalhe: string | null
  rodape?: ReactNode
}) {
  const [fotoFalhou, setFotoFalhou] = useState(false)
  const nomeLongo = nome.length > 26
  return (
    <div className="flex flex-col items-center">
      <CartaoDividido
        imagemUrl={premioImagemUrl}
        premioNome={premioNome}
        canto={
          // Com foto, o círculo laranja do canto mostra o ganhador; sem foto, a medalha.
          fotoUrl && !fotoFalhou ? (
            <img
              src={fotoUrl}
              alt=""
              onError={() => setFotoFalhou(true)}
              className="absolute rounded-full object-cover"
              style={{ right: u(-58), top: u(-56), width: u(180), height: u(180), border: `${u(7)} solid ${LARANJA}` }}
            />
          ) : (
            <Medalha tamanho={180} className="absolute" estilo={{ right: u(-58), top: u(-56) }} />
          )
        }
        direita={
          <>
            <p style={{ fontSize: u(23) }}>Vencedor</p>
            <p style={{ fontSize: u(nomeLongo ? 50 : 62), fontWeight: 800, lineHeight: 1.08, marginTop: u(6) }}>{nome}</p>
            {setor && (
              <p style={{ fontSize: u(23), marginTop: u(10) }}>
                Setor: <span style={{ fontWeight: 600 }}>{setor}</span>
              </p>
            )}
            {numero && (
              <div
                className="self-start text-center"
                style={{ marginTop: u(22), padding: `${u(10)} ${u(44)} ${u(14)}`, borderRadius: u(40), background: LARANJA, color: '#fff' }}
              >
                <p style={{ fontSize: u(16), fontWeight: 500, opacity: 0.9 }}>{ehMatricula ? 'Matrícula' : 'Nº da sorte'}</p>
                <p style={{ fontSize: u(112), fontWeight: 800, lineHeight: 1, letterSpacing: u(2) }}>{numero}</p>
              </div>
            )}
            {detalhe && <p style={{ fontSize: u(18), marginTop: u(14), opacity: 0.75 }}>{detalhe}</p>}
          </>
        }
      />
      {rodape}
    </div>
  )
}

// ------------------------------------------------------------------ carrossel
function Carrossel({ estado, reduzir }: { estado: TelaoEstado; reduzir: boolean }) {
  const dados = estado.carrossel
  const { posicao, progresso } = usePosicaoCarrossel(dados, estado.servidor_agora)
  if (!dados || dados.total === 0) return null
  if (posicao >= dados.total) return <ResumoCarrossel slides={dados.slides} reduzir={reduzir} />

  const slide = dados.slides[posicao]
  // Abaixo de 1 s por ganhador, a troca é direta (sem animação de entrada).
  const animar = !reduzir && dados.duracao_s >= 1
  return (
    <div key={posicao} className={animar ? 'animate-entra-vencedor' : ''}>
      <CartaoVencedor
        nome={slide.ganhador_nome}
        setor={slide.ganhador_setor}
        fotoUrl={slide.ganhador_foto_url}
        numero={numeroExibido(slide.ganhador_numero, slide.ganhador_matricula_da_sorte)}
        ehMatricula={!!slide.ganhador_matricula_da_sorte}
        premioNome={slide.premio_nome}
        premioImagemUrl={slide.premio_imagem_url}
        detalhe={null}
        rodape={
          <div className="flex items-center" style={{ marginTop: u(40), width: u(800), gap: u(22) }}>
            <span style={{ fontSize: u(24), fontWeight: 600 }} className="tabular-nums">
              {posicao + 1} de {dados.total}
            </span>
            <div className="flex-1 overflow-hidden rounded-full" style={{ height: u(10), background: CINZA }}>
              <div
                className="h-full rounded-full"
                style={{ width: `${Math.round(progresso * 100)}%`, background: LARANJA, transition: progresso === 0 ? 'none' : 'width 0.2s linear' }}
              />
            </div>
            {dados.pausado && (
              <span className="rounded-full" style={{ fontSize: u(18), padding: `${u(6)} ${u(18)}`, border: `${u(2)} solid ${LARANJA}`, color: LARANJA }}>
                PAUSADO
              </span>
            )}
          </div>
        }
      />
    </div>
  )
}

/**
 * Grade do resumo do carrossel (os dois temas): quanto mais ganhadores, mais
 * colunas e pílulas menores, para caber inteiro no telão (blocos de até ~90).
 * `largura` em unidades do modelo (2000 = tela toda).
 */
export function gradeResumo(n: number): { colunas: number; escala: number; largura: number } {
  if (n <= 8) return { colunas: 2, escala: 1, largura: 1100 }
  if (n <= 15) return { colunas: 3, escala: 0.86, largura: 1500 }
  if (n <= 28) return { colunas: 4, escala: 0.74, largura: 1760 }
  if (n <= 45) return { colunas: 5, escala: 0.64, largura: 1840 }
  if (n <= 66) return { colunas: 6, escala: 0.56, largura: 1860 }
  return { colunas: 7, escala: 0.5, largura: 1880 }
}

function ResumoCarrossel({ slides, reduzir }: { slides: SlideCarrossel[]; reduzir: boolean }) {
  // Quanto mais ganhadores, mais colunas e menor a pílula, para caber na tela.
  const { colunas, escala, largura } = gradeResumo(slides.length)
  return (
    <div className={`flex flex-col items-center ${reduzir ? '' : 'animate-sobe-suave'}`} style={{ marginTop: u(60) }}>
      <h2 style={{ fontSize: u(72), fontWeight: 800, color: GRAFITE }}>Parabéns aos vencedores!</h2>
      <ul
        className="grid"
        style={{ width: u(largura), marginTop: u(46 * escala), gap: `${u(20 * escala)} ${u(20)}`, gridTemplateColumns: `repeat(${colunas}, minmax(0, 1fr))` }}
      >
        {slides.map((s, i) => (
          <li
            key={`${s.premio_nome}-${s.unidade_numero}-${i}`}
            className="flex items-center rounded-full"
            style={{
              border: `${u(2.5)} solid ${LARANJA}`,
              padding: `${u(12 * escala)} ${u(24 * escala)} ${u(12 * escala)} ${u(14 * escala)}`,
              gap: u(16 * escala),
            }}
          >
            <FotoPilula url={s.ganhador_foto_url} nome={s.ganhador_nome} tamanho={70 * escala} />
            <div className="min-w-0">
              <p className="line-clamp-2 break-words" style={{ color: LARANJA, fontWeight: 800, fontSize: u(26 * escala), lineHeight: 1.15 }}>
                {s.ganhador_nome}
              </p>
              <p className="line-clamp-2 break-words" style={{ fontSize: u(22 * escala) }}>
                {s.ganhador_matricula_da_sorte ? 'Matrícula ' : 'Nº '}
                <span style={{ fontWeight: 700 }}>{numeroExibido(s.ganhador_numero, s.ganhador_matricula_da_sorte)}</span>
                {' · '}
                {s.premio_nome}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function FotoPilula({ url, nome, tamanho }: { url: string | null; nome: string; tamanho: number }) {
  const [falhou, setFalhou] = useState(false)
  if (url && !falhou) {
    return (
      <img
        src={url}
        alt=""
        onError={() => setFalhou(true)}
        className="shrink-0 rounded-full object-cover"
        style={{ width: u(tamanho), height: u(tamanho) }}
      />
    )
  }
  const partes = nome.trim().split(/\s+/)
  const iniciais = ((partes[0]?.[0] ?? '') + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase()
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-full"
      style={{ width: u(tamanho), height: u(tamanho), background: CINZA, fontSize: u(tamanho * 0.36), fontWeight: 700 }}
    >
      {iniciais}
    </span>
  )
}

// ------------------------------------------------------------------ encerramento
function Encerramento({ estado }: { estado: TelaoEstado }) {
  const galeria = estado.galeria
  const rolagemRef = useRef<HTMLDivElement | null>(null)
  const rolar = useCallback((direcao: number) => {
    rolagemRef.current?.scrollBy({ left: direcao * 420, behavior: 'smooth' })
  }, [])
  return (
    <div className="flex w-full flex-col items-center animate-sobe-suave" style={{ padding: `0 ${u(120)}` }}>
      <h2 className="text-center" style={{ fontSize: u(72), fontWeight: 800, color: GRAFITE, lineHeight: 1.1 }}>
        {estado.evento.mensagem_encerramento}
      </h2>
      {galeria.length === 0 ? (
        <p style={{ marginTop: u(40), fontSize: u(26) }}>Nenhum prêmio foi sorteado.</p>
      ) : (
        <>
          <p style={{ marginTop: u(16), fontSize: u(22), letterSpacing: u(4), fontWeight: 500 }}>{galeria.length} GANHADOR(ES)</p>
          <div ref={rolagemRef} className="flex w-full overflow-x-auto" style={{ marginTop: u(36), gap: u(24), paddingBottom: u(16), scrollbarWidth: 'thin' }}>
            {galeria.map((item, i) => (
              <div
                key={`${item.premio_nome}-${item.unidade_numero}-${i}`}
                className="shrink-0 text-center"
                style={{ width: u(300), borderRadius: u(24), background: '#ffffff', padding: u(18) }}
              >
                <ImagemPremio
                  url={item.premio_imagem_url}
                  nome={item.premio_nome}
                  className="aspect-[4/3] w-full rounded-xl text-slate-300"
                />
                <p className="truncate" style={{ marginTop: u(12), fontSize: u(18) }}>{item.premio_nome}</p>
                <p style={{ marginTop: u(6), fontSize: u(22), fontWeight: 800, color: LARANJA, lineHeight: 1.15 }}>{item.ganhador_nome}</p>
                <p style={{ fontSize: u(18), fontWeight: 600 }} className="tabular-nums">
                  {item.ganhador_matricula_da_sorte ? 'Matrícula ' : 'Nº '}
                  {numeroExibido(item.ganhador_numero, item.ganhador_matricula_da_sorte)}
                </p>
                <p className="truncate" style={{ fontSize: u(16), opacity: 0.75 }}>{item.ganhador_setor}</p>
              </div>
            ))}
          </div>
          {galeria.some((g) => g.premio_imagem_url) && (
            <p style={{ fontSize: u(15), fontStyle: 'italic', opacity: 0.6 }}>Imagens meramente ilustrativas</p>
          )}
          {galeria.length > 4 && (
            <div className="flex" style={{ gap: u(16), marginTop: u(16) }}>
              {[-1, 1].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => rolar(d)}
                  className="rounded-full"
                  style={{ padding: `${u(8)} ${u(28)}`, border: `${u(2)} solid ${LARANJA}`, color: LARANJA, fontSize: u(24) }}
                >
                  {d < 0 ? '←' : '→'}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
