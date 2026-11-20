import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { enviarBlob, lerBlob, requisitar } from '../api'
import { useAuth } from '../auth'
import CapturaFoto, { type FotoPronta } from '../componentes/CapturaFoto'
import Icone, { type NomeIcone } from '../componentes/Icone'
import { CabecalhoMallory, CLASSE_BOTAO_CABECALHO, RodapeMallory } from '../componentes/Mallory'
import { Aviso, Carregando, ImagemPremio } from '../componentes/ui'
import {
  ativarManifestoPortal,
  ativarPush,
  desativarPush,
  ehIos,
  inscricaoAtual,
  suportePush,
} from '../portalPwa'
import type {
  MinhaArea as MinhaAreaTipo,
  MinhaParticipacao,
  Notificacao,
  PushStatus,
  SituacaoResultado,
} from '../types'
import { useCanalPrivado } from '../useCanalPrivado'
import { AvisoSenha, BilheteSorte, CartaoPessoa, SituacaoCheckin } from './Autocadastro'

type Aba = 'cartao' | 'premios' | 'notificacoes' | 'perfil'
const ABAS: { id: Aba; rotulo: string; icone: NomeIcone }[] = [
  { id: 'cartao', rotulo: 'Meu Cartão', icone: 'bilhete' },
  { id: 'premios', rotulo: 'Meus Prêmios', icone: 'premios' },
  { id: 'notificacoes', rotulo: 'Notificações', icone: 'sino' },
  { id: 'perfil', rotulo: 'Meu Perfil', icone: 'pessoa' },
]

function quando(data: string): string {
  return new Date(`${data}Z`).toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const SITUACAO: Record<SituacaoResultado, { texto: string; classe: string }> = {
  aguardando_retirada: { texto: 'Aguardando retirada', classe: 'bg-amber-50 text-amber-800' },
  entregue: { texto: 'Retirado', classe: 'bg-emerald-50 text-emerald-700' },
  anulado: { texto: 'Anulado', classe: 'bg-rose-50 text-rose-700' },
}

function EtiquetaSituacao({ situacao }: { situacao: SituacaoResultado }) {
  const item = SITUACAO[situacao]
  return <span className={`etiqueta ${item.classe}`}>{item.texto}</span>
}

function mensagem(e: unknown, padrao: string): string {
  return e instanceof Error ? e.message : padrao
}

/** Portal do Colaborador: Meu Cartão da Sorte, prêmios, notificações e perfil. */
export default function MinhaArea() {
  const { usuario, sair } = useAuth()
  const [busca, setBusca] = useSearchParams()
  const [dados, setDados] = useState<MinhaAreaTipo | null>(null)
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([])
  const [erro, setErro] = useState('')
  const [eventoId, setEventoId] = useState<number | null>(null)
  const [alerta, setAlerta] = useState<Notificacao | null>(null)
  const idsConhecidos = useRef<Set<number> | null>(null)

  const abaUrl = busca.get('aba') as Aba | null
  const aba: Aba = ABAS.some((a) => a.id === abaUrl) ? (abaUrl as Aba) : 'cartao'
  const irPara = (proxima: Aba) => setBusca(proxima === 'cartao' ? {} : { aba: proxima }, { replace: true })

  useEffect(() => {
    ativarManifestoPortal()
  }, [])

  const carregar = useCallback(async () => {
    try {
      const [area, lista] = await Promise.all([
        requisitar<MinhaAreaTipo>('/api/minha-area'),
        requisitar<Notificacao[]>('/api/minha-area/notificacoes'),
      ])
      setDados(area)
      setNotificacoes(lista)
      setErro('')
      // Alerta de premiação: só para avisos que chegaram com o portal aberto.
      const conhecidos = idsConhecidos.current
      if (conhecidos) {
        const nova = lista.find((n) => !conhecidos.has(n.id) && n.tipo === 'PREMIO_GANHO')
        if (nova) setAlerta(nova)
      }
      idsConhecidos.current = new Set(lista.map((n) => n.id))
    } catch (e) {
      setErro(mensagem(e, 'Falha ao carregar seu cartão'))
    }
  }, [])

  useEffect(() => {
    void carregar()
  }, [carregar])

  // Tempo real: o servidor só avisa "mudou"; os dados vêm da API autenticada.
  const canal = useCanalPrivado(() => void carregar())

  // Push recebido com o portal aberto (service worker avisa a página).
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return
    const ouvir = (evento: MessageEvent) => {
      if (evento.data?.tipo === 'push_recebido') void carregar()
    }
    navigator.serviceWorker.addEventListener('message', ouvir)
    return () => navigator.serviceWorker.removeEventListener('message', ouvir)
  }, [carregar])

  const participacoes = dados?.participacoes ?? []
  const atual = participacoes.find((p) => p.evento_id === eventoId) ?? participacoes[0] ?? null
  const naoLidas = dados?.notificacoes_nao_lidas ?? 0

  async function marcarLida(id: number) {
    await requisitar(`/api/minha-area/notificacoes/${id}/lida`, { metodo: 'POST' })
    await carregar()
  }

  async function marcarTodas() {
    await requisitar('/api/minha-area/notificacoes/lidas', { metodo: 'POST' })
    await carregar()
  }

  return (
    <div className="flex min-h-full flex-col bg-mallory-fundo text-mallory-preto">
      <CabecalhoMallory secao="Meu Cartão da Sorte" icone="bilhete" evento={atual?.evento_nome}>
        <button type="button" className={CLASSE_BOTAO_CABECALHO} onClick={sair}>
          <Icone nome="sair" className="h-4 w-4" />
          <span className="hidden sm:inline">Sair</span>
        </button>
      </CabecalhoMallory>

      <nav aria-label="Seções do portal" className="sticky top-0 z-30 border-b border-slate-200 bg-white">
        <ul className="mx-auto grid max-w-2xl grid-cols-4">
          {ABAS.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => irPara(a.id)}
                aria-current={aba === a.id ? 'page' : undefined}
                className={`rec-foco relative flex w-full flex-col items-center gap-1 px-1 py-2.5 text-[11px] font-semibold sm:flex-row sm:justify-center sm:text-sm ${
                  aba === a.id ? 'text-mallory-acao' : 'text-mallory-texto hover:text-mallory-preto'
                }`}
              >
                <span className="relative">
                  <Icone nome={a.icone} className="h-5 w-5" />
                  {a.id === 'notificacoes' && naoLidas > 0 && (
                    <span className="absolute -right-2.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-600 px-1 text-[10px] font-bold text-white">
                      {naoLidas > 99 ? '99+' : naoLidas}
                    </span>
                  )}
                </span>
                {a.rotulo}
                {aba === a.id && <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-mallory-laranja" />}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <main className="mx-auto w-full max-w-2xl flex-1 space-y-4 px-4 py-5">
        <p className="flex items-center gap-2 text-xs text-mallory-texto" aria-live="polite">
          <span className={`inline-block h-2 w-2 rounded-full ${canal === 'conectado' ? 'bg-emerald-500' : 'bg-amber-400'}`} />
          {canal === 'conectado' ? 'Atualização automática ativa' : 'Reconectando...'}
        </p>

        {alerta && (
          <button
            type="button"
            onClick={() => {
              setAlerta(null)
              irPara('premios')
            }}
            className="rec-foco flex w-full items-center gap-3 rounded-2xl bg-gradient-to-br from-[#DD5000] to-[#B84200] p-4 text-left text-white shadow-suave"
          >
            <Icone nome="premios" className="h-9 w-9 shrink-0" />
            <span>
              <span className="block text-lg font-bold">{alerta.titulo}</span>
              <span className="block text-sm">Toque para ver seu prêmio.</span>
            </span>
          </button>
        )}

        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {!dados && !erro && <Carregando />}

        {dados && participacoes.length === 0 && (
          <Aviso tipo="info">
            Sua conta ainda não está ligada a um cadastro de participante. Procure a Recepção do evento.
          </Aviso>
        )}

        {participacoes.length > 1 && (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Evento">
            {participacoes.map((p) => (
              <button
                key={p.evento_id}
                type="button"
                onClick={() => setEventoId(p.evento_id)}
                className={`rec-foco rounded-full border px-3 py-1.5 text-sm font-medium ${
                  atual?.evento_id === p.evento_id
                    ? 'border-mallory-laranja bg-mallory-claro text-mallory-preto'
                    : 'border-slate-300 bg-white text-mallory-texto'
                }`}
              >
                {p.evento_nome}
              </button>
            ))}
          </div>
        )}

        {atual && aba === 'cartao' && <MeuCartao p={atual} aoVerPremios={() => irPara('premios')} />}
        {atual && aba === 'premios' && <MeusPremios p={atual} />}
        {aba === 'notificacoes' && dados && (
          <Notificacoes lista={notificacoes} naoLidas={naoLidas} aoMarcar={marcarLida} aoMarcarTodas={marcarTodas} />
        )}
        {aba === 'perfil' && dados && (
          <MeuPerfil
            p={atual}
            login={usuario?.usuario ?? dados.usuario}
            colaborador={(usuario?.papel ?? 'COLABORADOR') === 'COLABORADOR'}
            aoAtualizar={carregar}
            aoSair={sair}
          />
        )}
      </main>

      <RodapeMallory secao="Portal do Colaborador" />
    </div>
  )
}

function Painel({ titulo, icone, children }: { titulo: string; icone: NomeIcone; children: React.ReactNode }) {
  return (
    <section className="rec-painel space-y-4 p-5">
      <h2 className="flex items-center gap-2 text-lg font-bold">
        <Icone nome={icone} className="h-5 w-5 text-mallory-escuro" />
        {titulo}
      </h2>
      {children}
    </section>
  )
}

function QrCartao({ eventoId }: { eventoId: number }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    let atual: string | null = null
    lerBlob(`/api/minha-area/${eventoId}/qrcode.png`)
      .then((blob) => {
        atual = URL.createObjectURL(blob)
        setUrl(atual)
      })
      .catch(() => setUrl(null))
    return () => {
      if (atual) URL.revokeObjectURL(atual)
    }
  }, [eventoId])
  if (!url) return null
  return (
    <div className="flex items-center gap-4 rounded-xl border border-slate-200 p-3">
      <img src={url} alt="QR Code do seu Cartão da Sorte" className="h-28 w-28 shrink-0 rounded-lg" />
      <p className="text-sm text-mallory-texto">
        Mostre este QR Code na <strong className="text-mallory-preto">retirada do prêmio</strong>: ele agiliza a busca. A
        equipe também confere você e a sua pulseira.
      </p>
    </div>
  )
}

function MeuCartao({ p, aoVerPremios }: { p: MinhaParticipacao; aoVerPremios: () => void }) {
  return (
    <Painel titulo="Meu Cartão da Sorte" icone="bilhete">
      <p className="-mt-2 text-sm text-mallory-texto">{p.evento_nome}</p>
      <BilheteSorte numero={p.numero_sorteio} matricula={p.matricula_da_sorte} sorteado={p.premios.length > 0} />
      {p.premios.length > 0 && <Parabens p={p} aoVerPremios={aoVerPremios} />}
      <CartaoPessoa cartao={p} />
      <SituacaoCheckin cartao={p} />
      {p.numero_sorteio !== null && <QrCartao eventoId={p.evento_id} />}
    </Painel>
  )
}

/** Aviso de premiação no cartão: só existe com resultado válido já revelado no telão. */
function Parabens({ p, aoVerPremios }: { p: MinhaParticipacao; aoVerPremios: () => void }) {
  const pendentes = p.premios.filter((premio) => !premio.entregue).length
  return (
    <section
      aria-live="polite"
      className="overflow-hidden rounded-2xl border-2 border-[#E2B13C] bg-gradient-to-br from-[#FFF8DC] via-white to-[#FFF1C2]"
    >
      <div className="flex items-center gap-2 bg-gradient-to-r from-[#B07D0A] to-[#E2A91F] px-4 py-2.5 text-white">
        <Icone nome="premios" className="h-5 w-5" />
        <p className="text-lg font-extrabold">Parabéns! Você foi sorteado!</p>
      </div>
      <ul className="divide-y divide-[#F1DFA6]">
        {p.premios.map((premio) => (
          <li key={premio.sorteio_id} className="flex items-center gap-3 p-3">
            <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl border border-[#F1DFA6] bg-white">
              <ImagemPremio url={premio.premio_imagem_url} nome={premio.premio_nome} className="h-full w-full text-slate-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#8F5D00]">Seu prêmio</p>
              <p className="text-lg font-bold leading-snug text-mallory-preto">{premio.premio_nome}</p>
              <div className="mt-1">
                <EtiquetaSituacao situacao={premio.entregue ? 'entregue' : 'aguardando_retirada'} />
              </div>
            </div>
          </li>
        ))}
      </ul>
      <div className="space-y-2 border-t border-[#F1DFA6] p-3">
        {pendentes > 0 && (
          <p className="text-sm text-mallory-texto">
            Retire na Recepção apresentando {p.pulseira ? <>a pulseira <strong>{p.pulseira}</strong></> : 'sua pulseira'} e
            o QR Code abaixo.
          </p>
        )}
        <button type="button" className="rec-btn-contorno h-11 w-full" onClick={aoVerPremios}>
          <Icone nome="premios" className="h-5 w-5" />
          Ver meus prêmios
        </button>
      </div>
    </section>
  )
}

function MeusPremios({ p }: { p: MinhaParticipacao }) {
  return (
    <Painel titulo="Meus Prêmios" icone="premios">
      {p.premios.length === 0 ? (
        <p className="text-base text-mallory-texto">Nenhum prêmio por enquanto. Boa sorte!</p>
      ) : (
        <ul className="space-y-3">
          {p.premios.map((premio) => (
            <li key={premio.sorteio_id} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3">
              <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-mallory-fundo">
                <ImagemPremio url={premio.premio_imagem_url} nome={premio.premio_nome} className="h-full w-full text-slate-400" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold leading-snug">{premio.premio_nome}</p>
                <p className="text-xs text-mallory-texto">
                  {premio.bloco_numero ? `Bloco ${String(premio.bloco_numero).padStart(2, '0')} · ` : ''}
                  Rodada {premio.rodada}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-mallory-texto">
                  <EtiquetaSituacao situacao={premio.entregue ? 'entregue' : 'aguardando_retirada'} />
                  {premio.entregue && premio.entregue_em && <span>em {quando(premio.entregue_em)}</span>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {p.premios.some((premio) => !premio.entregue) && (
        <p className="rounded-lg bg-mallory-claro px-3 py-2 text-sm">
          Retire seu prêmio na Recepção apresentando {p.pulseira ? <>a pulseira <strong>{p.pulseira}</strong></> : 'sua pulseira'}.
        </p>
      )}
    </Painel>
  )
}

function Notificacoes({
  lista,
  naoLidas,
  aoMarcar,
  aoMarcarTodas,
}: {
  lista: Notificacao[]
  naoLidas: number
  aoMarcar: (id: number) => Promise<void>
  aoMarcarTodas: () => Promise<void>
}) {
  return (
    <Painel titulo="Notificações" icone="sino">
      {lista.length === 0 ? (
        <p className="text-base text-mallory-texto">Nenhuma notificação por enquanto.</p>
      ) : (
        <>
          {naoLidas > 0 && (
            <div className="flex justify-end">
              <button type="button" className="rec-foco rounded text-sm font-semibold text-mallory-acao hover:underline" onClick={() => void aoMarcarTodas()}>
                Marcar todas como lidas
              </button>
            </div>
          )}
          <ul className="space-y-3">
            {lista.map((n) => (
              <li key={n.id} className={`rounded-xl border p-3 ${n.lida ? 'border-slate-200 bg-white' : 'border-mallory-borda bg-mallory-claro'}`}>
                <div className="flex gap-3">
                  <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-white">
                    <ImagemPremio url={n.premio_imagem_url} nome={n.premio_nome ?? 'prêmio'} className="h-full w-full text-slate-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold leading-snug">{n.titulo}</p>
                    <p className="mt-1 whitespace-pre-line text-sm text-mallory-texto">{n.mensagem}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-mallory-texto">
                      {n.situacao && <EtiquetaSituacao situacao={n.situacao} />}
                      <span>{quando(n.criada_em)}</span>
                      {!n.lida && (
                        <button type="button" className="ml-auto font-semibold text-mallory-acao hover:underline" onClick={() => void aoMarcar(n.id)}>
                          Marcar como lida
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Painel>
  )
}

function MeuPerfil({
  p,
  login,
  colaborador,
  aoAtualizar,
  aoSair,
}: {
  p: MinhaParticipacao | null
  login: string
  /** Conta do portal (senha = 5 dígitos do CPF); a equipe tem senha própria. */
  colaborador: boolean
  aoAtualizar: () => Promise<void>
  aoSair: () => void
}) {
  const [foto, setFoto] = useState<FotoPronta | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState('')
  const [ok, setOk] = useState('')

  async function salvarFoto() {
    if (!p || !foto) return
    setSalvando(true)
    setErro('')
    setOk('')
    try {
      await enviarBlob(`/api/minha-area/${p.evento_id}/foto`, foto.conteudo, foto.nome)
      URL.revokeObjectURL(foto.url)
      setFoto(null)
      setOk('Foto atualizada.')
      await aoAtualizar()
    } catch (e) {
      setErro(mensagem(e, 'Não foi possível salvar a foto'))
    } finally {
      setSalvando(false)
    }
  }

  async function removerFoto() {
    if (!p || !confirm('Remover sua foto?')) return
    setSalvando(true)
    setErro('')
    setOk('')
    try {
      await requisitar(`/api/minha-area/${p.evento_id}/foto`, { metodo: 'DELETE' })
      setOk('Foto removida.')
      await aoAtualizar()
    } catch (e) {
      setErro(mensagem(e, 'Não foi possível remover a foto'))
    } finally {
      setSalvando(false)
    }
  }

  return (
    <>
      {p && (
        <Painel titulo="Minha foto" icone="camera">
          {erro && <Aviso tipo="erro">{erro}</Aviso>}
          {ok && <Aviso tipo="sucesso">{ok}</Aviso>}
          {p.foto_url && !foto && (
            <div className="flex items-center gap-3">
              <img src={p.foto_url} alt="Sua foto atual" className="h-20 w-20 rounded-xl object-cover" />
              <button type="button" className="rec-btn-neutro" disabled={salvando} onClick={() => void removerFoto()}>
                <Icone nome="excluir" className="h-4 w-4" />
                Remover foto
              </button>
            </div>
          )}
          <CapturaFoto foto={foto} aoMudar={setFoto} />
          {foto && (
            <button type="button" className="rec-btn-primario w-full" disabled={salvando} onClick={() => void salvarFoto()}>
              {salvando ? 'Salvando...' : 'Salvar nova foto'}
            </button>
          )}
          <p className="text-xs text-mallory-texto">
            A foto é opcional e ajuda a Recepção a identificar você. Matrícula, CPF e número da sorte não podem ser
            alterados por aqui.
          </p>
        </Painel>
      )}

      <Painel titulo="Notificações no celular" icone="celular">
        <ControlePush />
      </Painel>

      <Painel titulo="Acesso" icone="senha">
        {colaborador ? (
          <>
            <AvisoSenha login={login} />
            <p className="text-xs text-mallory-texto">Se você trocar a senha abaixo, passa a entrar com a senha nova.</p>
          </>
        ) : (
          <p className="text-sm text-mallory-texto">
            Você entra com o usuário <strong className="font-mono text-mallory-preto">{login}</strong> e a sua senha da
            equipe.
          </p>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Link to="/trocar-senha" className="rec-btn-neutro">
            <Icone nome="senha" className="h-4 w-4" />
            Trocar senha
          </Link>
          <button type="button" className="rec-btn-contorno" onClick={aoSair}>
            <Icone nome="sair" className="h-4 w-4" />
            Encerrar sessão
          </button>
        </div>
      </Painel>
    </>
  )
}

function ControlePush() {
  const [status, setStatus] = useState<PushStatus | null>(null)
  const [inscrito, setInscrito] = useState(false)
  const [ocupado, setOcupado] = useState(false)
  const [erro, setErro] = useState('')
  const suporte = suportePush()

  const atualizar = useCallback(async () => {
    try {
      setStatus(await requisitar<PushStatus>('/api/minha-area/push'))
      setInscrito(!!(await inscricaoAtual()))
    } catch (e) {
      setErro(mensagem(e, 'Falha ao consultar as notificações'))
    }
  }, [])

  useEffect(() => {
    void atualizar()
  }, [atualizar])

  async function alternar() {
    if (!status) return
    setOcupado(true)
    setErro('')
    try {
      if (inscrito) await desativarPush()
      else await ativarPush(status)
      await atualizar()
    } catch (e) {
      setErro(mensagem(e, 'Não foi possível alterar as notificações'))
    } finally {
      setOcupado(false)
    }
  }

  const avisoPadrao = (
    <p className="text-xs text-mallory-texto">
      Com ou sem notificações no celular, seus avisos ficam sempre aqui no portal. A entrega no celular depende do
      aparelho, do navegador e da internet, e não é garantida.
    </p>
  )

  if (!status) return erro ? <Aviso tipo="erro">{erro}</Aviso> : <Carregando />

  if (!status.disponivel || suporte.ok !== true) {
    let texto = status.motivo ?? 'As notificações no celular não estão disponíveis.'
    if (status.disponivel && suporte.ok === false) {
      texto = {
        sem_https: 'Este endereço não usa HTTPS, então o navegador não permite notificações no celular.',
        ios_instalar:
          'No iPhone, as notificações funcionam com o portal instalado: toque em Compartilhar e depois em “Adicionar à Tela de Início”. Abra o portal pelo ícone e volte aqui.',
        navegador: 'Este navegador não oferece notificações push. Tente o Chrome (Android) ou o Safari (iPhone, com o portal instalado).',
        negado: 'As notificações foram bloqueadas para este site. Libere nas configurações do navegador e volte aqui.',
      }[suporte.motivo]
    }
    return (
      <div className="space-y-2">
        <p className="text-sm">{texto}</p>
        {ehIos() && suporte.ok === false && suporte.motivo === 'ios_instalar' && (
          <p className="text-xs text-mallory-texto">Requer iOS 16.4 ou mais recente.</p>
        )}
        {avisoPadrao}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <p className="text-sm">
        {inscrito
          ? 'Ativadas neste aparelho. Você será avisado quando for sorteado.'
          : 'Receba um aviso no celular quando você for sorteado.'}
      </p>
      <button type="button" className={inscrito ? 'rec-btn-neutro w-full' : 'rec-btn-primario w-full'} disabled={ocupado} onClick={() => void alternar()}>
        <Icone nome="sino" className="h-5 w-5" />
        {ocupado ? 'Aguarde...' : inscrito ? 'Desativar notificações' : 'Ativar notificações'}
      </button>
      {avisoPadrao}
    </div>
  )
}
