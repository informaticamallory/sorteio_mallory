import { useEffect, useState } from 'react'
import { requisitar } from '../api'
import { usePosicaoCarrossel } from '../carrossel'
import type { Bloco, TelaoEstado } from '../types'
import { Aviso } from './ui'
import Icone from './Icone'

type Acao = 'iniciar' | 'pausar' | 'continuar' | 'repetir' | 'proximo' | 'anterior' | 'encerrar'

/**
 * Controles da apresentação dos ganhadores. O estado oficial é do servidor;
 * este cartão só envia comandos e mostra o que o telão está exibindo.
 * Nenhum comando sorteia ou altera resultado.
 */
export default function ControleCarrossel({
  eventId,
  telao,
  blocos,
}: {
  eventId: number
  telao: TelaoEstado | null
  blocos: Bloco[]
}) {
  const ativo = telao?.estado === 'carrossel_ganhadores' && !!telao.carrossel
  const carrossel = ativo ? telao?.carrossel : null
  const { posicao, progresso } = usePosicaoCarrossel(carrossel, telao?.servidor_agora)
  const comGanhadores = blocos.filter((b) => b.sorteadas > 0)
  const [blocoId, setBlocoId] = useState<number | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')

  // Padrão: o último bloco finalizado com ganhadores.
  useEffect(() => {
    if (blocoId !== null && comGanhadores.some((b) => b.id === blocoId)) return
    const finalizados = comGanhadores.filter((b) => b.status === 'FINALIZADO')
    const padrao = finalizados[finalizados.length - 1] ?? comGanhadores[comGanhadores.length - 1]
    setBlocoId(padrao?.id ?? null)
  }, [comGanhadores, blocoId])

  async function comandar(acao: Acao) {
    setEnviando(true)
    setErro('')
    try {
      await requisitar(`/api/events/${eventId}/telao/carrossel`, {
        metodo: 'POST',
        corpo: acao === 'iniciar' ? { acao, bloco_id: blocoId } : { acao },
      })
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Comando não aplicado')
    } finally {
      setEnviando(false)
    }
  }

  const blocoExibido = blocos.find((b) => b.id === carrossel?.bloco_id)
  const atual = carrossel && posicao < carrossel.total ? carrossel.slides[posicao] : null

  return (
    <div className="cartao p-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-semibold text-slate-900">Apresentação dos ganhadores</h2>
        {ativo && (
          <span className={`etiqueta ${carrossel?.pausado ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}`}>
            {carrossel?.pausado ? 'Pausada' : 'No telão'}
          </span>
        )}
      </div>
      {erro && (
        <div className="mb-3">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}

      {telao?.carrossel_agendado_em && !ativo && (
        <div className="mb-3">
          <Aviso tipo="info">A apresentação do bloco começa sozinha logo após a revelação.</Aviso>
        </div>
      )}

      {ativo && carrossel ? (
        <div className="space-y-3">
          <div className="rounded-md border border-borda bg-slate-50 p-3">
            <p className="text-xs text-slate-500">
              {blocoExibido?.nome ?? 'Bloco'} · {Math.min(posicao + 1, carrossel.total)} de {carrossel.total}
            </p>
            <p className="truncate font-medium text-slate-900">
              {atual ? `${atual.ganhador_nome} — ${atual.premio_nome}` : 'Resumo final do bloco'}
            </p>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-marca-500" style={{ width: `${Math.round(progresso * 100)}%` }} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button type="button" className="btn-neutro px-2" disabled={enviando} onClick={() => void comandar('anterior')}>
              <Icone nome="anterior" className="h-4 w-4" /> Anterior
            </button>
            {carrossel.pausado ? (
              <button type="button" className="btn-primario px-2" disabled={enviando} onClick={() => void comandar('continuar')}>
                <Icone nome="play" className="h-4 w-4" /> Continuar
              </button>
            ) : (
              <button type="button" className="btn-primario px-2" disabled={enviando} onClick={() => void comandar('pausar')}>
                <Icone nome="pausa" className="h-4 w-4" /> Pausar
              </button>
            )}
            <button type="button" className="btn-neutro px-2" disabled={enviando} onClick={() => void comandar('proximo')}>
              Próximo <Icone nome="proximo" className="h-4 w-4" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" className="btn-neutro" disabled={enviando} onClick={() => void comandar('repetir')}>
              <Icone nome="repetir" className="h-4 w-4" /> Repetir
            </button>
            <button type="button" className="btn-perigo" disabled={enviando} onClick={() => void comandar('encerrar')}>
              Encerrar
            </button>
          </div>
          <p className="text-xs text-slate-500">
            Cada ganhador fica {carrossel.duracao_s} s na tela. Para sortear o próximo bloco, encerre a
            apresentação.
          </p>
        </div>
      ) : comGanhadores.length === 0 ? (
        <p className="text-sm text-slate-500">
          Os ganhadores aparecem aqui quando um bloco tiver resultados. Ao finalizar um bloco, a
          apresentação começa sozinha no telão.
        </p>
      ) : (
        <div className="space-y-2">
          <label className="rotulo" htmlFor="bloco-carrossel">
            Bloco
          </label>
          <select
            id="bloco-carrossel"
            className="campo"
            value={blocoId ?? ''}
            onChange={(e) => setBlocoId(Number(e.target.value))}
          >
            {comGanhadores.map((b) => (
              <option key={b.id} value={b.id}>
                {b.nome} · {b.sorteadas} ganhador(es){b.status === 'FINALIZADO' ? '' : ' · em aberto'}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-primario w-full"
            disabled={enviando || blocoId === null}
            onClick={() => void comandar('iniciar')}
          >
            Iniciar apresentação
          </button>
        </div>
      )}
    </div>
  )
}
