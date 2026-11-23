import { useEffect, useId, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ErroApi, enviarFormulario, requisitar } from '../api'
import { useAuth } from '../auth'
import CapturaFoto, { type FotoPronta } from '../componentes/CapturaFoto'
import { CabecalhoMallory, CLASSE_BOTAO_CABECALHO, FaixaDemo, RodapeMallory } from '../componentes/Mallory'
import Icone, { type NomeIcone } from '../componentes/Icone'
import { Aviso, Carregando } from '../componentes/ui'
import type { AutocadastroConcluido, CartaoSorte, EventoAutocadastro, Identificacao } from '../types'

type Passo = 'identificacao' | 'confirmacao' | 'pronto'

const ROTULO = 'mb-1.5 flex items-center gap-2 text-sm font-semibold text-mallory-preto'
const CAMPO = 'rec-campo h-12 text-base'

function mensagem(e: unknown): string {
  return e instanceof Error ? e.message : 'Não foi possível concluir. Tente novamente.'
}

function hojeIso(): string {
  const agora = new Date()
  return new Date(agora.getTime() - agora.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

/** Digitação da data: "15031990" -> "15/03/1990" (as barras entram sozinhas). */
export function mascararData(texto: string): string {
  const d = texto.replace(/\D/g, '').slice(0, 8)
  if (d.length <= 2) return d
  if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`
  return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`
}

/**
 * "dd/mm/aaaa" -> "aaaa-mm-dd" (formato que o servidor espera), ou null se a
 * data estiver incompleta, nao existir (31/02) ou estiver fora de 1900..hoje.
 */
export function dataParaIso(texto: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(texto)
  if (!m) return null
  const [, dia, mes, ano] = m
  const data = new Date(Date.UTC(Number(ano), Number(mes) - 1, Number(dia)))
  if (
    data.getUTCFullYear() !== Number(ano) ||
    data.getUTCMonth() !== Number(mes) - 1 ||
    data.getUTCDate() !== Number(dia)
  )
    return null
  const iso = `${ano}-${mes}-${dia}`
  return iso >= '1900-01-01' && iso <= hojeIso() ? iso : null
}

/**
 * Página pública do QR Code: o colaborador se cadastra pelo próprio celular.
 * /evento/:eventId/cadastro (QR Code), /cadastro/:eventId e /cadastro (lista).
 */
export default function Autocadastro() {
  const { eventId } = useParams()
  const [eventos, setEventos] = useState<EventoAutocadastro[] | null>(null)
  const [erroEventos, setErroEventos] = useState('')

  useEffect(() => {
    const carregar = eventId
      ? requisitar<EventoAutocadastro>(`/api/autocadastro/${eventId}`, { autenticado: false }).then((e) => [e])
      : requisitar<EventoAutocadastro[]>('/api/autocadastro/eventos', { autenticado: false })
    carregar
      .then(setEventos)
      .catch((e) => {
        if (e instanceof ErroApi && e.status === 404) setEventos([])
        else setErroEventos(mensagem(e))
      })
  }, [eventId])

  if (erroEventos) return <Moldura><Aviso tipo="erro">{erroEventos}</Aviso></Moldura>
  if (!eventos) return <Moldura><Carregando /></Moldura>

  const evento = eventos.length === 1 ? eventos[0] : null
  if (!evento) {
    return (
      <Moldura>
        {eventos.length === 0 ? (
          <section className="rec-painel p-6 text-center">
            <Icone nome="info" className="mx-auto h-10 w-10 text-mallory-acao" />
            <h1 className="mt-3 text-xl font-bold">Cadastro indisponível</h1>
            <p className="mt-2 text-base text-mallory-texto">
              O cadastro pelo celular não está aberto agora. Procure a Recepção do evento.
            </p>
          </section>
        ) : (
          <section className="rec-painel p-6">
            <h1 className="text-xl font-bold">Escolha o evento</h1>
            <ul className="mt-4 space-y-3">
              {eventos.map((e) => (
                <li key={e.id}>
                  <Link
                    to={`/evento/${e.id}/cadastro`}
                    className="rec-foco flex w-full items-center justify-between gap-3 rounded-xl border-2 border-slate-200 bg-white p-4 hover:border-mallory-laranja"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{e.nome}</span>
                      <span className="block truncate text-sm text-mallory-texto">
                        {e.empresa_nome}
                        {e.demo ? ' · demonstração' : ''}
                      </span>
                    </span>
                    <Icone nome="seta" className="h-5 w-5 shrink-0 text-mallory-acao" />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </Moldura>
    )
  }

  return <Fluxo evento={evento} />
}

function Moldura({
  evento,
  rodapeLogin = true,
  children,
}: {
  evento?: EventoAutocadastro
  rodapeLogin?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-full flex-col bg-mallory-fundo text-mallory-preto">
      <CabecalhoMallory secao="Cadastro" icone="premios" evento={evento?.nome} mostrarSecao={false}>
        <Link to="/login" className={CLASSE_BOTAO_CABECALHO} title="Entrar">
          <Icone nome="senha" className="h-4 w-4" />
          <span className="hidden sm:inline">Entrar</span>
        </Link>
      </CabecalhoMallory>
      {evento?.demo && <FaixaDemo />}
      {/* Celular: espaçamentos menores para o formulário caber sem rolar. */}
      <main className="mx-auto w-full max-w-md flex-1 px-4 py-3 sm:py-8">
        {children}
        {rodapeLogin && (
          <p className="mt-4 text-center text-sm text-mallory-texto sm:mt-6">
            Já tem cadastro?{' '}
            <Link to="/login" className="rec-foco rounded font-semibold text-mallory-acao hover:underline">
              Entrar com matrícula e senha
            </Link>
          </p>
        )}
      </main>
      <div className="hidden sm:block">
        <RodapeMallory secao="Cadastro" />
      </div>
    </div>
  )
}

/** Cartão branco com o detalhe laranja no canto, como no modelo. */
function Cartao({ children }: { children: React.ReactNode }) {
  return (
    <section className="rec-painel relative overflow-hidden">
      <svg aria-hidden className="pointer-events-none absolute bottom-0 right-0 h-14 w-40" viewBox="0 0 160 56" preserveAspectRatio="none">
        <path d="M160 6 C 130 40, 70 54, 0 56 L 160 56 Z" fill="#F16425" />
      </svg>
      <div className="relative space-y-4 px-5 pb-10 pt-5 sm:space-y-5 sm:px-7 sm:pb-12 sm:pt-7">{children}</div>
    </section>
  )
}

function Topo({ icone, titulo, subtitulo, cor = 'laranja' }: { icone: NomeIcone; titulo: string; subtitulo?: React.ReactNode; cor?: 'laranja' | 'verde' }) {
  return (
    <div className="text-center">
      {cor === 'verde' ? (
        <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-600 text-white shadow-suave">
          <Icone nome={icone} className="h-9 w-9" />
        </span>
      ) : (
        <Icone nome={icone} className="mx-auto h-10 w-10 text-mallory-escuro sm:h-12 sm:w-12" />
      )}
      <h1 className="mt-2 text-[26px] font-bold leading-tight sm:mt-3">{titulo}</h1>
      {subtitulo && <div className="mt-2 text-base text-mallory-texto">{subtitulo}</div>}
    </div>
  )
}

function Fluxo({ evento }: { evento: EventoAutocadastro }) {
  const navegar = useNavigate()
  const { adotarSessao } = useAuth()
  const [passo, setPasso] = useState<Passo>('identificacao')
  const [matricula, setMatricula] = useState('')
  const [nascimento, setNascimento] = useState('')
  const [cpf5, setCpf5] = useState('')
  const [identificacao, setIdentificacao] = useState<Identificacao | null>(null)
  const [foto, setFoto] = useState<FotoPronta | null>(null)
  const [removerFoto, setRemoverFoto] = useState(false)
  const [erro, setErro] = useState('')
  const [jaCadastrado, setJaCadastrado] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [concluido, setConcluido] = useState<AutocadastroConcluido | null>(null)

  const base = `/api/autocadastro/${evento.id}`
  const nascimentoIso = dataParaIso(nascimento)

  function irPara(proximo: Passo) {
    setErro('')
    setPasso(proximo)
    window.scrollTo({ top: 0 })
  }

  async function executar(acao: () => Promise<void>) {
    setEnviando(true)
    setErro('')
    setJaCadastrado(false)
    try {
      await acao()
    } catch (e) {
      setErro(mensagem(e))
      setJaCadastrado(e instanceof ErroApi && e.status === 409)
      // Passe vencido: volta para a identificação.
      if (e instanceof ErroApi && e.status === 401 && passo === 'confirmacao') {
        setIdentificacao(null)
        setPasso('identificacao')
      }
    } finally {
      setEnviando(false)
    }
  }

  const identificar = () =>
    executar(async () => {
      const dados = await requisitar<Identificacao>(`${base}/identificar`, {
        metodo: 'POST',
        corpo: { matricula: matricula.trim(), nascimento: nascimentoIso, cpf5: cpf5.trim() },
        autenticado: false,
      })
      // Nascimento e CPF ficam só na memória desta tela até confirmar o cadastro
      // (o servidor confere de novo: os 5 dígitos viram a senha).
      setIdentificacao(dados)
      setRemoverFoto(false)
      irPara('confirmacao')
    })

  const concluir = () =>
    executar(async () => {
      if (!identificacao) return
      const resultado = await enviarFormulario<AutocadastroConcluido>(
        `${base}/concluir`,
        {
          passe: identificacao.passe,
          nascimento: nascimentoIso ?? '',
          cpf5: cpf5.trim(),
          remover_foto: removerFoto && !foto ? 'true' : 'false',
        },
        foto ? { foto: { conteudo: foto.conteudo, nome: foto.nome } } : {},
      )
      adotarSessao(resultado.access_token, resultado.usuario)
      setConcluido(resultado)
      setNascimento('')
      setCpf5('')
      irPara('pronto')
    })

  const identificacaoCompleta = !!matricula.trim() && nascimentoIso !== null && /^\d{5}$/.test(cpf5)
  // Data com 10 caracteres que nao existe (31/02, ano futuro): avisa no campo.
  const dataInvalida = nascimento.length === 10 && nascimentoIso === null
  const fotoAtual = identificacao?.foto_url && !removerFoto ? identificacao.foto_url : null

  return (
    <Moldura evento={evento} rodapeLogin={passo === 'identificacao'}>
      <Cartao>
        {erro && (
          <Aviso tipo="erro">
            {erro}
            {jaCadastrado && (
              <Link to="/login" className="mt-2 block font-semibold underline">
                Ir para o login
              </Link>
            )}
          </Aviso>
        )}

        {passo === 'identificacao' && (
          <form
            className="space-y-4 sm:space-y-5"
            onSubmit={(e) => {
              e.preventDefault()
              void identificar()
            }}
          >
            {/* O nome do evento já aparece inteiro no cabeçalho. */}
            <Topo icone="premios" titulo="Cadastro para o Sorteio" subtitulo="Preencha seus dados para participar do sorteio." />
            <div>
              <label className={ROTULO} htmlFor="matricula">
                <Icone nome="cracha" className="h-5 w-5 text-mallory-escuro" />
                Matrícula <span className="text-mallory-acao">*</span>
              </label>
              <input
                id="matricula"
                className={CAMPO}
                autoComplete="username"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={20}
                placeholder="Digite sua matrícula"
                value={matricula}
                onChange={(e) => setMatricula(e.target.value.replace(/\D/g, ''))}
                autoFocus
                required
              />
            </div>
            <div>
              <label className={ROTULO} htmlFor="nascimento">
                <Icone nome="eventos" className="h-5 w-5 text-mallory-escuro" />
                Data de nascimento <span className="text-mallory-acao">*</span>
              </label>
              <input
                id="nascimento"
                type="text"
                inputMode="numeric"
                autoComplete="bday"
                className={CAMPO}
                placeholder="dd/mm/aaaa"
                maxLength={10}
                value={nascimento}
                onChange={(e) => setNascimento(mascararData(e.target.value))}
                aria-invalid={dataInvalida}
                aria-describedby={dataInvalida ? 'nascimento-erro' : undefined}
                required
              />
              {dataInvalida && (
                <p id="nascimento-erro" className="mt-1 text-sm font-medium text-red-700">
                  Data inválida. Confira o dia, o mês e o ano.
                </p>
              )}
            </div>
            <div>
              <label className={ROTULO} htmlFor="cpf5">
                <Icone nome="bilhete" className="h-5 w-5 text-mallory-escuro" />
                CPF (5 primeiros dígitos) <span className="text-mallory-acao">*</span>
              </label>
              <input
                id="cpf5"
                className={`${CAMPO} ${cpf5 ? 'tracking-[0.3em]' : ''}`}
                inputMode="numeric"
                autoComplete="off"
                pattern="\d{5}"
                maxLength={5}
                placeholder="Ex.: 12345"
                value={cpf5}
                onChange={(e) => setCpf5(e.target.value.replace(/\D/g, '').slice(0, 5))}
                required
              />
              <p className="mt-1.5 text-xs text-mallory-texto">
                Usado só para confirmar que é você. O sistema não guarda seu CPF nem sua data de nascimento.
              </p>
            </div>
            <button className="rec-btn-primario w-full uppercase tracking-wide" disabled={enviando || !identificacaoCompleta}>
              {enviando ? 'Conferindo...' : 'Continuar'}
              {!enviando && <Icone nome="avancar" className="h-5 w-5" />}
            </button>
            <p className="text-center text-xs text-mallory-texto">* Campos obrigatórios</p>
          </form>
        )}

        {passo === 'confirmacao' && identificacao && (
          <form
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault()
              void concluir()
            }}
          >
            <Topo
              icone="pessoa"
              titulo="Confirme seus dados"
              subtitulo="Confira seu nome e, se quiser, adicione uma foto para o credenciamento."
            />
            <div className="rounded-xl bg-mallory-fundo p-4">
              <div className="flex items-start gap-3">
                <Icone nome="pessoa" className="mt-1 h-5 w-5 shrink-0 text-mallory-escuro" />
                <div className="min-w-0">
                  <p className="text-xs text-mallory-texto">Nome</p>
                  <p className="text-lg font-bold leading-snug">{identificacao.nome}</p>
                </div>
              </div>
              <div className="mt-3 flex items-start gap-3 border-t border-slate-200 pt-3">
                <Icone nome="cracha" className="mt-0.5 h-5 w-5 shrink-0 text-mallory-escuro" />
                <div>
                  <p className="text-xs text-mallory-texto">Matrícula</p>
                  <p className="font-mono font-semibold">{identificacao.matricula}</p>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <p className={ROTULO}>
                <Icone nome="camera" className="h-5 w-5 text-mallory-escuro" />
                Foto <span className="font-normal text-mallory-texto">(opcional)</span>
              </p>
              {fotoAtual && !foto && (
                <div className="flex items-center gap-3 rounded-xl border border-slate-200 p-3">
                  <img src={fotoAtual} alt="Sua foto atual" className="h-14 w-14 rounded-full object-cover ring-2 ring-mallory-laranja" />
                  <p className="flex-1 text-sm text-mallory-texto">Esta é a sua foto atual.</p>
                  <button type="button" className="rec-foco rounded text-sm font-semibold text-mallory-acao hover:underline" onClick={() => setRemoverFoto(true)}>
                    Remover
                  </button>
                </div>
              )}
              {removerFoto && !foto && (
                <p className="rounded-lg bg-mallory-claro px-3 py-2 text-sm">
                  A foto atual será removida.{' '}
                  <button type="button" className="font-semibold text-mallory-acao underline" onClick={() => setRemoverFoto(false)}>
                    Manter foto
                  </button>
                </p>
              )}
              <div className="rounded-xl border-2 border-dashed border-slate-300 p-4">
                {!foto && (
                  <div className="mb-3 text-center">
                    <Icone nome="camera" className="mx-auto h-9 w-9 text-slate-400" />
                    <p className="mt-1 font-semibold">{fotoAtual ? 'Trocar foto' : 'Adicionar foto'}</p>
                    <p className="text-xs text-mallory-texto">Tire uma foto ou escolha um arquivo.</p>
                  </div>
                )}
                <CapturaFoto foto={foto} aoMudar={setFoto} />
              </div>
              <p className="text-center text-xs text-mallory-texto">Formatos: JPG ou PNG (até 5 MB)</p>
            </div>

            <AvisoSenha login={identificacao.login} />

            <div className="space-y-3">
              <button className="rec-btn-primario w-full uppercase tracking-wide" disabled={enviando}>
                {!enviando && <Icone nome="check" className="h-5 w-5" />}
                {enviando ? 'Confirmando...' : 'Confirmar cadastro'}
              </button>
              <button
                type="button"
                className="rec-foco mx-auto flex items-center gap-2 rounded px-2 py-1 text-sm font-medium text-mallory-texto hover:text-mallory-preto"
                onClick={() => {
                  setIdentificacao(null)
                  setFoto(null)
                  irPara('identificacao')
                }}
              >
                <Icone nome="seta" className="h-4 w-4 rotate-180" />
                Corrigir dados
              </button>
            </div>
          </form>
        )}

        {passo === 'pronto' && concluido && (
          <div className="space-y-5">
            <Topo
              icone="check"
              cor="verde"
              titulo="Cadastro realizado!"
              subtitulo={`Você está na lista do sorteio da ${concluido.cartao.evento_nome}.`}
            />
            <BilheteSorte numero={concluido.cartao.numero_sorteio} matricula={concluido.cartao.matricula_da_sorte} />
            <CartaoPessoa cartao={concluido.cartao} />
            <SituacaoCheckin cartao={concluido.cartao} />
            <button type="button" className="rec-btn-primario w-full" onClick={() => navegar('/minha-area')}>
              <Icone nome="inicio" className="h-5 w-5" />
              Ver meu cartão da sorte
            </button>
            <AvisoSenha login={concluido.login} />
          </div>
        )}
      </Cartao>
    </Moldura>
  )
}

/** Alerta de como o colaborador entra depois (senha = 5 primeiros dígitos do CPF). */
export function AvisoSenha({ login }: { login: string }) {
  return (
    <div role="note" className="flex gap-3 rounded-xl border-2 border-mallory-laranja bg-mallory-claro p-4">
      <Icone nome="senha" className="mt-0.5 h-6 w-6 shrink-0 text-mallory-acao" />
      <div className="text-sm text-mallory-preto">
        <p className="text-base font-bold">Sua senha de acesso</p>
        <p className="mt-1">
          A sua senha são os <strong>5 primeiros dígitos do seu CPF</strong>.
        </p>
        <p className="mt-1">
          Para voltar ao seu cartão, toque em <strong>Entrar</strong> e use a matrícula{' '}
          <strong className="font-mono">{login}</strong> e essa senha.
        </p>
      </div>
    </div>
  )
}

/** Trevo de quatro folhas (decorativo, SVG local reutilizado nos quatro cantos). */
function Trevo({ className }: { className: string }) {
  // Folha em coração com a ponta no centro; girada 4 vezes em X.
  const folha =
    'M0 0C-1.2-2.4-6.4-3.6-6.4-7.4C-6.4-10-3.8-11.2-1.9-10.2C-1-9.7-.4-9-.0-8.2C.4-9 1-9.7 1.9-10.2C3.8-11.2 6.4-10 6.4-7.4C6.4-3.6 1.2-2.4 0 0Z'
  const id = `trevo-${useId().replace(/:/g, '')}`
  return (
    <svg viewBox="-13 -13 26 26" aria-hidden="true" focusable="false" className={`bilhete-sorte__trevo ${className}`}>
      <defs>
        <linearGradient id={id} x1="0" y1="-11" x2="0" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#3DBB3D" />
          <stop offset="1" stopColor="#168A16" />
        </linearGradient>
      </defs>
      <path d="M1.2 1.5C3.2 4.2 4.4 7.4 4.6 11.5" fill="none" stroke="#168A16" strokeWidth="1.5" strokeLinecap="round" />
      {[45, 135, 225, 315].map((g) => (
        <g key={g} transform={`rotate(${g})`}>
          <path d={folha} fill={`url(#${id})`} />
          <path d="M0-1.2V-7.6" stroke="#9BE29B" strokeWidth=".7" strokeLinecap="round" opacity=".8" />
        </g>
      ))}
      <circle r="1.1" fill="#126F12" />
    </svg>
  )
}

/**
 * Número da sorte em destaque (mesmo componente do portal e da confirmação de
 * cadastro). Verde normalmente; dourado quando a pessoa já foi sorteada (o
 * prêmio só chega ao portal depois da revelação no telão).
 *
 * `matricula`: preenchida quando o evento sorteia pela faixa de matrículas;
 * aí a matrícula é o número da sorte e aparece no lugar do número aleatório.
 */
export function BilheteSorte({
  numero: numeroAleatorio,
  matricula = null,
  sorteado = false,
}: {
  numero: number | null
  matricula?: string | null
  sorteado?: boolean
}) {
  const numero = matricula ?? numeroAleatorio
  const tamanho = String(numero ?? '').length
  const classeTamanho = tamanho > 9 ? ' bilhete-sorte__numero--longo' : tamanho > 6 ? ' bilhete-sorte__numero--medio' : ''
  const destaque = sorteado ? '#C88A12' : '#6CC72E'
  return (
    <div className={`bilhete-sorte${sorteado ? ' bilhete-sorte--ouro' : ''}`}>
      <div className="bilhete-sorte__fundo" aria-hidden="true">
        {/* Curvas decorativas discretas nas extremidades. */}
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 160" preserveAspectRatio="none">
          <path d="M0 116C70 96 150 98 250 132C150 110 70 112 0 136Z" fill="#FFFFFF" opacity=".5" />
          <path d="M0 140C80 118 160 122 230 150C150 132 80 136 0 160Z" fill={destaque} opacity=".22" />
          <path d="M400 20C330 52 250 58 150 32C250 48 330 40 400 0Z" fill="#FFFFFF" opacity=".5" />
          <path d="M400 44C320 74 240 74 170 54C245 64 330 58 400 26Z" fill={destaque} opacity=".2" />
        </svg>
        {sorteado && (
          // Brilhos estáticos (sem animação), como na referência dourada.
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 160" preserveAspectRatio="xMidYMid slice">
            {[
              [40, 98, 6],
              [348, 80, 8],
              [300, 140, 5],
              [26, 58, 4],
            ].map(([x, y, r]) => (
              <path
                key={`${x}-${y}`}
                d={`M${x} ${y - r}Q${x + r * 0.18} ${y - r * 0.18} ${x + r} ${y}Q${x + r * 0.18} ${y + r * 0.18} ${x} ${y + r}Q${x - r * 0.18} ${y + r * 0.18} ${x - r} ${y}Q${x - r * 0.18} ${y - r * 0.18} ${x} ${y - r}Z`}
                fill="#FFFFFF"
                opacity=".9"
              />
            ))}
          </svg>
        )}
      </div>
      <Trevo className="bilhete-sorte__trevo--se" />
      <Trevo className="bilhete-sorte__trevo--sd" />
      <Trevo className="bilhete-sorte__trevo--ie" />
      <Trevo className="bilhete-sorte__trevo--id" />
      <div className="relative px-12 py-6 text-center sm:px-16 sm:py-8">
        {numero !== null ? (
          <>
            <p className={`text-base font-bold sm:text-xl ${sorteado ? 'text-[#5C3B00]' : 'text-[#1F5F1F]'}`}>
              {matricula ? 'Seu número da sorte é a sua matrícula' : 'Seu número da sorte é'}
            </p>
            <p className={`bilhete-sorte__numero mt-1${classeTamanho}`}>{numero}</p>
          </>
        ) : (
          <>
            <p className="text-base font-bold text-[#1F5F1F]">Número da sorte</p>
            <p className="mt-2 text-sm text-[#2F4A2F]">
              Seu número ainda não foi atribuído. Ele aparece aqui assim que a organização liberar.
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export function CartaoPessoa({ cartao }: { cartao: Pick<CartaoSorte, 'nome' | 'matricula' | 'foto_url'> }) {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-mallory-fundo p-4">
      <div className="min-w-0 flex-1 space-y-2">
        <p className="flex items-center gap-2 text-lg font-bold leading-snug">
          <Icone nome="pessoa" className="h-5 w-5 shrink-0 text-mallory-escuro" />
          <span className="min-w-0 break-words">{cartao.nome}</span>
        </p>
        <p className="flex items-center gap-2 border-t border-slate-200 pt-2 text-sm text-mallory-texto">
          <Icone nome="cracha" className="h-4 w-4 shrink-0 text-mallory-escuro" />
          Matrícula: <span className="font-mono text-mallory-preto">{cartao.matricula}</span>
        </p>
      </div>
      {cartao.foto_url ? (
        <img src={cartao.foto_url} alt="Sua foto" className="h-20 w-20 shrink-0 rounded-xl object-cover" />
      ) : (
        <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-xl bg-white text-slate-300">
          <Icone nome="pessoa" className="h-10 w-10" />
        </span>
      )}
    </div>
  )
}

export function SituacaoCheckin({ cartao }: { cartao: Pick<CartaoSorte, 'presente' | 'participando'> }) {
  if (!cartao.participando) {
    return <Aviso tipo="atencao">Sua participação está suspensa. Procure a organização do evento.</Aviso>
  }
  return cartao.presente ? (
    <p className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800">
      <Icone nome="check" className="h-4 w-4" /> Check-in confirmado.
    </p>
  ) : (
    <p className="flex items-start gap-2 rounded-lg bg-mallory-claro px-3 py-2 text-sm text-mallory-preto">
      <Icone nome="info" className="mt-0.5 h-4 w-4 shrink-0 text-mallory-acao" />
      Check-in pendente: no dia do evento, confirme sua presença na Recepção.
    </p>
  )
}
