import React from 'react'
import ReactDOM from 'react-dom/client'
import { Link, Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom'

import './index.css'
import { ProvedorAuth, destinoInicial, useAuth } from './auth'
import type { Permissao } from './auth'
import { Carregando } from './componentes/ui'
import Login from './paginas/Login'
import Eventos from './paginas/Eventos'
import PainelLayout, { AbaInicial } from './paginas/PainelLayout'
import Configuracao from './paginas/Configuracao'
import Participantes from './paginas/Participantes'
import Premios from './paginas/Premios'
import Blocos from './paginas/Blocos'
import Regras from './paginas/Regras'
import Sorteio from './paginas/Sorteio'
import Historico from './paginas/Historico'
import Relatorio from './paginas/Relatorio'
// Recepcao.tsx e a tela de entregas (hoje do Organizador); a nova Recepção
// (check-in e consulta do número) fica em RecepcaoAtendimento.tsx.
import Entregas from './paginas/Recepcao'
import RecepcaoAtendimento from './paginas/RecepcaoAtendimento'
import Credenciamento from './paginas/Credenciamento'
import Usuarios from './paginas/Usuarios'
import MinhaArea from './paginas/MinhaArea'
import TrocarSenha from './paginas/TrocarSenha'
import Telao from './paginas/Telao'
import Autocadastro from './paginas/Autocadastro'
import VisaoGeral from './paginas/VisaoGeral'

/**
 * Guarda de navegação. Não é a proteção do sistema (o backend recusa toda
 * chamada sem permissão); serve para mandar cada perfil para a tela certa.
 */
function Protegida({ permissao, children }: { permissao?: Permissao; children: React.ReactNode }) {
  const { usuario, carregando, pode } = useAuth()
  if (carregando) return <Carregando texto="Verificando sessão..." />
  if (!usuario) return <Navigate to="/login" replace />
  if (usuario.deve_trocar_senha) return <Navigate to="/trocar-senha" replace />
  if (permissao && !pode(permissao)) return <SemAcesso />
  return <>{children}</>
}

function SemAcesso() {
  const { usuario, sair } = useAuth()
  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <div className="cartao max-w-sm p-6 text-center">
        <h1 className="text-lg font-semibold text-slate-900">Acesso restrito</h1>
        <p className="mt-2 text-sm text-slate-600">Seu perfil não tem acesso a esta área.</p>
        <div className="mt-4 flex justify-center gap-2">
          {usuario && (
            <Link to={destinoInicial(usuario)} className="btn-primario">
              Ir para minha área
            </Link>
          )}
          <button type="button" className="btn-neutro" onClick={sair}>
            Sair
          </button>
        </div>
      </div>
    </div>
  )
}

function Inicio() {
  const { usuario, carregando } = useAuth()
  if (carregando) return <Carregando texto="Verificando sessão..." />
  return <Navigate to={usuario ? destinoInicial(usuario) : '/login'} replace />
}

function App() {
  return (
    <Routes>
      {/* O telao e publico por token e nunca exige login. */}
      <Route path="/telao/:token" element={<Telao />} />
      {/* Cadastro pelo QR Code (Portal do Colaborador): público; matrícula, nascimento e
          5 dígitos do CPF conferidos com a planilha importada. */}
      <Route path="/evento/:eventId/cadastro" element={<Autocadastro />} />
      <Route path="/cadastro" element={<Autocadastro />} />
      <Route path="/cadastro/:eventId" element={<Autocadastro />} />
      {/* Recepção: check-in e consulta do número, sem login, em qualquer aparelho. */}
      <Route path="/recepcao" element={<RecepcaoAtendimento />} />
      <Route path="/login" element={<Login />} />
      <Route path="/trocar-senha" element={<TrocarSenha />} />
      <Route
        path="/minha-area"
        element={
          <Protegida permissao="acessar_area_pessoal">
            <MinhaArea />
          </Protegida>
        }
      />
      <Route
        path="/usuarios"
        element={
          <Protegida permissao="gerenciar_usuarios">
            <Usuarios />
          </Protegida>
        }
      />
      <Route
        path="/eventos"
        element={
          <Protegida permissao="visualizar_evento">
            <Eventos />
          </Protegida>
        }
      />
      <Route
        path="/eventos/:eventId"
        element={
          <Protegida permissao="visualizar_evento">
            <PainelLayout />
          </Protegida>
        }
      >
        <Route index element={<AbaInicial />} />
        <Route
          path="visao-geral"
          element={<Protegida permissao="consultar_relatorios"><VisaoGeral /></Protegida>}
        />
        <Route path="sorteio" element={<Protegida permissao="controlar_sorteio"><Sorteio /></Protegida>} />
        <Route path="blocos" element={<Protegida permissao="configurar_blocos"><Blocos /></Protegida>} />
        <Route path="entregas" element={<Protegida permissao="pesquisar_colaboradores"><Entregas /></Protegida>} />
        <Route
          path="credenciamento"
          element={<Protegida permissao="acompanhar_credenciamento"><Credenciamento /></Protegida>}
        />
        <Route
          path="participantes"
          element={<Protegida permissao="gerenciar_participantes"><Participantes /></Protegida>}
        />
        <Route path="premios" element={<Protegida permissao="cadastrar_premios"><Premios /></Protegida>} />
        <Route path="regras" element={<Protegida permissao="definir_regras"><Regras /></Protegida>} />
        <Route path="historico" element={<Protegida permissao="consultar_resultados"><Historico /></Protegida>} />
        <Route path="relatorio" element={<Protegida permissao="consultar_relatorios"><Relatorio /></Protegida>} />
        <Route
          path="configuracao"
          element={<Protegida permissao="configurar_evento"><Configuracao /></Protegida>}
        />
      </Route>
      <Route path="*" element={<Inicio />} />
    </Routes>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ProvedorAuth>
      <Router>
        <App />
      </Router>
    </ProvedorAuth>
  </React.StrictMode>,
)
