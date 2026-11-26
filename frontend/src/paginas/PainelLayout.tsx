import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate, Outlet, useLocation, useOutletContext, useParams } from 'react-router-dom'
import { requisitar } from '../api'
import { useAuth } from '../auth'
import type { Permissao } from '../auth'
import Casca, { type ItemMenu } from '../componentes/Casca'
import Icone, { type NomeIcone } from '../componentes/Icone'
import { Aviso, Carregando } from '../componentes/ui'
import type { Evento, Resumo } from '../types'

export interface ContextoPainel {
  evento: Evento
  resumo: Resumo | null
  recarregarEvento: () => Promise<void>
  recarregarResumo: () => Promise<void>
}

export function usePainel(): ContextoPainel {
  return useOutletContext<ContextoPainel>()
}

// Ordem do menu. A tela inicial segue ORDEM_INICIAL: Admin e Organizador caem
// na Visão geral; Sorteador em Sorteio; a conta Recepção no Credenciamento
// (ela também tem Entregas); a Equipe de Entregas em Entregas. O check-in e a
// consulta públicos ficam em /recepcao.
export const ABAS: { para: string; rotulo: string; permissao: Permissao; icone: NomeIcone; titulo?: string }[] = [
  { para: 'visao-geral', rotulo: 'Visão geral', permissao: 'consultar_relatorios', icone: 'painel' },
  { para: 'sorteio', rotulo: 'Sorteio', permissao: 'controlar_sorteio', icone: 'sorteio' },
  { para: 'credenciamento', rotulo: 'Credenciamento', permissao: 'acompanhar_credenciamento', icone: 'credenciamento' },
  { para: 'entregas', rotulo: 'Entregas', permissao: 'pesquisar_colaboradores', icone: 'entregas', titulo: 'Central de Entregas' },
  // Tela de Blocos só para quem monta os blocos. O Sorteador escolhe e inicia o
  // bloco na própria tela de Sorteio (a leitura dos blocos continua liberada a ele).
  { para: 'blocos', rotulo: 'Blocos', permissao: 'configurar_blocos', icone: 'blocos', titulo: 'Gerenciamento de Blocos' },
  { para: 'participantes', rotulo: 'Participantes', permissao: 'gerenciar_participantes', icone: 'participantes' },
  { para: 'premios', rotulo: 'Prêmios', permissao: 'cadastrar_premios', icone: 'premios' },
  { para: 'regras', rotulo: 'Regras', permissao: 'definir_regras', icone: 'regras' },
  { para: 'historico', rotulo: 'Histórico', permissao: 'consultar_resultados', icone: 'historico' },
  { para: 'relatorio', rotulo: 'Relatório', permissao: 'consultar_relatorios', icone: 'relatorio' },
  { para: 'configuracao', rotulo: 'Configuração', permissao: 'configurar_evento', icone: 'configuracao' },
]

const ORDEM_INICIAL = ['visao-geral', 'sorteio', 'credenciamento', 'entregas']

export function abaInicial(pode: (p: Permissao) => boolean): string | null {
  const permitidas = ABAS.filter((aba) => pode(aba.permissao))
  const preferida = ORDEM_INICIAL.find((para) => permitidas.some((aba) => aba.para === para))
  return preferida ?? permitidas[0]?.para ?? null
}

/** Rota índice do evento: abre a primeira aba permitida ao perfil. */
export function AbaInicial() {
  const { pode } = useAuth()
  const aba = abaInicial(pode)
  if (!aba) return <Aviso tipo="atencao">Seu perfil não tem telas neste evento.</Aviso>
  return <Navigate to={aba} replace />
}

export default function PainelLayout() {
  const { eventId } = useParams()
  const { pode } = useAuth()
  const local = useLocation()
  const [evento, setEvento] = useState<Evento | null>(null)
  const [resumo, setResumo] = useState<Resumo | null>(null)
  const [erro, setErro] = useState('')

  const recarregarEvento = useCallback(async () => {
    setEvento(await requisitar<Evento>(`/api/events/${eventId}`))
  }, [eventId])

  const recarregarResumo = useCallback(async () => {
    setResumo(await requisitar<Resumo>(`/api/events/${eventId}/resumo`))
  }, [eventId])

  useEffect(() => {
    setEvento(null)
    setErro('')
    Promise.all([recarregarEvento(), recarregarResumo()]).catch((e) =>
      setErro(e instanceof Error ? e.message : 'Falha ao carregar o evento'),
    )
  }, [recarregarEvento, recarregarResumo])

  if (erro) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <Aviso tipo="erro">{erro}</Aviso>
        <Link to="/eventos" className="btn-neutro mt-4">
          Voltar para eventos
        </Link>
      </div>
    )
  }
  if (!evento) return <Carregando texto="Carregando evento..." />

  const abas = ABAS.filter((aba) => pode(aba.permissao))
  const atual = ABAS.find((aba) => local.pathname.endsWith(`/${aba.para}`))
  const itens: ItemMenu[] = abas.map((aba) => ({ para: aba.para, rotulo: aba.rotulo, icone: aba.icone }))
  // Atalho para o check-in (tela da Recepção, que tem botão de volta ao Credenciamento).
  if (pode('acompanhar_credenciamento')) {
    itens.push({ para: '/recepcao', rotulo: 'Check-in', icone: 'cracha' })
  }
  if (pode('controlar_telao')) {
    itens.push({ para: `/telao/${evento.telao_token}`, rotulo: 'Abrir telão', icone: 'telao', externo: true })
  }
  if (pode('gerenciar_usuarios')) {
    itens.push({ para: '/usuarios', rotulo: 'Usuários', icone: 'usuarios' })
  }

  return (
    <Casca
      itens={itens}
      titulo={atual?.titulo ?? atual?.rotulo ?? evento.nome}
      subtitulo={evento.nome}
      contexto={
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-grafite-400">Evento</p>
          <p className="truncate text-sm font-medium text-white" title={evento.nome}>
            {evento.nome}
          </p>
          {pode('visualizar_evento') && (
            <Link
              to="/eventos"
              state={{ lista: true }}
              className="mt-1 inline-flex items-center gap-1 text-xs hover:text-white"
            >
              <Icone nome="voltar" className="h-3.5 w-3.5" />
              Todos os eventos
            </Link>
          )}
        </div>
      }
      faixa={
        evento.demo ? (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-center text-xs text-amber-900 sm:px-6">
            Evento de demonstração — dados fictícios, separados dos eventos reais
          </div>
        ) : evento.evento_teste ? (
          <FaixaEventoTeste eventoId={evento.id} podeRecomecar={pode('gerenciar_eventos')} />
        ) : undefined
      }
    >
      <Outlet context={{ evento, resumo, recarregarEvento, recarregarResumo }} />
    </Casca>
  )
}

/** Faixa do evento de teste, com "Recomeçar teste" (só o admin). */
function FaixaEventoTeste({ eventoId, podeRecomecar }: { eventoId: number; podeRecomecar: boolean }) {
  const [confirmando, setConfirmando] = useState(false)
  const [trabalhando, setTrabalhando] = useState(false)
  const [erro, setErro] = useState('')

  async function recomecar() {
    setTrabalhando(true)
    setErro('')
    try {
      await requisitar(`/api/events/${eventoId}/recomecar-teste`, { metodo: 'POST' })
      // Recarrega tudo (blocos, sorteio, telão) já zerado.
      window.location.reload()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao recomeçar o teste')
      setTrabalhando(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-slate-200 bg-slate-100 px-4 py-1.5 text-center text-xs text-slate-700 sm:px-6">
      <span>Evento de teste — não aparece no portal do colaborador nem manda avisos para o celular</span>
      {podeRecomecar &&
        (confirmando ? (
          <span className="flex items-center gap-2">
            <span className="font-semibold text-rose-700">Apagar todos os sorteios e entregas deste teste?</span>
            <button
              type="button"
              className="rounded-md bg-rose-600 px-2 py-0.5 font-semibold text-white hover:bg-rose-700"
              disabled={trabalhando}
              onClick={() => void recomecar()}
            >
              {trabalhando ? 'Recomeçando...' : 'Sim, recomeçar'}
            </button>
            <button type="button" className="underline" disabled={trabalhando} onClick={() => setConfirmando(false)}>
              Cancelar
            </button>
          </span>
        ) : (
          <button
            type="button"
            className="inline-flex items-center gap-1 font-semibold text-marca-700 hover:underline"
            onClick={() => setConfirmando(true)}
          >
            <Icone nome="repetir" className="h-3.5 w-3.5" />
            Recomeçar teste
          </button>
        ))}
      {erro && <span className="font-semibold text-rose-700">{erro}</span>}
    </div>
  )
}
