import { useCallback, useEffect, useRef, useState } from 'react'
import type { TelaoEstado } from './types'

export type Conexao = 'conectando' | 'conectado' | 'reconectando' | 'erro'

/**
 * Assina o estado do telao via SSE.
 *
 * Pontos importantes de confiabilidade:
 *  - o estado completo chega na conexao e a cada mudanca, entao F5/reconexao
 *    recuperam a tela sem nenhuma acao do organizador;
 *  - a transicao "sorteando -> resultado" e agendada pelo tempo que o PROPRIO
 *    servidor informou (revelar_em - servidor_agora), imune a relogio local
 *    desajustado;
 *  - ao fim da animacao o cliente apenas LE o estado; nunca dispara sorteio;
 *  - o carrossel dos ganhadores avanca pelo relogio do servidor (ver
 *    carrossel.ts), entao nao precisa de mensagens a cada slide.
 */
export function useTelao(token: string | undefined) {
  const [estado, setEstado] = useState<TelaoEstado | null>(null)
  const [conexao, setConexao] = useState<Conexao>('conectando')
  const versaoRef = useRef(-1)
  const temporizadorRef = useRef<number | null>(null)

  const aplicar = useCallback((novo: TelaoEstado) => {
    // Mensagens fora de ordem nao podem retroceder a tela.
    if (novo.versao < versaoRef.current) return
    versaoRef.current = novo.versao
    setEstado(novo)
  }, [])

  const buscarEstado = useCallback(async () => {
    if (!token) return
    try {
      const resposta = await fetch(`/api/public/${token}/estado`)
      if (!resposta.ok) return
      aplicar((await resposta.json()) as TelaoEstado)
    } catch {
      /* a proxima tentativa do SSE resolve */
    }
  }, [token, aplicar])

  useEffect(() => {
    if (!token) return
    const fonte = new EventSource(`/api/public/${token}/stream`)

    fonte.onopen = () => setConexao('conectado')
    fonte.onmessage = (evento) => {
      setConexao('conectado')
      try {
        aplicar(JSON.parse(evento.data) as TelaoEstado)
      } catch {
        /* mensagem malformada: ignorada */
      }
    }
    fonte.onerror = () => {
      // O EventSource reconecta sozinho; sinalizamos para a interface.
      setConexao((atual) => (atual === 'conectado' ? 'reconectando' : 'erro'))
    }

    return () => fonte.close()
  }, [token, aplicar])

  // Agenda a leitura do resultado para o fim exato da animacao.
  useEffect(() => {
    if (temporizadorRef.current) {
      window.clearTimeout(temporizadorRef.current)
      temporizadorRef.current = null
    }
    if (!estado) return
    // Próxima mudança que o servidor faz sozinho: revelação do sorteio ou
    // início do carrossel agendado para depois dela (fim de bloco).
    const alvo =
      estado.estado === 'sorteando' && estado.revelar_em
        ? estado.revelar_em
        : estado.estado !== 'carrossel_ganhadores'
          ? estado.carrossel_agendado_em
          : null
    if (!alvo) return

    const restante = new Date(alvo).getTime() - new Date(estado.servidor_agora).getTime()
    temporizadorRef.current = window.setTimeout(
      () => void buscarEstado(),
      Math.max(0, restante) + 120,
    )

    return () => {
      if (temporizadorRef.current) window.clearTimeout(temporizadorRef.current)
    }
  }, [estado, buscarEstado])

  return { estado, conexao, recarregar: buscarEstado }
}

/** Milissegundos restantes da animacao, calculados com o relogio do servidor. */
export function msRestantes(estado: TelaoEstado | null): number {
  if (!estado?.revelar_em) return 0
  return Math.max(
    0,
    new Date(estado.revelar_em).getTime() - new Date(estado.servidor_agora).getTime(),
  )
}
