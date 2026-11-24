import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { requisitar } from '../api'
import { ROTULO_PAPEL, useAuth } from '../auth'
import Casca, { type ItemMenu } from '../componentes/Casca'
import Icone from '../componentes/Icone'
import { Aviso, Carregando, Modal, Vazio } from '../componentes/ui'
import type { Evento } from '../types'

export default function Eventos() {
  const { usuario, pode } = useAuth()
  const navegar = useNavigate()
  const [eventos, setEventos] = useState<Evento[] | null>(null)
  const [erro, setErro] = useState('')
  const [criando, setCriando] = useState(false)
  const [nome, setNome] = useState('')
  const [empresa, setEmpresa] = useState('')
  const [salvando, setSalvando] = useState(false)

  async function carregar() {
    try {
      setEventos(await requisitar<Evento[]>('/api/events'))
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao carregar eventos')
    }
  }

  useEffect(() => {
    void carregar()
  }, [])

  async function criar(e: React.FormEvent) {
    e.preventDefault()
    setSalvando(true)
    setErro('')
    try {
      const evento = await requisitar<Evento>('/api/events', {
        metodo: 'POST',
        corpo: { nome: nome.trim(), empresa_nome: empresa.trim() },
      })
      navegar(`/eventos/${evento.id}/configuracao`)
    } catch (erroCriar) {
      setErro(erroCriar instanceof Error ? erroCriar.message : 'Falha ao criar o evento')
    } finally {
      setSalvando(false)
    }
  }

  // Equipe que não administra eventos e só tem um evento: vai direto à
  // própria tela (Operador -> Sorteio, Recepção -> Credenciamento).
  if (eventos?.length === 1 && !pode('gerenciar_eventos')) {
    return <Navigate to={`/eventos/${eventos[0].id}`} replace />
  }

  const itens: ItemMenu[] = [{ para: '/eventos', rotulo: 'Eventos', icone: 'eventos', fim: true }]
  if (pode('gerenciar_usuarios')) itens.push({ para: '/usuarios', rotulo: 'Usuários', icone: 'usuarios' })

  return (
    <Casca
      itens={itens}
      titulo="Eventos"
      subtitulo={usuario ? `${usuario.nome} · ${ROTULO_PAPEL[usuario.papel]}` : undefined}
      acoes={
        pode('gerenciar_eventos') && (
          <button type="button" className="btn-primario" onClick={() => setCriando(true)}>
            Novo evento
          </button>
        )
      }
    >
      <div className="space-y-4">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}

        {eventos === null ? (
          <Carregando />
        ) : eventos.length === 0 ? (
          <Vazio
            titulo="Nenhum evento cadastrado"
            descricao="Crie o primeiro evento para começar a cadastrar participantes e prêmios."
          />
        ) : (
          <div className="cartao overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Evento</th>
                  <th className="hidden sm:table-cell">Empresa</th>
                  <th className="hidden md:table-cell">Criado em</th>
                  <th className="text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {eventos.map((evento) => (
                  <tr key={evento.id}>
                    <td>
                      <Link to={`/eventos/${evento.id}`} className="font-medium text-slate-900 hover:text-marca-700 hover:underline">
                        {evento.nome}
                      </Link>
                      {evento.demo && (
                        <span className="etiqueta ml-2 bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200">
                          Demonstração
                        </span>
                      )}
                    </td>
                    <td className="hidden text-slate-600 sm:table-cell">{evento.empresa_nome || '—'}</td>
                    <td className="hidden text-slate-600 md:table-cell">
                      {new Date(`${evento.criado_em}Z`).toLocaleDateString('pt-BR')}
                    </td>
                    <td>
                      <div className="flex justify-end gap-1">
                        {pode('controlar_telao') && (
                          <a
                            href={`/telao/${evento.telao_token}`}
                            target="_blank"
                            rel="noreferrer"
                            className="btn-sutil"
                          >
                            <Icone nome="telao" />
                            <span className="hidden sm:inline">Telão</span>
                          </a>
                        )}
                        {/* A rota índice do evento abre a primeira tela do perfil. */}
                        <Link to={`/eventos/${evento.id}`} className="btn-neutro">
                          Abrir
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal titulo="Novo evento" aberto={criando} aoFechar={() => setCriando(false)}>
        <form onSubmit={criar} className="space-y-4">
          <div>
            <label className="rotulo" htmlFor="novo-nome">
              Nome do evento
            </label>
            <input
              id="novo-nome"
              className="campo"
              autoFocus
              required
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Confraternização de Fim de Ano 2026"
            />
          </div>
          <div>
            <label className="rotulo" htmlFor="nova-empresa">
              Nome da empresa
            </label>
            <input
              id="nova-empresa"
              className="campo"
              value={empresa}
              onChange={(e) => setEmpresa(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-neutro" onClick={() => setCriando(false)}>
              Cancelar
            </button>
            <button type="submit" className="btn-primario" disabled={salvando}>
              {salvando ? 'Criando...' : 'Criar evento'}
            </button>
          </div>
        </form>
      </Modal>
    </Casca>
  )
}
