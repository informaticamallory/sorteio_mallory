import { useEffect, useRef, useState } from 'react'
import { EVENTO_SESSAO_ENCERRADA, gravarToken, lerToken } from './api'

export type EstadoCanal = 'conectando' | 'conectado' | 'reconectando'

export interface MensagemPrivada {
  tipo: 'pronto' | 'notificacao' | 'atualizacao' | 'sessao_encerrada'
}

/**
 * Canal privado e autenticado (SSE) da área pessoal.
 *
 * Usa fetch com streaming em vez de EventSource porque o EventSource não envia
 * cabeçalhos: o token vai no Authorization, nunca na URL (que fica em logs).
 * As mensagens não carregam dado pessoal; servem para a tela reler a área
 * pessoal. Reconecta sozinho com espera crescente; a cada reconexão a tela
 * também relê os dados, então nada se perde enquanto o celular esteve offline.
 */
export function useCanalPrivado(aoReceber: (mensagem: MensagemPrivada) => void): EstadoCanal {
  const [estado, setEstado] = useState<EstadoCanal>('conectando')
  const callback = useRef(aoReceber)
  callback.current = aoReceber

  useEffect(() => {
    let ativo = true
    let controlador: AbortController | null = null
    let espera = 1000

    const encerrarSessao = () => {
      gravarToken(null)
      window.dispatchEvent(new Event(EVENTO_SESSAO_ENCERRADA))
    }

    async function conectar() {
      while (ativo) {
        const token = lerToken()
        if (!token) return
        controlador = new AbortController()
        try {
          const resposta = await fetch('/api/minha-area/stream', {
            headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
            signal: controlador.signal,
            cache: 'no-store',
          })
          if (resposta.status === 401) {
            encerrarSessao()
            return
          }
          if (!resposta.ok || !resposta.body) throw new Error(`HTTP ${resposta.status}`)

          const leitor = resposta.body.getReader()
          const decodificador = new TextDecoder()
          let pendente = ''
          espera = 1000
          for (;;) {
            const { value, done } = await leitor.read()
            if (done) break
            pendente += decodificador.decode(value, { stream: true })
            const blocos = pendente.split('\n\n')
            pendente = blocos.pop() ?? ''
            for (const bloco of blocos) {
              const dados = bloco
                .split('\n')
                .filter((linha) => linha.startsWith('data:'))
                .map((linha) => linha.slice(5).trim())
                .join('')
              if (!dados) continue
              try {
                const mensagem = JSON.parse(dados) as MensagemPrivada
                if (mensagem.tipo === 'sessao_encerrada') {
                  encerrarSessao()
                  return
                }
                if (mensagem.tipo === 'pronto') setEstado('conectado')
                callback.current(mensagem)
              } catch {
                /* mensagem malformada: ignorada */
              }
            }
          }
        } catch {
          if (!ativo) return
        }
        if (!ativo) return
        setEstado('reconectando')
        await new Promise((r) => setTimeout(r, espera))
        espera = Math.min(espera * 2, 30_000)
      }
    }

    void conectar()
    return () => {
      ativo = false
      controlador?.abort()
    }
  }, [])

  return estado
}
