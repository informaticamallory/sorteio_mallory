import { useEffect, useState } from 'react'
import { requisitar } from '../api'
import { Aviso, Modal } from '../componentes/ui'
import type { Sorteio } from '../types'

const TIPOS = [
  { valor: 'ausencia', rotulo: 'Ganhador não estava presente' },
  { valor: 'desistencia', rotulo: 'Ganhador desistiu do prêmio' },
  { valor: 'erro_operacional', rotulo: 'Erro operacional do organizador' },
  { valor: 'outro', rotulo: 'Outro motivo' },
]

/**
 * Anulacao justificada. O resultado anterior e preservado como anulado e a
 * unidade volta a ficar disponivel; o nome do vencedor nunca e editado.
 */
export default function ModalAnulacao({
  aberto,
  sorteio,
  eventId,
  aoFechar,
  aoConcluir,
}: {
  aberto: boolean
  /** Basta o que o aviso mostra (a Central de Entregas não tem o Sorteio completo). */
  sorteio: Pick<Sorteio, 'id' | 'rodada' | 'ganhador_nome' | 'premio_nome' | 'entregue'> | null
  eventId: number
  aoFechar: () => void
  aoConcluir: (atualizado: Sorteio) => Promise<void> | void
}) {
  const [motivo, setMotivo] = useState('')
  const [tipo, setTipo] = useState('ausencia')
  const [confirmarEstorno, setConfirmarEstorno] = useState(false)
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (aberto) {
      setMotivo('')
      setTipo('ausencia')
      setConfirmarEstorno(false)
      setErro('')
    }
  }, [aberto])

  if (!sorteio) return null

  async function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (!sorteio) return
    setEnviando(true)
    setErro('')
    try {
      const atualizado = await requisitar<Sorteio>(
        `/api/events/${eventId}/sorteios/${sorteio.id}/anular`,
        {
          metodo: 'POST',
          corpo: { motivo: motivo.trim(), tipo, confirmar_estorno: confirmarEstorno },
        },
      )
      await aoConcluir(atualizado)
    } catch (erroAnular) {
      setErro(erroAnular instanceof Error ? erroAnular.message : 'Falha ao anular')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal titulo="Anular resultado" aberto={aberto} aoFechar={aoFechar}>
      <form onSubmit={enviar} className="space-y-4">
        <Aviso tipo="atencao">
          O resultado da rodada {sorteio.rodada} (<strong>{sorteio.ganhador_nome}</strong> —{' '}
          {sorteio.premio_nome}) será preservado no histórico como <strong>anulado</strong>. A
          unidade volta a ficar disponível e um novo sorteio deverá ser feito.
        </Aviso>

        {sorteio.entregue && (
          <label className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-rose-600"
              checked={confirmarEstorno}
              onChange={(e) => setConfirmarEstorno(e.target.checked)}
            />
            <span className="text-rose-900">
              Este prêmio já consta como <strong>entregue</strong>. Confirmo o estorno: o prêmio
              será recolhido e a entrega cancelada.
            </span>
          </label>
        )}

        <div>
          <label className="rotulo" htmlFor="tipo-anulacao">
            Tipo
          </label>
          <select
            id="tipo-anulacao"
            className="campo"
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
          >
            {TIPOS.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.rotulo}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="rotulo" htmlFor="motivo-anulacao">
            Justificativa (mínimo 5 caracteres)
          </label>
          <textarea
            id="motivo-anulacao"
            className="campo"
            rows={3}
            required
            minLength={5}
            autoFocus
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: chamado três vezes e não compareceu ao palco"
          />
        </div>

        {erro && <Aviso tipo="erro">{erro}</Aviso>}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn-perigo"
            disabled={enviando || (sorteio.entregue && !confirmarEstorno)}
          >
            {enviando ? 'Anulando...' : 'Anular resultado'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
