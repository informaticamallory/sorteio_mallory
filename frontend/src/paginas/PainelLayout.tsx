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

// A ordem define a tela inicial de cada perfil: a primeira que ele pode ver.
// Admin e Organizador caem na Visão geral; Sorteador em Sorteio; a conta
// Recepção no Credenciamento. O check-in e a consulta públicos ficam em /recepcao.
export const ABAS: { para: string; rotulo: string; permissao: Permissao; icone: NomeIcone; titulo?: string }[] = [
  { para: 'visao-geral', rotulo: 'Visão geral', permissao: 'consultar_relatorios', icone: 'painel' },
  { para: 'sorteio', rotulo: 'Sorteio', permissao: 'controlar_sorteio', icone: 'sorteio' },
  { para: 'entregas', rotulo: 'Entregas', permissao: 'pesquisar_colaboradores', icone: 'entregas', titulo: 'Central de Entregas' },
  { para: 'credenciamento', rotulo: 'Credenciamento', permissao: 'acompanhar_credenciamento', icone: 'credenciamento' },
  { para: 'blocos', rotulo: 'Blocos', permissao: 'visualizar_blocos', icone: 'blocos', titulo: 'Gerenciamento de Blocos' },
  { para: 'participantes', rotulo: 'Participantes', permissao: 'gerenciar_participantes', icone: 'participantes' },
  { para: 'premios', rotulo: 'Prêmios', permissao: 'cadastrar_premios', icone: 'premios' },
  { para: 'regras', rotulo: 'Regras', permissao: 'definir_regras', icone: 'regras' },
  { para: 'historico', rotulo: 'Histórico', permissao: 'consultar_resultados', icone: 'historico' },
  { para: 'relatorio', rotulo: 'Relatório', permissao: 'consultar_relatorios', icone: 'relatorio' },
  { para: 'configuracao', rotulo: 'Configuração', permissao: 'configurar_evento', icone: 'configuracao' },
]

export function abaInicial(pode: (p: Permissao) => boolean): string | null {
  return ABAS.find((aba) => pode(aba.permissao))?.para ?? null
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
          {pode('gerenciar_eventos') && (
            <Link to="/eventos" className="mt-1 inline-flex items-center gap-1 text-xs hover:text-white">
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
        ) : undefined
      }
    >
      <Outlet context={{ evento, resumo, recarregarEvento, recarregarResumo }} />
    </Casca>
  )
}
