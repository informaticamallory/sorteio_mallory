import { useCallback, useEffect, useState } from 'react'
import { requisitar } from '../api'
import { ROTULO_PAPEL, useAuth } from '../auth'
import Casca from '../componentes/Casca'
import { Aviso, Carregando, Modal, Vazio } from '../componentes/ui'
import type { Papel, RegistroAuditoria, SenhaTemporaria, UsuarioAdmin } from '../types'

const PAPEIS_EQUIPE: Papel[] = ['ADMIN', 'ORGANIZADOR', 'SORTEIO', 'RECEPCAO', 'ENTREGAS']

// Resumo do que cada perfil pode fazer (quem decide é o backend: app/permissoes.py).
const DESCRICAO_PAPEL: Partial<Record<Papel, string>> = {
  ADMIN: 'Tudo: usuários, criação de eventos, anulação de resultados e auditoria.',
  ORGANIZADOR:
    'Configura o evento, participantes, prêmios, blocos, regras, credenciamento, entregas (inclusive desfazer) e relatórios. Sorteia só se autorizado.',
  SORTEIO: 'Opera os sorteios: blocos, telão e resultados.',
  RECEPCAO: 'Check-in, credenciamento (confirmar e desfazer presença) e Central de Entregas (localizar e confirmar; não desfaz).',
  ENTREGAS: 'Central de Entregas: localizar ganhadores, confirmar entregas e ver o histórico. Não desfaz entregas.',
}

const SETORES_SUGERIDOS = ['RH', 'TI', 'Comunicação', 'Financeiro', 'Operações']

function CamposSetorEAutorizacao({
  papel,
  setor,
  podeSortear,
  aoMudarSetor,
  aoMudarPodeSortear,
  prefixo,
}: {
  papel: Papel
  setor: string
  podeSortear: boolean
  aoMudarSetor: (v: string) => void
  aoMudarPodeSortear: (v: boolean) => void
  prefixo: string
}) {
  return (
    <>
      {DESCRICAO_PAPEL[papel] && <p className="-mt-2 text-xs text-slate-500">{DESCRICAO_PAPEL[papel]}</p>}
      <div>
        <label className="rotulo" htmlFor={`${prefixo}-setor`}>
          Setor (opcional)
        </label>
        <input
          id={`${prefixo}-setor`}
          className="campo"
          maxLength={80}
          list={`${prefixo}-setores`}
          placeholder="Ex.: RH, TI"
          value={setor}
          onChange={(e) => aoMudarSetor(e.target.value)}
        />
        <datalist id={`${prefixo}-setores`}>
          {SETORES_SUGERIDOS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
        <p className="mt-1 text-xs text-slate-500">Só identifica a área da pessoa. Quem define o acesso é o perfil.</p>
      </div>
      {papel === 'ORGANIZADOR' && (
        <label className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-2">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 accent-marca-600"
            checked={podeSortear}
            onChange={(e) => aoMudarPodeSortear(e.target.checked)}
          />
          <span className="text-sm text-slate-700">
            <strong>Pode operar sorteios</strong>
            <span className="block text-xs text-slate-500">Libera iniciar blocos, sortear e controlar o telão.</span>
          </span>
        </label>
      )}
    </>
  )
}

function quando(data: string | null): string {
  if (!data) return 'nunca'
  return new Date(`${data}Z`).toLocaleString('pt-BR')
}

function bloqueado(u: UsuarioAdmin): boolean {
  return u.bloqueado_ate !== null && new Date(`${u.bloqueado_ate}Z`) > new Date()
}

export default function Usuarios() {
  const { usuario: eu } = useAuth()
  const [lista, setLista] = useState<UsuarioAdmin[] | null>(null)
  const [busca, setBusca] = useState('')
  const [papel, setPapel] = useState('')
  const [situacao, setSituacao] = useState('')
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')

  const [criando, setCriando] = useState(false)
  const [editando, setEditando] = useState<UsuarioAdmin | null>(null)
  const [senhaGerada, setSenhaGerada] = useState<SenhaTemporaria | null>(null)
  const [confirmarReset, setConfirmarReset] = useState<UsuarioAdmin | null>(null)
  const [auditoria, setAuditoria] = useState<{ usuario: UsuarioAdmin; registros: RegistroAuditoria[] } | null>(null)
  const [confirmarExclusao, setConfirmarExclusao] = useState<UsuarioAdmin | null>(null)
  const [erroExclusao, setErroExclusao] = useState('')
  const [excluindo, setExcluindo] = useState(false)

  async function excluir(alvo: UsuarioAdmin) {
    setExcluindo(true)
    setErroExclusao('')
    try {
      await requisitar(`/api/usuarios/${alvo.id}`, { metodo: 'DELETE' })
      setConfirmarExclusao(null)
      setErro('')
      setAviso(`Conta de ${alvo.nome} excluída.`)
      await carregar()
    } catch (e) {
      setErroExclusao(e instanceof Error ? e.message : 'Falha ao excluir a conta')
    } finally {
      setExcluindo(false)
    }
  }

  const carregar = useCallback(async () => {
    const params = new URLSearchParams()
    if (busca.trim()) params.set('busca', busca.trim())
    if (papel) params.set('papel', papel)
    if (situacao) params.set('ativo', situacao === 'ativos' ? 'true' : 'false')
    try {
      setLista(await requisitar<UsuarioAdmin[]>(`/api/usuarios?${params.toString()}`))
      setErro('')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao carregar usuários')
    }
  }, [busca, papel, situacao])

  useEffect(() => {
    const espera = window.setTimeout(() => void carregar(), 300)
    return () => window.clearTimeout(espera)
  }, [carregar])

  async function acao(fn: () => Promise<unknown>, mensagem: string) {
    setErro('')
    setAviso('')
    try {
      await fn()
      setAviso(mensagem)
      await carregar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Operação não concluída')
    }
  }

  return (
    <Casca
      itens={[
        { para: '/eventos', rotulo: 'Eventos', icone: 'eventos', fim: true },
        { para: '/usuarios', rotulo: 'Usuários', icone: 'usuarios' },
      ]}
      titulo="Usuários e permissões"
      subtitulo="Contas da equipe do evento"
      acoes={
        <button type="button" className="btn-primario" onClick={() => setCriando(true)}>
          Novo usuário
        </button>
      }
    >
      <div className="space-y-4">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {aviso && <Aviso tipo="sucesso">{aviso}</Aviso>}

        <details className="cartao p-4 text-sm">
          <summary className="cursor-pointer font-semibold text-slate-900">O que cada perfil pode fazer</summary>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            {PAPEIS_EQUIPE.map((p) => (
              <div key={p} className="rounded-lg bg-slate-50 p-3">
                <dt className="font-semibold text-slate-900">{ROTULO_PAPEL[p]}</dt>
                <dd className="text-xs text-slate-600">{DESCRICAO_PAPEL[p]}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-slate-500">
            Perfil e setor são coisas diferentes: o perfil define o acesso; o setor (TI, RH...) só identifica a área.
          </p>
        </details>

        <div className="cartao grid gap-3 p-4 sm:grid-cols-3">
          <div>
            <label className="rotulo" htmlFor="u-busca">
              Buscar
            </label>
            <input
              id="u-busca"
              type="search"
              className="campo"
              placeholder="Nome ou usuário"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
          </div>
          <div>
            <label className="rotulo" htmlFor="u-papel">
              Perfil
            </label>
            <select id="u-papel" className="campo" value={papel} onChange={(e) => setPapel(e.target.value)}>
              <option value="">Todos</option>
              {(Object.keys(ROTULO_PAPEL) as Papel[]).map((p) => (
                <option key={p} value={p}>
                  {ROTULO_PAPEL[p]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="rotulo" htmlFor="u-situacao">
              Situação
            </label>
            <select
              id="u-situacao"
              className="campo"
              value={situacao}
              onChange={(e) => setSituacao(e.target.value)}
            >
              <option value="">Todas</option>
              <option value="ativos">Ativos</option>
              <option value="inativos">Inativos</option>
            </select>
          </div>
        </div>

        {lista === null ? (
          <Carregando />
        ) : lista.length === 0 ? (
          <Vazio titulo="Nenhum usuário encontrado" />
        ) : (
          <ul className="space-y-2">
            {lista.map((u) => (
              <li key={u.id} className={`cartao p-4 ${u.ativo ? '' : 'opacity-70'}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-slate-900">
                      {u.nome}
                      {u.id === eu?.id && <span className="ml-2 text-xs font-normal text-slate-500">(você)</span>}
                    </p>
                    <p className="font-mono text-xs text-slate-500">{u.usuario}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <span className="etiqueta bg-marca-50 text-marca-700">{ROTULO_PAPEL[u.papel]}</span>
                      {u.setor && <span className="etiqueta bg-slate-100 text-slate-700">Setor: {u.setor}</span>}
                      {u.pode_sortear && <span className="etiqueta bg-emerald-50 text-emerald-700">Pode sortear</span>}
                      {!u.ativo && <span className="etiqueta bg-slate-200 text-slate-700">Inativo</span>}
                      {bloqueado(u) && <span className="etiqueta bg-rose-100 text-rose-800">Bloqueado</span>}
                      {u.deve_trocar_senha && (
                        <span className="etiqueta bg-amber-100 text-amber-800">Senha temporária</span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-slate-500">Último acesso: {quando(u.ultimo_acesso_em)}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => setEditando(u)}>
                      Editar
                    </button>
                    <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => setConfirmarReset(u)}>
                      Redefinir senha
                    </button>
                    {bloqueado(u) && (
                      <button
                        type="button"
                        className="btn-neutro px-3 py-1.5"
                        onClick={() =>
                          void acao(
                            () => requisitar(`/api/usuarios/${u.id}/desbloquear`, { metodo: 'POST' }),
                            `${u.nome} desbloqueado.`,
                          )
                        }
                      >
                        Desbloquear
                      </button>
                    )}
                    {u.id !== eu?.id && (
                      <button
                        type="button"
                        className="btn-neutro px-3 py-1.5"
                        onClick={() =>
                          void acao(
                            () => requisitar(`/api/usuarios/${u.id}/encerrar-sessoes`, { metodo: 'POST' }),
                            `Sessões de ${u.nome} encerradas.`,
                          )
                        }
                      >
                        Encerrar sessões
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn-neutro px-3 py-1.5"
                      onClick={async () =>
                        setAuditoria({
                          usuario: u,
                          registros: await requisitar<RegistroAuditoria[]>(`/api/usuarios/${u.id}/auditoria`),
                        })
                      }
                    >
                      Auditoria
                    </button>
                    {u.id !== eu?.id && (
                      <button
                        type="button"
                        className="btn-neutro px-3 py-1.5 text-rose-700 hover:border-rose-300 hover:bg-rose-50"
                        onClick={() => {
                          setErroExclusao('')
                          setConfirmarExclusao(u)
                        }}
                      >
                        Excluir
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ModalNovo
        aberto={criando}
        aoFechar={() => setCriando(false)}
        aoCriar={async (resultado) => {
          setCriando(false)
          setSenhaGerada(resultado)
          await carregar()
        }}
      />

      <ModalEdicao
        alvo={editando}
        euMesmo={editando?.id === eu?.id}
        aoFechar={() => setEditando(null)}
        aoSalvar={async (mensagem, senha) => {
          setEditando(null)
          setAviso(mensagem)
          if (senha) setSenhaGerada(senha)
          await carregar()
        }}
      />

      <Modal titulo="Excluir usuário" aberto={confirmarExclusao !== null} aoFechar={() => setConfirmarExclusao(null)}>
        {confirmarExclusao && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              A conta <strong>{confirmarExclusao.nome}</strong> (
              <span className="font-mono">{confirmarExclusao.usuario}</span>) será excluída e não poderá mais
              entrar no sistema.
            </p>
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
              <li>
                Se a pessoa é participante, continua na lista do sorteio, só sem conta; pode se cadastrar de novo pelo
                QR Code.
              </li>
              <li>
                Contas que já realizaram sorteios, entregas, anulações ou outras ações de gestão não podem ser
                excluídas, para preservar o histórico. Nesse caso, desative a conta em <strong>Editar</strong>.
              </li>
              <li>A exclusão fica registrada na auditoria.</li>
            </ul>
            {erroExclusao && <Aviso tipo="erro">{erroExclusao}</Aviso>}
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-neutro" onClick={() => setConfirmarExclusao(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn-perigo"
                disabled={excluindo}
                onClick={() => void excluir(confirmarExclusao)}
              >
                {excluindo ? 'Excluindo...' : 'Excluir conta'}
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal titulo="Redefinir senha" aberto={confirmarReset !== null} aoFechar={() => setConfirmarReset(null)}>
        {confirmarReset && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              Será gerada uma senha temporária para <strong>{confirmarReset.nome}</strong>. A senha
              atual deixa de funcionar, as sessões abertas são encerradas e a pessoa precisará criar
              uma senha nova no próximo acesso.
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-neutro" onClick={() => setConfirmarReset(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn-perigo"
                onClick={async () => {
                  const alvo = confirmarReset
                  setConfirmarReset(null)
                  try {
                    setSenhaGerada(
                      await requisitar<SenhaTemporaria>(`/api/usuarios/${alvo.id}/redefinir-senha`, {
                        metodo: 'POST',
                      }),
                    )
                    await carregar()
                  } catch (e) {
                    setErro(e instanceof Error ? e.message : 'Falha ao redefinir a senha')
                  }
                }}
              >
                Gerar senha temporária
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal titulo="Senha temporária" aberto={senhaGerada !== null} aoFechar={() => setSenhaGerada(null)}>
        {senhaGerada && (
          <div className="space-y-4">
            <Aviso tipo="atencao">
              Esta senha aparece <strong>somente agora</strong>. Entregue-a pessoalmente a{' '}
              {senhaGerada.usuario.nome}; no primeiro acesso será obrigatório criar uma senha nova.
            </Aviso>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-500">Usuário</dt>
              <dd className="font-mono">{senhaGerada.usuario.usuario}</dd>
              <dt className="text-slate-500">Senha</dt>
              <dd className="select-all font-mono text-lg font-semibold tracking-wider">{senhaGerada.senha_temporaria}</dd>
            </dl>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="btn-neutro"
                onClick={() => void navigator.clipboard?.writeText(senhaGerada.senha_temporaria)}
              >
                Copiar senha
              </button>
              <button type="button" className="btn-primario" onClick={() => setSenhaGerada(null)}>
                Já anotei
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        titulo={auditoria ? `Auditoria — ${auditoria.usuario.nome}` : ''}
        aberto={auditoria !== null}
        aoFechar={() => setAuditoria(null)}
        largura="max-w-2xl"
      >
        {auditoria &&
          (auditoria.registros.length === 0 ? (
            <Vazio titulo="Nenhum registro" />
          ) : (
            <ul className="max-h-[60vh] space-y-1 overflow-y-auto text-xs">
              {auditoria.registros.map((r) => (
                <li key={r.id} className="flex flex-wrap gap-2 border-b border-slate-100 py-1.5">
                  <span className="font-mono text-slate-400">{quando(r.criado_em)}</span>
                  <span className="font-semibold text-slate-700">{r.acao}</span>
                  <span className="text-slate-500">por {r.usuario || '—'}</span>
                  <span className="w-full break-all font-mono text-slate-400">{JSON.stringify(r.detalhes)}</span>
                </li>
              ))}
            </ul>
          ))}
      </Modal>
    </Casca>
  )
}

function ModalNovo({
  aberto,
  aoFechar,
  aoCriar,
}: {
  aberto: boolean
  aoFechar: () => void
  aoCriar: (resultado: SenhaTemporaria) => Promise<void>
}) {
  const [usuario, setUsuario] = useState('')
  const [nome, setNome] = useState('')
  const [papel, setPapel] = useState<Papel>('SORTEIO')
  const [setor, setSetor] = useState('')
  const [podeSortear, setPodeSortear] = useState(false)
  const [erro, setErro] = useState('')

  useEffect(() => {
    if (aberto) {
      setUsuario('')
      setNome('')
      setPapel('SORTEIO')
      setSetor('')
      setPodeSortear(false)
      setErro('')
    }
  }, [aberto])

  async function enviar(e: React.FormEvent) {
    e.preventDefault()
    setErro('')
    try {
      await aoCriar(
        await requisitar<SenhaTemporaria>('/api/usuarios', {
          metodo: 'POST',
          corpo: {
            usuario: usuario.trim().toLowerCase(),
            nome: nome.trim(),
            papel,
            setor: setor.trim(),
            pode_sortear: papel === 'ORGANIZADOR' && podeSortear,
          },
        }),
      )
    } catch (erroCriar) {
      setErro(erroCriar instanceof Error ? erroCriar.message : 'Falha ao criar o usuário')
    }
  }

  return (
    <Modal titulo="Novo usuário da equipe" aberto={aberto} aoFechar={aoFechar}>
      <form onSubmit={enviar} className="space-y-4">
        <div>
          <label className="rotulo" htmlFor="n-nome">
            Nome
          </label>
          <input id="n-nome" className="campo" required autoFocus value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
        <div>
          <label className="rotulo" htmlFor="n-usuario">
            Usuário (login)
          </label>
          <input
            id="n-usuario"
            className="campo font-mono"
            required
            pattern="[a-z0-9._\-]{3,80}"
            title="3 a 80 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value.toLowerCase())}
            placeholder="maria.recepcao"
          />
        </div>
        <div>
          <label className="rotulo" htmlFor="n-papel">
            Perfil
          </label>
          <select id="n-papel" className="campo" value={papel} onChange={(e) => setPapel(e.target.value as Papel)}>
            {PAPEIS_EQUIPE.map((p) => (
              <option key={p} value={p}>
                {ROTULO_PAPEL[p]}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">
            Contas de colaborador são criadas pelo próprio colaborador, no cadastro pelo QR Code.
          </p>
        </div>
        <CamposSetorEAutorizacao
          prefixo="n"
          papel={papel}
          setor={setor}
          podeSortear={podeSortear}
          aoMudarSetor={setSetor}
          aoMudarPodeSortear={setPodeSortear}
        />
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn-primario">
            Criar e gerar senha temporária
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ModalEdicao({
  alvo,
  euMesmo,
  aoFechar,
  aoSalvar,
}: {
  alvo: UsuarioAdmin | null
  euMesmo: boolean
  aoFechar: () => void
  aoSalvar: (mensagem: string, senha?: SenhaTemporaria) => Promise<void>
}) {
  const [nome, setNome] = useState('')
  const [papel, setPapel] = useState<Papel>('SORTEIO')
  const [ativo, setAtivo] = useState(true)
  const [setor, setSetor] = useState('')
  const [podeSortear, setPodeSortear] = useState(false)
  const [erro, setErro] = useState('')

  useEffect(() => {
    if (alvo) {
      setNome(alvo.nome)
      setPapel(alvo.papel)
      setAtivo(alvo.ativo)
      setSetor(alvo.setor ?? '')
      setPodeSortear(alvo.pode_sortear)
      setErro('')
    }
  }, [alvo])

  if (!alvo) return null
  const colaborador = alvo.papel === 'COLABORADOR'

  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    if (!alvo) return
    const corpo: Record<string, unknown> = {}
    if (nome.trim() !== alvo.nome) corpo.nome = nome.trim()
    if (papel !== alvo.papel) corpo.papel = papel
    if (ativo !== alvo.ativo) corpo.ativo = ativo
    if (setor.trim() !== (alvo.setor ?? '')) corpo.setor = setor.trim()
    const sortear = papel === 'ORGANIZADOR' && podeSortear
    if (sortear !== alvo.pode_sortear && papel === 'ORGANIZADOR') corpo.pode_sortear = sortear
    try {
      const salvo = await requisitar<UsuarioAdmin & { senha_temporaria: string | null }>(`/api/usuarios/${alvo.id}`, {
        metodo: 'PATCH',
        corpo,
      })
      const { senha_temporaria, ...usuario } = salvo
      await aoSalvar(
        senha_temporaria
          ? `${nome} agora é ${ROTULO_PAPEL[salvo.papel]}. Entregue a senha temporária; ela será trocada no primeiro acesso.`
          : corpo.papel || corpo.ativo !== undefined || corpo.pode_sortear !== undefined
            ? `${nome} atualizado. As sessões abertas dessa conta foram encerradas.`
            : `${nome} atualizado.`,
        senha_temporaria ? { usuario, senha_temporaria } : undefined,
      )
    } catch (erroSalvar) {
      setErro(erroSalvar instanceof Error ? erroSalvar.message : 'Falha ao salvar')
    }
  }

  return (
    <Modal titulo="Editar usuário" aberto aoFechar={aoFechar}>
      <form onSubmit={salvar} className="space-y-4">
        <p className="font-mono text-sm text-slate-500">{alvo.usuario}</p>
        <div>
          <label className="rotulo" htmlFor="e-nome">
            Nome
          </label>
          <input id="e-nome" className="campo" required value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
        <div>
          <label className="rotulo" htmlFor="e-papel">
            Perfil
          </label>
          <select
            id="e-papel"
            className="campo"
            value={papel}
            disabled={euMesmo}
            onChange={(e) => setPapel(e.target.value as Papel)}
          >
            {(colaborador ? (['COLABORADOR', ...PAPEIS_EQUIPE] as Papel[]) : PAPEIS_EQUIPE).map((p) => (
              <option key={p} value={p}>
                {ROTULO_PAPEL[p]}
              </option>
            ))}
          </select>
          {euMesmo && <p className="mt-1 text-xs text-slate-500">Você não pode alterar o próprio perfil.</p>}
          {colaborador && papel !== 'COLABORADOR' && (
            <div className="mt-2">
              <Aviso tipo="atencao">
                Esta conta foi criada pelo cadastro do celular e usa os 5 primeiros dígitos do CPF como senha. Ao
                salvar, o sistema gera uma <strong>senha temporária</strong> (mostrada uma vez) e a pessoa cria uma senha
                forte no primeiro acesso. O login continua <span className="font-mono">{alvo.usuario}</span>, e o Cartão
                da Sorte, os prêmios e os avisos continuam com ela. Contas da equipe não voltam a ser Colaborador.
              </Aviso>
            </div>
          )}
        </div>
        {(!colaborador || papel !== 'COLABORADOR') && (
          <CamposSetorEAutorizacao
            prefixo="e"
            papel={papel}
            setor={setor}
            podeSortear={podeSortear}
            aoMudarSetor={setSetor}
            aoMudarPodeSortear={setPodeSortear}
          />
        )}
        <label className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2">
          <input
            type="checkbox"
            className="h-4 w-4 accent-marca-800"
            checked={ativo}
            disabled={euMesmo}
            onChange={(e) => setAtivo(e.target.checked)}
          />
          <span className="text-sm text-slate-700">Conta ativa</span>
        </label>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn-primario">
            Salvar
          </button>
        </div>
      </form>
    </Modal>
  )
}
