import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { EVENTO_SESSAO_ENCERRADA, gravarToken, lerToken, requisitar } from './api'
import type { Papel, Usuario } from './types'

// Espelho de app/permissoes.py, usado só para adaptar menus e botões.
// Quem decide o acesso é o backend, em toda requisição.
export type Permissao =
  | 'visualizar_evento'
  | 'gerenciar_eventos'
  | 'configurar_evento'
  | 'desfazer_entrega'
  | 'gerenciar_usuarios'
  | 'gerenciar_participantes'
  | 'cadastrar_premios'
  | 'configurar_blocos'
  | 'definir_regras'
  | 'anular_resultado'
  | 'consultar_relatorios'
  | 'exportar_resultados'
  | 'visualizar_auditoria'
  | 'visualizar_blocos'
  | 'controlar_sorteio'
  | 'controlar_telao'
  | 'consultar_resultados'
  | 'pular_ordem_do_bloco'
  | 'pesquisar_colaboradores'
  | 'confirmar_entrega'
  | 'consultar_atendimentos'
  | 'acompanhar_credenciamento'
  | 'auxiliar_credenciamento'
  | 'acessar_area_pessoal'

export const ROTULO_PAPEL: Record<Papel, string> = {
  ADMIN: 'Administrador',
  ORGANIZADOR: 'Organizador — RH',
  SORTEIO: 'Sorteador',
  RECEPCAO: 'Recepção / Credenciamento',
  ENTREGAS: 'Equipe de Entregas',
  COLABORADOR: 'Colaborador',
}

/** Primeira tela de cada perfil após o login. */
export function destinoInicial(usuario: Usuario): string {
  if (usuario.deve_trocar_senha) return '/trocar-senha'
  if (usuario.papel === 'COLABORADOR') return '/minha-area'
  // Check-in e consulta são públicos; a conta Recepção cai na mesma tela.
  if (usuario.papel === 'RECEPCAO') return '/recepcao'
  return '/eventos'
}

interface ContextoAuth {
  usuario: Usuario | null
  carregando: boolean
  entrar: (usuario: string, senha: string) => Promise<Usuario>
  sair: () => void
  /** Troca a sessão atual (após trocar a senha, o servidor emite um token novo). */
  adotarSessao: (token: string, usuario: Usuario) => void
  pode: (permissao: Permissao) => boolean
}

const Contexto = createContext<ContextoAuth | null>(null)

export function ProvedorAuth({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null)
  const [carregando, setCarregando] = useState(true)

  useEffect(() => {
    let ativo = true
    if (!lerToken()) {
      setCarregando(false)
      return
    }
    requisitar<Usuario>('/api/auth/me')
      .then((u) => ativo && setUsuario(u))
      .catch(() => gravarToken(null))
      .finally(() => ativo && setCarregando(false))
    return () => {
      ativo = false
    }
  }, [])

  // Sessão encerrada no servidor (conta desativada, perfil alterado, senha
  // redefinida, token expirado): volta ao login na próxima requisição.
  useEffect(() => {
    const encerrar = () => setUsuario(null)
    window.addEventListener(EVENTO_SESSAO_ENCERRADA, encerrar)
    return () => window.removeEventListener(EVENTO_SESSAO_ENCERRADA, encerrar)
  }, [])

  const entrar = useCallback(async (login: string, senha: string) => {
    const resposta = await requisitar<{ access_token: string; usuario: Usuario }>(
      '/api/auth/login',
      { metodo: 'POST', corpo: { usuario: login, senha }, autenticado: false },
    )
    gravarToken(resposta.access_token)
    setUsuario(resposta.usuario)
    return resposta.usuario
  }, [])

  const sair = useCallback(() => {
    gravarToken(null)
    setUsuario(null)
  }, [])

  const adotarSessao = useCallback((token: string, novo: Usuario) => {
    gravarToken(token)
    setUsuario(novo)
  }, [])

  const pode = useCallback(
    (permissao: Permissao) =>
      // Backend anterior à Fase 4 não envia permissões: todo usuário era admin.
      usuario?.permissoes === undefined ? true : usuario.permissoes.includes(permissao),
    [usuario],
  )

  const valor = useMemo(
    () => ({ usuario, carregando, entrar, sair, adotarSessao, pode }),
    [usuario, carregando, entrar, sair, adotarSessao, pode],
  )
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

export function useAuth(): ContextoAuth {
  const contexto = useContext(Contexto)
  if (!contexto) throw new Error('useAuth precisa estar dentro de ProvedorAuth')
  return contexto
}
