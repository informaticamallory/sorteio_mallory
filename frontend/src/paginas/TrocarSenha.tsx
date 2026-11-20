import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { requisitar } from '../api'
import { destinoInicial, useAuth } from '../auth'
import { Aviso, Carregando } from '../componentes/ui'
import type { Usuario } from '../types'

// Mesma política do backend (security.problema_na_senha), para avisar antes de enviar.
function problemaNaSenha(senha: string, usuario: string): string {
  if (senha.length < 8) return 'Use pelo menos 8 caracteres.'
  if (!/[a-zA-Z]/.test(senha) || !/\d/.test(senha)) return 'Use letras e números.'
  if (usuario && senha.toLowerCase().includes(usuario.toLowerCase()))
    return 'A senha não pode conter o nome de usuário.'
  return ''
}

export default function TrocarSenha() {
  const { usuario, carregando, adotarSessao, sair } = useAuth()
  const navegar = useNavigate()
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [confirmacao, setConfirmacao] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  if (carregando) return <Carregando texto="Verificando sessão..." />
  if (!usuario) return <Navigate to="/login" replace />

  const obrigatoria = usuario.deve_trocar_senha === true

  async function enviar(e: React.FormEvent) {
    e.preventDefault()
    if (!usuario) return
    const problema = problemaNaSenha(nova, usuario.usuario)
    if (problema) return setErro(problema)
    if (nova !== confirmacao) return setErro('A confirmação não confere com a nova senha.')
    setEnviando(true)
    setErro('')
    try {
      const resposta = await requisitar<{ access_token: string; usuario: Usuario }>(
        '/api/auth/trocar-senha',
        { metodo: 'POST', corpo: { senha_atual: atual, senha_nova: nova } },
      )
      adotarSessao(resposta.access_token, resposta.usuario)
      navegar(destinoInicial(resposta.usuario), { replace: true })
    } catch (erroTroca) {
      setErro(erroTroca instanceof Error ? erroTroca.message : 'Não foi possível trocar a senha')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-fundo p-4">
      <form onSubmit={enviar} className="cartao w-full max-w-sm space-y-4 p-6">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">
            {obrigatoria ? 'Crie sua senha' : 'Trocar senha'}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {obrigatoria
              ? 'Você entrou com uma senha temporária. Defina uma senha pessoal para continuar.'
              : 'Ao trocar a senha, as sessões abertas em outros aparelhos são encerradas.'}
          </p>
        </div>
        <div>
          <label className="rotulo" htmlFor="senha-atual">
            {obrigatoria ? 'Senha temporária' : 'Senha atual'}
          </label>
          <input
            id="senha-atual"
            type="password"
            className="campo"
            autoComplete="current-password"
            required
            value={atual}
            onChange={(e) => setAtual(e.target.value)}
          />
        </div>
        <div>
          <label className="rotulo" htmlFor="senha-nova">
            Nova senha
          </label>
          <input
            id="senha-nova"
            type="password"
            className="campo"
            autoComplete="new-password"
            required
            value={nova}
            onChange={(e) => setNova(e.target.value)}
            aria-describedby="regra-senha"
          />
          <p id="regra-senha" className="mt-1 text-xs text-slate-500">
            Pelo menos 8 caracteres, com letras e números.
          </p>
        </div>
        <div>
          <label className="rotulo" htmlFor="senha-confirmacao">
            Confirme a nova senha
          </label>
          <input
            id="senha-confirmacao"
            type="password"
            className="campo"
            autoComplete="new-password"
            required
            value={confirmacao}
            onChange={(e) => setConfirmacao(e.target.value)}
          />
        </div>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <button type="submit" className="btn-primario w-full" disabled={enviando}>
          {enviando ? 'Salvando...' : 'Salvar nova senha'}
        </button>
        <div className="flex justify-between text-sm">
          {obrigatoria ? (
            <span />
          ) : (
            <Link to={destinoInicial(usuario)} className="text-slate-500 underline">
              Voltar
            </Link>
          )}
          <button type="button" className="text-slate-500 underline" onClick={sair}>
            Sair
          </button>
        </div>
      </form>
    </div>
  )
}
