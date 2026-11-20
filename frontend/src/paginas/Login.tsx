import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { destinoInicial, useAuth } from '../auth'
import Icone from '../componentes/Icone'
import {
  BoasVindasMallory,
  CabecalhoMallory,
  CartaoAcao,
  MolduraCartao,
  RodapeMallory,
  TopoCartao,
} from '../componentes/Mallory'
import { Aviso } from '../componentes/ui'

/**
 * Tela inicial, na identidade Mallory: Recepção (sem senha, qualquer aparelho)
 * e o acesso da equipe com usuário e senha.
 */
export default function Login() {
  const { entrar, usuario } = useAuth()
  const navegar = useNavigate()
  const [login, setLogin] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  if (usuario) return <Navigate to={destinoInicial(usuario)} replace />

  async function enviar(e: React.FormEvent) {
    e.preventDefault()
    setErro('')
    setEnviando(true)
    try {
      const entrou = await entrar(login.trim(), senha)
      navegar(destinoInicial(entrou), { replace: true })
    } catch (erroLogin) {
      setErro(erroLogin instanceof Error ? erroLogin.message : 'Não foi possível entrar')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex min-h-full flex-col bg-mallory-fundo text-mallory-preto">
      <CabecalhoMallory secao="Sorteios" icone="sorteio" />

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <BoasVindasMallory prefixo="Bem-vindo aos Sorteios" subtitulo="Escolha como deseja acessar o sistema." />

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          {/* Recepção: sem senha, em qualquer aparelho. */}
          <CartaoAcao
            variante="destaque"
            icone="cracha"
            titulo="Recepção"
            descricao="Check-in e consulta do número do sorteio. Não precisa de senha."
            acao="Acessar Recepção"
            para="/recepcao"
          >
            <ul className="space-y-3 text-base text-white">
              {[
                'Confirmar a presença pela matrícula',
                'Consultar o número do sorteio pelo nome ou matrícula',
                'Ver se o colaborador já foi sorteado e se retirou o prêmio',
              ].map((item) => (
                <li key={item} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/20">
                    <Icone nome="check" className="h-4 w-4" />
                  </span>
                  {item}
                </li>
              ))}
            </ul>
          </CartaoAcao>

          <MolduraCartao destaque={false}>
            <TopoCartao
              destaque={false}
              icone="senha"
              titulo="Equipe do evento"
              descricao="Organizador, sorteador, administrador e colaborador já cadastrado."
            />
            <p className="relative mt-5 flex gap-2 rounded-lg border border-mallory-borda bg-mallory-claro px-3 py-2 text-sm text-mallory-preto">
              <Icone nome="info" className="mt-0.5 h-4 w-4 shrink-0 text-mallory-acao" />
              <span>
                <strong>Colaborador:</strong> no usuário, digite sua matrícula; na senha, os{' '}
                <strong>5 primeiros dígitos do seu CPF</strong>.
              </span>
            </p>
            <form onSubmit={enviar} className="relative mt-4 space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-semibold" htmlFor="usuario">
                  Usuário
                </label>
                <input
                  id="usuario"
                  className="rec-campo h-12 text-base"
                  autoComplete="username"
                  value={login}
                  onChange={(e) => setLogin(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-semibold" htmlFor="senha">
                  Senha
                </label>
                <input
                  id="senha"
                  type="password"
                  className="rec-campo h-12 text-base"
                  autoComplete="current-password"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  required
                />
              </div>

              {erro && <Aviso tipo="erro">{erro}</Aviso>}

              <button type="submit" className="rec-btn-primario w-full" disabled={enviando}>
                {enviando ? 'Entrando...' : 'Entrar'}
                {!enviando && <Icone nome="seta" className="h-5 w-5" />}
              </button>
            </form>
            <p className="relative mt-5 text-sm text-mallory-texto">
              Primeiro acesso?{' '}
              <Link
                to="/cadastro"
                className="rec-foco rounded font-semibold text-mallory-acao underline-offset-2 hover:underline"
              >
                Faça seu cadastro
              </Link>
            </p>
          </MolduraCartao>
        </div>
      </main>

      <RodapeMallory secao="Acesso" />
    </div>
  )
}
