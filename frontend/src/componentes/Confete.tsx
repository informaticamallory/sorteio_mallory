import { useEffect, useRef } from 'react'

interface Particula {
  x: number
  y: number
  vx: number
  vy: number
  rotacao: number
  giro: number
  largura: number
  altura: number
  cor: string
}

/**
 * Confetes em canvas, sem biblioteca externa - o evento pode rodar sem internet.
 * `ativo=false` ou `reduzido=true` nao desenham nada.
 */
export default function Confete({
  ativo,
  reduzido = false,
  cores = ['#D4AF37', '#F8FAFC', '#1D4ED8', '#E6C75A', '#38BDF8'],
  duracaoMs = 7000,
  quantidade = 160,
}: {
  ativo: boolean
  reduzido?: boolean
  cores?: string[]
  duracaoMs?: number
  /** Menos partículas = celebração mais discreta (usado no carrossel). */
  quantidade?: number
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    if (!ativo || reduzido) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const redimensionar = () => {
      canvas.width = canvas.clientWidth * dpr
      canvas.height = canvas.clientHeight * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    redimensionar()
    window.addEventListener('resize', redimensionar)

    const largura = () => canvas.clientWidth
    const altura = () => canvas.clientHeight

    const particulas: Particula[] = Array.from({ length: quantidade }, () => ({
      x: Math.random() * largura(),
      y: -20 - Math.random() * altura() * 0.8,
      vx: (Math.random() - 0.5) * 1.6,
      vy: 1.6 + Math.random() * 2.6,
      rotacao: Math.random() * Math.PI,
      giro: (Math.random() - 0.5) * 0.18,
      largura: 6 + Math.random() * 7,
      altura: 9 + Math.random() * 10,
      cor: cores[Math.floor(Math.random() * cores.length)],
    }))

    const inicio = performance.now()
    let quadro = 0

    const desenhar = (agora: number) => {
      const decorrido = agora - inicio
      ctx.clearRect(0, 0, largura(), altura())

      // Desvanece nos ultimos 1,5s em vez de sumir de uma vez.
      const opacidade = decorrido > duracaoMs - 1500 ? Math.max(0, (duracaoMs - decorrido) / 1500) : 1
      ctx.globalAlpha = opacidade

      for (const p of particulas) {
        p.x += p.vx
        p.y += p.vy
        p.rotacao += p.giro
        p.vx += Math.sin((p.y + decorrido / 240) / 40) * 0.016

        if (p.y > altura() + 24) {
          p.y = -24
          p.x = Math.random() * largura()
        }

        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate(p.rotacao)
        ctx.fillStyle = p.cor
        ctx.fillRect(-p.largura / 2, -p.altura / 2, p.largura, p.altura)
        ctx.restore()
      }

      if (decorrido < duracaoMs) quadro = requestAnimationFrame(desenhar)
      else ctx.clearRect(0, 0, largura(), altura())
    }

    quadro = requestAnimationFrame(desenhar)
    return () => {
      cancelAnimationFrame(quadro)
      window.removeEventListener('resize', redimensionar)
      ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight)
    }
  }, [ativo, reduzido, cores, duracaoMs, quantidade])

  if (!ativo || reduzido) return null
  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  )
}
