import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import Icone from './Icone'

/** Lado (px) da foto de perfil salva: quadrada, já enquadrada. */
const LADO_SAIDA = 800
const ZOOM_MAXIMO = 4

interface Estado {
  zoom: number
  dx: number
  dy: number
  rot: number
}

const INICIAL: Estado = { zoom: 1, dx: 0, dy: 0, rot: 0 }

/** Largura e altura da imagem depois de girar. */
function medidas(img: HTMLImageElement, rot: number) {
  const deitada = rot % 180 !== 0
  return deitada
    ? { w: img.naturalHeight, h: img.naturalWidth }
    : { w: img.naturalWidth, h: img.naturalHeight }
}

/** Mantém a moldura sempre coberta pela imagem (sem bordas vazias). */
function limitar(estado: Estado, img: HTMLImageElement, lado: number): Estado {
  const { w, h } = medidas(img, estado.rot)
  const escala = (lado / Math.min(w, h)) * estado.zoom
  const folgaX = Math.max(0, (w * escala - lado) / 2)
  const folgaY = Math.max(0, (h * escala - lado) / 2)
  return {
    ...estado,
    dx: Math.max(-folgaX, Math.min(folgaX, estado.dx)),
    dy: Math.max(-folgaY, Math.min(folgaY, estado.dy)),
  }
}

/**
 * Ajuste da foto de perfil antes de salvar: arrastar para enquadrar o rosto,
 * zoom (controle, roda do mouse ou pinça com dois dedos) e girar 90°.
 * Devolve só o recorte quadrado em JPEG; a original não é enviada.
 */
export default function AjusteFoto({
  fonte,
  aoConfirmar,
  aoCancelar,
  textoCancelar = 'Escolher outra',
  portal = false,
}: {
  /** Arquivo escolhido/capturado ou URL de uma foto já salva (mesma origem). */
  fonte: Blob | string
  aoConfirmar: (foto: Blob) => void | Promise<void>
  aoCancelar: () => void
  textoCancelar?: string
  /** Visual do portal do colaborador (botões grandes). */
  portal?: boolean
}) {
  const caixaRef = useRef<HTMLDivElement | null>(null)
  const [lado, setLado] = useState(280)
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [erro, setErro] = useState('')
  const [estado, setEstado] = useState<Estado>(INICIAL)
  const [salvando, setSalvando] = useState(false)
  const ponteiros = useRef(new Map<number, { x: number; y: number }>())
  const pinca = useRef<{ distancia: number; zoom: number } | null>(null)

  // Carrega a imagem (arquivo local ou foto já salva).
  useEffect(() => {
    // `vivo`: um carregamento antigo (fonte trocada ou efeito refeito) não mexe na tela.
    let vivo = true
    let urlLocal: string | null = null
    const imagem = new Image()
    imagem.crossOrigin = 'anonymous'
    imagem.onload = () => {
      if (!vivo) return
      setErro('')
      setImg(imagem)
      setEstado(INICIAL)
    }
    imagem.onerror = () => {
      if (vivo) setErro('Não foi possível abrir esta imagem. Use uma foto JPG ou PNG.')
    }
    if (typeof fonte === 'string') imagem.src = fonte
    else {
      urlLocal = URL.createObjectURL(fonte)
      imagem.src = urlLocal
    }
    return () => {
      vivo = false
      // Revoga depois: a imagem já carregada continua sendo desenhada pelo <img>.
      if (urlLocal) {
        const url = urlLocal
        window.setTimeout(() => URL.revokeObjectURL(url), 0)
      }
    }
  }, [fonte])

  // A moldura acompanha a largura disponível (até 300 px).
  useLayoutEffect(() => {
    const caixa = caixaRef.current
    if (!caixa) return
    const medir = () => setLado(Math.max(200, Math.min(300, Math.floor(caixa.clientWidth))))
    medir()
    const observador = new ResizeObserver(medir)
    observador.observe(caixa)
    return () => observador.disconnect()
  }, [])

  function mudar(proximo: Partial<Estado> | ((atual: Estado) => Partial<Estado>)) {
    if (!img) return
    setEstado((atual) =>
      limitar({ ...atual, ...(typeof proximo === 'function' ? proximo(atual) : proximo) }, img, lado),
    )
  }

  function zoomPara(valor: number) {
    mudar({ zoom: Math.max(1, Math.min(ZOOM_MAXIMO, valor)) })
  }

  function aoApertar(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId)
    ponteiros.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (ponteiros.current.size === 2) {
      const [a, b] = [...ponteiros.current.values()]
      pinca.current = { distancia: Math.hypot(a.x - b.x, a.y - b.y), zoom: estado.zoom }
    }
  }

  function aoMover(e: React.PointerEvent<HTMLDivElement>) {
    const anterior = ponteiros.current.get(e.pointerId)
    if (!anterior) return
    ponteiros.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (ponteiros.current.size >= 2 && pinca.current) {
      const [a, b] = [...ponteiros.current.values()]
      const distancia = Math.hypot(a.x - b.x, a.y - b.y)
      zoomPara(pinca.current.zoom * (distancia / Math.max(1, pinca.current.distancia)))
      return
    }
    const ddx = e.clientX - anterior.x
    const ddy = e.clientY - anterior.y
    mudar((atual) => ({ dx: atual.dx + ddx, dy: atual.dy + ddy }))
  }

  function aoSoltar(e: React.PointerEvent<HTMLDivElement>) {
    ponteiros.current.delete(e.pointerId)
    if (ponteiros.current.size < 2) pinca.current = null
  }

  function teclado(e: React.KeyboardEvent<HTMLDivElement>) {
    const passo = e.shiftKey ? 20 : 6
    const acoes: Record<string, () => void> = {
      ArrowLeft: () => mudar({ dx: estado.dx - passo }),
      ArrowRight: () => mudar({ dx: estado.dx + passo }),
      ArrowUp: () => mudar({ dy: estado.dy - passo }),
      ArrowDown: () => mudar({ dy: estado.dy + passo }),
      '+': () => zoomPara(estado.zoom + 0.1),
      '=': () => zoomPara(estado.zoom + 0.1),
      '-': () => zoomPara(estado.zoom - 0.1),
    }
    const acao = acoes[e.key]
    if (acao) {
      e.preventDefault()
      acao()
    }
  }

  // Roda do mouse: zoom sem rolar a página.
  useEffect(() => {
    const caixa = caixaRef.current?.querySelector<HTMLDivElement>('[data-moldura]')
    if (!caixa) return
    const roda = (e: WheelEvent) => {
      e.preventDefault()
      setEstado((atual) =>
        img ? limitar({ ...atual, zoom: Math.max(1, Math.min(ZOOM_MAXIMO, atual.zoom - e.deltaY * 0.0015)) }, img, lado) : atual,
      )
    }
    caixa.addEventListener('wheel', roda, { passive: false })
    return () => caixa.removeEventListener('wheel', roda)
  }, [img, lado])

  async function confirmar() {
    if (!img) return
    setSalvando(true)
    try {
      const { w, h } = medidas(img, estado.rot)
      const escala = (lado / Math.min(w, h)) * estado.zoom
      const k = LADO_SAIDA / lado
      const tela = document.createElement('canvas')
      tela.width = LADO_SAIDA
      tela.height = LADO_SAIDA
      const ctx = tela.getContext('2d')
      if (!ctx) throw new Error('canvas')
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, LADO_SAIDA, LADO_SAIDA)
      ctx.imageSmoothingQuality = 'high'
      ctx.translate(LADO_SAIDA / 2 + estado.dx * k, LADO_SAIDA / 2 + estado.dy * k)
      ctx.rotate((estado.rot * Math.PI) / 180)
      ctx.scale(escala * k, escala * k)
      ctx.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2)
      const blob = await new Promise<Blob>((resolver, rejeitar) =>
        tela.toBlob((b) => (b ? resolver(b) : rejeitar(new Error('jpeg'))), 'image/jpeg', 0.88),
      )
      await aoConfirmar(blob)
    } catch {
      setErro('Não foi possível preparar a foto. Tente outra imagem.')
    } finally {
      setSalvando(false)
    }
  }

  const escalaBase = img ? lado / Math.min(medidas(img, estado.rot).w, medidas(img, estado.rot).h) : 1
  const transformar = (fator: number) =>
    `translate(-50%, -50%) translate(${estado.dx * fator}px, ${estado.dy * fator}px) rotate(${estado.rot}deg) scale(${
      escalaBase * estado.zoom * fator
    })`

  const imagemNa = (fator: number) =>
    img && (
      <img
        src={img.src}
        alt=""
        draggable={false}
        className="pointer-events-none absolute left-1/2 top-1/2 max-w-none select-none"
        style={{ width: img.naturalWidth, height: img.naturalHeight, transform: transformar(fator) }}
      />
    )

  const btnNeutro = portal ? 'rec-btn-neutro' : 'btn-neutro'
  const btnPrimario = portal ? 'rec-btn-primario' : 'btn-primario'

  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-semibold text-slate-900">Ajuste a foto</p>
        <p className="text-xs text-slate-500">Arraste para centralizar o rosto no círculo e use o zoom se precisar.</p>
      </div>
      <div ref={caixaRef} className="w-full max-w-[300px]">
        <div
          data-moldura
          role="img"
          aria-label="Enquadramento da foto. Use as setas para mover e + ou - para o zoom."
          tabIndex={0}
          onPointerDown={aoApertar}
          onPointerMove={aoMover}
          onPointerUp={aoSoltar}
          onPointerCancel={aoSoltar}
          onKeyDown={teclado}
          className="relative cursor-grab touch-none overflow-hidden rounded-xl bg-slate-900 outline-none focus-visible:ring-2 focus-visible:ring-marca-500 active:cursor-grabbing"
          style={{ width: lado, height: lado }}
        >
          {imagemNa(1)}
          {!img && !erro && <p className="absolute inset-0 grid place-items-center text-sm text-white/70">Carregando...</p>}
          {/* Círculo-guia = o que o telão mostra; os cantos aparecem no cartão e nas listas. */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{ background: `radial-gradient(circle at center, transparent ${lado / 2 - 1}px, rgba(0,0,0,.45) ${lado / 2}px)` }}
          />
          <div className="pointer-events-none absolute inset-0 rounded-full border-2 border-mallory-laranja" />
        </div>
      </div>

      {erro && (
        <p role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
          {erro}
        </p>
      )}

      <div className="flex max-w-[300px] items-center gap-2">
        <span className="text-xs text-slate-500" aria-hidden="true">−</span>
        <input
          type="range"
          min={1}
          max={ZOOM_MAXIMO}
          step={0.01}
          value={estado.zoom}
          onChange={(e) => zoomPara(Number(e.target.value))}
          className="flex-1 accent-marca-600"
          aria-label="Zoom da foto"
          disabled={!img}
        />
        <span className="text-xs text-slate-500" aria-hidden="true">+</span>
      </div>

      <div className="flex max-w-[300px] gap-2">
        <button type="button" className={`${btnNeutro} flex-1`} disabled={!img} onClick={() => mudar({ rot: (estado.rot + 90) % 360 })}>
          <Icone nome="girar" className="h-4 w-4" /> Girar
        </button>
        <button type="button" className={`${btnNeutro} flex-1`} disabled={!img} onClick={() => img && setEstado({ ...INICIAL, rot: estado.rot })}>
          <Icone nome="centralizar" className="h-4 w-4" /> Centralizar
        </button>
      </div>

      {img && (
        <div className="flex items-end gap-4">
          <Previa rotulo="Telão" tamanho={72} redonda>
            {imagemNa(72 / lado)}
          </Previa>
          <Previa rotulo="Cartão" tamanho={48}>
            {imagemNa(48 / lado)}
          </Previa>
          <Previa rotulo="Listas" tamanho={32}>
            {imagemNa(32 / lado)}
          </Previa>
        </div>
      )}

      <div className="flex max-w-[300px] gap-2">
        <button type="button" className={`${btnNeutro} flex-1`} onClick={aoCancelar} disabled={salvando}>
          {textoCancelar}
        </button>
        <button type="button" className={`${btnPrimario} flex-1`} onClick={() => void confirmar()} disabled={!img || salvando}>
          {salvando ? 'Salvando...' : 'Usar esta foto'}
        </button>
      </div>
    </div>
  )
}

function Previa({
  rotulo,
  tamanho,
  redonda = false,
  children,
}: {
  rotulo: string
  tamanho: number
  redonda?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="text-center">
      <div
        className={`relative overflow-hidden bg-slate-200 ${redonda ? 'rounded-full ring-2 ring-amber-400' : 'rounded-lg'}`}
        style={{ width: tamanho, height: tamanho }}
      >
        {children}
      </div>
      <p className="mt-1 text-[11px] text-slate-500">{rotulo}</p>
    </div>
  )
}
