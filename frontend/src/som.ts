/**
 * Sons gerados pela Web Audio API - nenhum arquivo de audio externo, para que
 * o evento funcione sem internet e sem assets extras.
 *
 * Navegadores so permitem audio apos uma interacao do usuario. O telao exibe um
 * botao "Ativar som" que chama `liberarAudio()`.
 *
 * As funcoes `agendar*` recebem o contexto e o destino, e nao dependem do
 * contexto global: assim o mesmo som pode ser renderizado offline
 * (OfflineAudioContext) para conferencia.
 */

let contexto: AudioContext | null = null
let liberado = false

type ConstrutorAudio = typeof AudioContext

function obterContexto(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (contexto) return contexto
  const Construtor: ConstrutorAudio | undefined =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: ConstrutorAudio }).webkitAudioContext
  if (!Construtor) return null
  try {
    contexto = new Construtor()
  } catch {
    return null
  }
  return contexto
}

export async function liberarAudio(): Promise<boolean> {
  const ctx = obterContexto()
  if (!ctx) return false
  try {
    if (ctx.state === 'suspended') await ctx.resume()
    liberado = ctx.state === 'running'
  } catch {
    liberado = false
  }
  return liberado
}

export function audioLiberado(): boolean {
  return liberado
}

const SILENCIO = 0.0001

/** Ruido branco de 1 s, criado uma vez por contexto (base da caixa e do prato). */
const ruidos = new WeakMap<BaseAudioContext, AudioBuffer>()
function ruido(ctx: BaseAudioContext): AudioBuffer {
  let buffer = ruidos.get(ctx)
  if (!buffer) {
    buffer = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate)
    const dados = buffer.getChannelData(0)
    for (let i = 0; i < dados.length; i++) dados[i] = Math.random() * 2 - 1
    ruidos.set(ctx, buffer)
  }
  return buffer
}

/** Envelope percussivo: ataque quase instantaneo e decaimento exponencial. */
function envelope(ctx: BaseAudioContext, quando: number, volume: number, decaimento: number): GainNode {
  const ganho = ctx.createGain()
  ganho.gain.setValueAtTime(SILENCIO, quando)
  ganho.gain.exponentialRampToValueAtTime(Math.max(SILENCIO, volume), quando + 0.002)
  ganho.gain.exponentialRampToValueAtTime(SILENCIO, quando + decaimento)
  return ganho
}

function nota(
  ctx: BaseAudioContext,
  destino: AudioNode,
  frequencia: number,
  inicio: number,
  duracao: number,
  volume: number,
  tipo: OscillatorType = 'triangle',
) {
  const osc = ctx.createOscillator()
  const ganho = ctx.createGain()
  osc.type = tipo
  osc.frequency.setValueAtTime(frequencia, inicio)
  ganho.gain.setValueAtTime(SILENCIO, inicio)
  ganho.gain.exponentialRampToValueAtTime(volume, inicio + 0.02)
  ganho.gain.exponentialRampToValueAtTime(SILENCIO, inicio + duracao)
  osc.connect(ganho).connect(destino)
  osc.start(inicio)
  osc.stop(inicio + duracao + 0.05)
}

/** Uma batida de caixa: esteira (ruido filtrado) + corpo do tambor (tom curto). */
function golpeCaixa(
  ctx: BaseAudioContext,
  destino: AudioNode,
  quando: number,
  volume: number,
): AudioScheduledSourceNode[] {
  const esteira = ctx.createBufferSource()
  esteira.buffer = ruido(ctx)
  const filtro = ctx.createBiquadFilter()
  filtro.type = 'bandpass'
  filtro.frequency.value = 2400 + Math.random() * 700
  filtro.Q.value = 0.7
  esteira.connect(filtro).connect(envelope(ctx, quando, volume, 0.11)).connect(destino)
  esteira.start(quando, Math.random() * 0.8, 0.13)

  const corpo = ctx.createOscillator()
  corpo.type = 'triangle'
  corpo.frequency.setValueAtTime(230, quando)
  corpo.frequency.exponentialRampToValueAtTime(170, quando + 0.05)
  corpo.connect(envelope(ctx, quando, volume * 0.45, 0.06)).connect(destino)
  corpo.start(quando)
  corpo.stop(quando + 0.08)
  return [esteira, corpo]
}

/**
 * Uma batida do rulo: corpo do tambor (ruido em ~260 Hz + tom curto) com um
 * pouco de esteira. Mais grave e "cheia" que a batida isolada de caixa.
 */
function golpeRulo(
  ctx: BaseAudioContext,
  destino: AudioNode,
  quando: number,
  volume: number,
): AudioScheduledSourceNode[] {
  const fonte = ctx.createBufferSource()
  fonte.buffer = ruido(ctx)
  const corpo = ctx.createBiquadFilter()
  corpo.type = 'bandpass'
  corpo.frequency.value = AJUSTE.corpoHz * (0.92 + Math.random() * 0.16)
  corpo.Q.value = AJUSTE.corpoQ
  fonte.connect(corpo).connect(envelope(ctx, quando, volume * AJUSTE.corpoGanho, AJUSTE.corpoDecai)).connect(destino)
  const esteira = ctx.createBiquadFilter()
  esteira.type = 'bandpass'
  esteira.frequency.value = AJUSTE.esteiraHz
  esteira.Q.value = 0.9
  fonte.connect(esteira).connect(envelope(ctx, quando, volume * AJUSTE.esteiraGanho, 0.05)).connect(destino)
  fonte.start(quando, Math.random() * 0.8, 0.12)

  const tom = ctx.createOscillator()
  tom.type = 'triangle'
  tom.frequency.setValueAtTime(AJUSTE.tomHz, quando)
  tom.frequency.exponentialRampToValueAtTime(AJUSTE.tomHz * 0.8, quando + 0.04)
  tom.connect(envelope(ctx, quando, volume * AJUSTE.tomGanho, 0.05)).connect(destino)
  tom.start(quando)
  tom.stop(quando + 0.07)
  return [fonte, tom]
}

/** Parametros do rufar, calibrados contra uma gravacao de referencia. */
const AJUSTE = {
  batidasPorSegundo: 36,
  repique: 0.6,
  repiqueAtraso: 0.012,
  corpoHz: 300,
  corpoQ: 1.7,
  corpoGanho: 2.8,
  corpoDecai: 0.065,
  esteiraHz: 2000,
  esteiraGanho: 0.45,
  tomHz: 190,
  tomGanho: 0.3,
  preenchimento: 0.35,
  volume: 0.66,
  inicioRelativo: 0.75,
}

/**
 * Rufar de tambores: rulo denso e continuo (cada batida com repique), com o
 * corpo do tambor em evidencia e uma leve subida ate o fim. Devolve as fontes
 * agendadas para que o rufar possa ser interrompido.
 */
export function agendarRufar(
  ctx: BaseAudioContext,
  destino: AudioNode,
  inicio: number,
  segundos: number,
): AudioScheduledSourceNode[] {
  const fim = inicio + segundos
  // Barramento do rulo: subida leve de volume e so a faixa do tambor (120 Hz-7 kHz).
  const barramento = ctx.createGain()
  barramento.gain.setValueAtTime(SILENCIO, inicio)
  barramento.gain.exponentialRampToValueAtTime(AJUSTE.inicioRelativo, inicio + 0.25)
  barramento.gain.linearRampToValueAtTime(1, fim - 0.05)
  barramento.gain.linearRampToValueAtTime(0, fim)
  const semSubGrave = ctx.createBiquadFilter()
  semSubGrave.type = 'highpass'
  semSubGrave.frequency.value = 140
  semSubGrave.Q.value = 1
  const semAgudo = ctx.createBiquadFilter()
  semAgudo.type = 'lowpass'
  semAgudo.frequency.value = 7000
  barramento.connect(semSubGrave).connect(semAgudo).connect(destino)

  const fontes: AudioScheduledSourceNode[] = []
  let t = 0
  let batida = 0
  while (t < segundos - 0.03) {
    const mao = batida % 2 === 0 ? 1 : 0.85
    const volume = AJUSTE.volume * mao * (0.85 + Math.random() * 0.3)
    fontes.push(...golpeRulo(ctx, barramento, inicio + t, volume))
    fontes.push(...golpeRulo(ctx, barramento, inicio + t + AJUSTE.repiqueAtraso, volume * AJUSTE.repique))
    t += (1 / AJUSTE.batidasPorSegundo) * (0.9 + Math.random() * 0.2)
    batida++
  }

  // Preenchimento continuo na regiao do corpo: deixa o rulo "liso", sem buracos.
  const fundo = ctx.createBufferSource()
  fundo.buffer = ruido(ctx)
  fundo.loop = true
  const faixa = ctx.createBiquadFilter()
  faixa.type = 'bandpass'
  faixa.frequency.value = 300
  faixa.Q.value = 1.4
  const ganhoFundo = ctx.createGain()
  ganhoFundo.gain.value = AJUSTE.preenchimento
  fundo.connect(faixa).connect(ganhoFundo).connect(barramento)
  fundo.start(inicio)
  fundo.stop(fim + 0.05)
  fontes.push(fundo)
  return fontes
}

/** Revelacao: bumbo + caixa forte + prato, seguidos da fanfarra. */
export function agendarRevelacao(ctx: BaseAudioContext, destino: AudioNode, inicio: number) {
  const bumbo = ctx.createOscillator()
  bumbo.type = 'sine'
  bumbo.frequency.setValueAtTime(130, inicio)
  bumbo.frequency.exponentialRampToValueAtTime(42, inicio + 0.35)
  bumbo.connect(envelope(ctx, inicio, 0.45, 0.6)).connect(destino)
  bumbo.start(inicio)
  bumbo.stop(inicio + 0.65)

  golpeCaixa(ctx, destino, inicio, 0.35)

  const prato = ctx.createBufferSource()
  prato.buffer = ruido(ctx)
  prato.loop = true
  const agudo = ctx.createBiquadFilter()
  agudo.type = 'highpass'
  agudo.frequency.value = 4500
  prato.connect(agudo).connect(envelope(ctx, inicio, 0.2, 2.2)).connect(destino)
  prato.start(inicio)
  prato.stop(inicio + 2.3)

  const fanfarra = inicio + 0.3
  ;[523.25, 659.25, 783.99, 1046.5].forEach((frequencia, indice) =>
    nota(ctx, destino, frequencia, fanfarra + indice * 0.13, 0.4, 0.12),
  )
  nota(ctx, destino, 1318.5, fanfarra + 0.55, 0.9, 0.1)
}

// ------------------------------------------------------------------ caca-niquel
/** Som do sorteio escolhido em Configuracao. */
export type SomSorteio = 'tambores' | 'caca_niquel'

export function somDoEvento(valor: string | null | undefined): SomSorteio {
  return valor === 'caca_niquel' ? 'caca_niquel' : 'tambores'
}

/** Um "tec" mecanico do rolo girando. */
function tique(ctx: BaseAudioContext, destino: AudioNode, quando: number, volume: number): AudioScheduledSourceNode[] {
  const fonte = ctx.createBufferSource()
  fonte.buffer = ruido(ctx)
  const faixa = ctx.createBiquadFilter()
  faixa.type = 'bandpass'
  faixa.frequency.value = 3200 + Math.random() * 600
  faixa.Q.value = 2.5
  fonte.connect(faixa).connect(envelope(ctx, quando, volume, 0.018)).connect(destino)
  fonte.start(quando, Math.random() * 0.8, 0.03)
  const estalo = ctx.createOscillator()
  estalo.type = 'square'
  estalo.frequency.setValueAtTime(1500 + Math.random() * 120, quando)
  estalo.connect(envelope(ctx, quando, volume * 0.12, 0.012)).connect(destino)
  estalo.start(quando)
  estalo.stop(quando + 0.02)
  return [fonte, estalo]
}

/** O "clac" de um rolo travando no digito: baque grave + estalo + brilho metalico. */
function clac(ctx: BaseAudioContext, destino: AudioNode, quando: number): AudioScheduledSourceNode[] {
  const baque = ctx.createOscillator()
  baque.type = 'sine'
  baque.frequency.setValueAtTime(150, quando)
  baque.frequency.exponentialRampToValueAtTime(55, quando + 0.09)
  baque.connect(envelope(ctx, quando, 0.55, 0.14)).connect(destino)
  baque.start(quando)
  baque.stop(quando + 0.16)
  const estalo = ctx.createBufferSource()
  estalo.buffer = ruido(ctx)
  const grave = ctx.createBiquadFilter()
  grave.type = 'lowpass'
  grave.frequency.value = 1800
  estalo.connect(grave).connect(envelope(ctx, quando, 0.5, 0.05)).connect(destino)
  estalo.start(quando, Math.random() * 0.8, 0.07)
  nota(ctx, destino, 2637, quando + 0.005, 0.09, 0.05)
  return [baque, estalo]
}

/** Zumbido baixo do motor da maquina enquanto os rolos giram. */
function zumbido(ctx: BaseAudioContext, destino: AudioNode, inicio: number, fim: number): AudioScheduledSourceNode {
  const fonte = ctx.createBufferSource()
  fonte.buffer = ruido(ctx)
  fonte.loop = true
  const faixa = ctx.createBiquadFilter()
  faixa.type = 'bandpass'
  faixa.frequency.value = 700
  faixa.Q.value = 3
  const ganho = ctx.createGain()
  ganho.gain.setValueAtTime(SILENCIO, inicio)
  ganho.gain.exponentialRampToValueAtTime(0.06, inicio + 0.2)
  ganho.gain.setValueAtTime(0.06, Math.max(inicio + 0.2, fim - 0.3))
  ganho.gain.exponentialRampToValueAtTime(SILENCIO, fim)
  fonte.connect(faixa).connect(ganho).connect(destino)
  fonte.start(inicio)
  fonte.stop(fim + 0.05)
  return fonte
}

const TIQUES_POR_SEGUNDO = 16

/** Giro dos rolos: tec-tec continuo com o zumbido do motor. */
export function agendarGiroCacaNiquel(
  ctx: BaseAudioContext,
  destino: AudioNode,
  inicio: number,
  segundos: number,
): AudioScheduledSourceNode[] {
  const fontes: AudioScheduledSourceNode[] = [zumbido(ctx, destino, inicio, inicio + segundos + 0.1)]
  let t = 0
  while (t < segundos - 0.02) {
    fontes.push(...tique(ctx, destino, inicio + t, 0.35 * (0.8 + Math.random() * 0.4)))
    t += (1 / TIQUES_POR_SEGUNDO) * (0.9 + Math.random() * 0.2)
  }
  return fontes
}

/**
 * Parada dos rolos: o tec-tec desacelera e cada rolo da um "clac" quando trava
 * (um a cada `intervaloS`, como na animacao). `jaPassouS`: reconexao no meio.
 */
export function agendarParadaCacaNiquel(
  ctx: BaseAudioContext,
  destino: AudioNode,
  inicio: number,
  rolos: number,
  intervaloS: number,
  jaPassouS = 0,
): AudioScheduledSourceNode[] {
  const total = rolos * intervaloS
  const fontes: AudioScheduledSourceNode[] = []
  if (jaPassouS < total) fontes.push(zumbido(ctx, destino, inicio, inicio + total - jaPassouS))
  let t = 0
  while (t < total) {
    if (t >= jaPassouS) {
      const progresso = t / total
      fontes.push(...tique(ctx, destino, inicio + t - jaPassouS, 0.3 * (1 - progresso * 0.5)))
    }
    t += 1 / TIQUES_POR_SEGUNDO / (1 - (t / total) * 0.6)
  }
  for (let i = 1; i <= rolos; i++) {
    const quando = i * intervaloS - jaPassouS
    if (quando >= 0) fontes.push(...clac(ctx, destino, inicio + quando))
  }
  return fontes
}

/** Vitoria no caca-niquel: arpejo de maquina, campainha e moedas. */
export function agendarVitoriaCacaNiquel(ctx: BaseAudioContext, destino: AudioNode, inicio: number) {
  ;[1046.5, 1318.5, 1568, 2093].forEach((frequencia, indice) =>
    nota(ctx, destino, frequencia, inicio + indice * 0.07, 0.22, 0.1, 'square'),
  )
  const sino = inicio + 0.32
  ;[1568, 3136, 4704].forEach((frequencia, indice) =>
    nota(ctx, destino, frequencia, sino, 1.3 - indice * 0.3, 0.12 / (indice + 1), 'sine'),
  )
  let t = sino + 0.15
  for (let i = 0; i < 16; i++) {
    nota(ctx, destino, 3000 + Math.random() * 2200, t, 0.09, 0.05)
    t += 0.05 + Math.random() * 0.04
  }
}

/** Toca e devolve a funcao que interrompe (ao sair da tela antes do fim). */
function tocarInterrompivel(agendar: (ctx: AudioContext, destino: AudioNode) => AudioScheduledSourceNode[]): () => void {
  const ctx = obterContexto()
  if (!ctx || !liberado) return () => {}
  const mestre = ctx.createGain()
  mestre.connect(ctx.destination)
  const fontes = agendar(ctx, mestre)
  return () => {
    const agora = ctx.currentTime
    mestre.gain.setTargetAtTime(0, agora, 0.03)
    for (const fonte of fontes) {
      try {
        fonte.stop(agora + 0.2)
      } catch {
        // fonte ja encerrada
      }
    }
    window.setTimeout(() => mestre.disconnect(), 400)
  }
}

/**
 * Som durante a animacao do sorteio (rufar ou giro do caca-niquel). Devolve uma
 * funcao que o encerra (ao sair da tela de sorteio antes do fim).
 */
export function somRufar(duracaoMs: number, som: SomSorteio = 'tambores'): () => void {
  const segundos = Math.max(1, duracaoMs / 1000)
  return tocarInterrompivel((ctx, destino) =>
    som === 'caca_niquel'
      ? agendarGiroCacaNiquel(ctx, destino, ctx.currentTime + 0.03, segundos)
      : agendarRufar(ctx, destino, ctx.currentTime + 0.03, segundos),
  )
}

/** Caca-niquel: o clac de cada rolo que para na revelacao (os tambores nao tem). */
export function somParadaRolos(rolos: number, intervaloMs: number, jaPassouMs: number, som: SomSorteio): () => void {
  if (som !== 'caca_niquel') return () => {}
  return tocarInterrompivel((ctx, destino) =>
    agendarParadaCacaNiquel(ctx, destino, ctx.currentTime + 0.02, rolos, intervaloMs / 1000, jaPassouMs / 1000),
  )
}

/** Revelacao do ganhador: fanfarra dos tambores ou campainha e moedas. */
export function somVitoria(som: SomSorteio = 'tambores') {
  const ctx = obterContexto()
  if (!ctx || !liberado) return
  if (som === 'caca_niquel') agendarVitoriaCacaNiquel(ctx, ctx.destination, ctx.currentTime)
  else agendarRevelacao(ctx, ctx.destination, ctx.currentTime)
}

/**
 * Previa na Configuracao: giro curto, rolos parando e a vitoria. Libera o audio
 * (precisa vir de um clique) e devolve a funcao que interrompe.
 */
export async function previaSom(som: SomSorteio, rolos = 4, intervaloMs = 350): Promise<() => void> {
  if (!(await liberarAudio())) return () => {}
  const giro = 2.5
  const parada = rolos * (intervaloMs / 1000)
  return tocarInterrompivel((ctx, destino) => {
    const inicio = ctx.currentTime + 0.05
    if (som === 'caca_niquel') {
      const fontes = [
        ...agendarGiroCacaNiquel(ctx, destino, inicio, giro),
        ...agendarParadaCacaNiquel(ctx, destino, inicio + giro, rolos, intervaloMs / 1000),
      ]
      agendarVitoriaCacaNiquel(ctx, destino, inicio + giro + parada + 0.25)
      return fontes
    }
    const fontes = agendarRufar(ctx, destino, inicio, giro)
    agendarRevelacao(ctx, destino, inicio + giro + parada + 0.25)
    return fontes
  })
}
