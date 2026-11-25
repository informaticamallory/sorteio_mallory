import { useEffect, useState } from 'react'
import type { TelaoCarrossel } from './types'

/** Datas do servidor chegam em UTC sem fuso ("2026-11-13T22:10:00"). */
function instante(data: string): number {
  return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(data) ? data : `${data}Z`)
}

export interface PosicaoCarrossel {
  /** 0..total-1 = ganhador; total = slide-resumo. */
  posicao: number
  /** Fração do tempo do slide atual já exibida (0..1). */
  progresso: number
}

/**
 * Slide atual do carrossel calculado pelo relógio DO SERVIDOR.
 *
 * O servidor guarda só "posição base + início da reprodução + duração". Telão,
 * painel e qualquer aba recarregada chegam ao mesmo slide, sem depender do
 * relógio do aparelho (a diferença é medida pelo `servidor_agora` recebido).
 */
export function usePosicaoCarrossel(
  carrossel: TelaoCarrossel | null | undefined,
  servidorAgora: string | undefined,
): PosicaoCarrossel {
  const [, setTique] = useState(0)
  const [diferenca, setDiferenca] = useState(0)

  useEffect(() => {
    if (servidorAgora) setDiferenca(Date.now() - instante(servidorAgora))
  }, [servidorAgora])

  const rodando = !!carrossel && !carrossel.pausado && !!carrossel.rodando_desde
  useEffect(() => {
    if (!rodando) return
    const id = window.setInterval(() => setTique((t) => t + 1), 200)
    return () => window.clearInterval(id)
  }, [rodando])

  if (!carrossel) return { posicao: 0, progresso: 0 }
  const total = carrossel.total
  if (!rodando || !carrossel.rodando_desde) {
    return { posicao: Math.min(Math.max(carrossel.indice, 0), total), progresso: 0 }
  }
  const duracaoMs = Math.max(1, carrossel.duracao_s) * 1000
  const agoraServidor = Date.now() - diferenca
  const decorrido = Math.max(0, agoraServidor - instante(carrossel.rodando_desde))
  const posicao = Math.min(total, carrossel.indice + Math.floor(decorrido / duracaoMs))
  const progresso = posicao >= total ? 1 : (decorrido % duracaoMs) / duracaoMs
  return { posicao, progresso }
}
