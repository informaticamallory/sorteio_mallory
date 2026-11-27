import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { usePosicaoCarrossel } from '../carrossel'
import AnuncioGanhador, {
  AVISO_IMAGEM_ILUSTRATIVA,
  FundoFestivo,
  ROTULO_MATRICULA_TELAO,
} from '../componentes/AnuncioGanhador'
import Confete from '../componentes/Confete'
import { ImagemPremio } from '../componentes/ui'
import { audioLiberado, liberarAudio, somDoEvento, somRufar } from '../som'
import type { TelaoEstado } from '../types'
import TelaoClaro, { gradeResumo, Rolos, useFaseRevelacao, type FaseRevelacao } from './TelaoClaro'
import { msRestantes, useTelao } from '../useTelao'

export default function Telao() {
  const { token } = useParams()
  const { estado, conexao } = useTelao(token)
  const [reduzirLocal, setReduzirLocal] = useState(false)
  const [somPronto, setSomPronto] = useState(false)
  const [controlesVisiveis, setControlesVisiveis] = useState(true)
  // Fase da revelação no Clássico: o fundo festivo e o cabeçalho flutuante só
  // entram com o anúncio completo (antes disso a tela é a dos rolos).
  const [faseResultado, setFaseResultado] = useState<FaseRevelacao>('completo')

  const reduzir = reduzirLocal || estado?.evento.reduzir_animacoes === true
  const somAtivo = somPronto && estado?.evento.som_ativado === true
  // Posição do carrossel calculada AQUI pelo relógio (o slide avança sem nova
  // mensagem do servidor): o fundo festivo some quando chega ao resumo.
  const { posicao: posicaoCarrossel } = usePosicaoCarrossel(estado?.carrossel, estado?.servidor_agora)

  // Aplica as cores do evento como variaveis CSS.
  useEffect(() => {
    if (!estado) return
    const raiz = document.documentElement.style
    raiz.setProperty('--cor-fundo', estado.evento.cor_fundo)
    raiz.setProperty('--cor-primaria', estado.evento.cor_primaria)
    raiz.setProperty('--cor-texto', estado.evento.cor_texto)
    raiz.setProperty('--cor-destaque', estado.evento.cor_destaque)
    document.title = `${estado.evento.nome} — Telão`
  }, [estado])

  // Os controles somem sozinhos para não poluir a projeção.
  useEffect(() => {
    let temporizador: number
    const mostrar = () => {
      setControlesVisiveis(true)
      window.clearTimeout(temporizador)
      temporizador = window.setTimeout(() => setControlesVisiveis(false), 4000)
    }
    mostrar()
    window.addEventListener('mousemove', mostrar)
    window.addEventListener('touchstart', mostrar)
    return () => {
      window.clearTimeout(temporizador)
      window.removeEventListener('mousemove', mostrar)
      window.removeEventListener('touchstart', mostrar)
    }
  }, [])

  async function alternarTelaCheia() {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await document.documentElement.requestFullscreen().catch(() => undefined)
  }

  if (!estado) {
    return (
      <div className="telao flex min-h-full items-center justify-center p-8 text-center">
        <div>
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-white/80" />
          <p className="text-xl opacity-80">
            {conexao === 'erro' ? 'Não foi possível conectar ao telão.' : 'Conectando ao evento...'}
          </p>
        </div>
      </div>
    )
  }

  // Tema "Mallory claro": outra apresentação, mesmos dados e mesmos controles.
  if (estado.evento.tema_telao === 'mallory_claro') {
    return (
      <TelaoClaro
        estado={estado}
        conexao={conexao}
        reduzir={reduzir}
        somAtivo={somAtivo}
        controlesVisiveis={controlesVisiveis}
        mostrarAtivarSom={estado.evento.som_ativado && !audioLiberado()}
        aoAtivarSom={() => void liberarAudio().then(setSomPronto)}
        aoAlternarAnimacoes={() => setReduzirLocal((v) => !v)}
        aoTelaCheia={() => void alternarTelaCheia()}
      />
    )
  }

  // Anúncio do ganhador (resultado e carrossel, menos o slide-resumo).
  const festivo =
    (estado.estado === 'resultado' && faseResultado === 'completo') ||
    (estado.estado === 'carrossel_ganhadores' && posicaoCarrossel < (estado.carrossel?.total ?? 0))

  return (
    <div
      className="telao relative flex h-full min-h-full flex-col overflow-hidden"
      // Unidade proporcional à tela (mesma do tema claro), usada pelos rolos de número.
      style={{ '--u': 'min(0.05vw, 0.08889vh)' } as React.CSSProperties}
    >
      {festivo && <FundoFestivo reduzir={reduzir} />}

      {/* ---------------------------------------------------- cabeçalho */}
      {/* No anúncio do ganhador o cabeçalho flutua, para o anúncio usar a tela toda. */}
      <header
        className={`z-20 flex items-center justify-between gap-4 px-6 py-4 sm:px-10 ${
          festivo ? 'absolute inset-x-0 top-0' : 'relative'
        }`}
      >
        <div className="flex items-center gap-4">
          {estado.evento.logo_url && (
            <img
              src={estado.evento.logo_url}
              alt={estado.evento.empresa_nome}
              className="h-10 w-auto object-contain sm:h-14"
            />
          )}
          <div>
            <p className="text-sm uppercase tracking-[0.12em] opacity-70 sm:text-base">
              {estado.evento.empresa_nome}
            </p>
            <p className="text-lg font-bold sm:text-2xl">{estado.evento.nome}</p>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {estado.bloco && estado.estado !== 'aguardando' && estado.estado !== 'encerramento' && (
            <div className="rounded-lg border-2 borda-ouro px-4 py-2 text-center">
              <p className="text-[10px] uppercase tracking-widest opacity-70">Bloco</p>
              <p className="text-2xl font-bold texto-ouro sm:text-3xl">
                {String(estado.bloco.numero).padStart(2, '0')}
              </p>
            </div>
          )}
          {estado.rodada !== null && estado.estado !== 'aguardando' && (
            <div className="rounded-lg border-2 borda-ouro px-4 py-2 text-center">
              <p className="text-[10px] uppercase tracking-widest opacity-70">Rodada</p>
              <p className="text-2xl font-bold texto-ouro sm:text-3xl">{estado.rodada}</p>
            </div>
          )}
        </div>
      </header>

      <main
        className={`relative z-10 flex flex-1 items-center justify-center px-6 sm:px-10 ${
          festivo ? 'py-[2.5vh]' : 'pb-10'
        }`}
      >
        {estado.estado === 'aguardando' && <Aguardando estado={estado} />}
        {estado.estado === 'premio' && <ApresentacaoPremio estado={estado} />}
        {estado.estado === 'sorteando' && (
          <Sorteando estado={estado} reduzir={reduzir} somAtivo={somAtivo} />
        )}
        {estado.estado === 'resultado' && (
          <Resultado estado={estado} reduzir={reduzir} somAtivo={somAtivo} aoMudarFase={setFaseResultado} />
        )}
        {estado.estado === 'encerramento' && <Encerramento estado={estado} />}
        {estado.estado === 'carrossel_ganhadores' && <Carrossel estado={estado} reduzir={reduzir} />}
      </main>

      {/* ---------------------------------------------------- controles */}
      <div
        className={`fixed bottom-4 right-4 z-20 flex items-center gap-2 transition-opacity duration-500 ${
          controlesVisiveis ? 'opacity-100' : 'opacity-0'
        }`}
      >
        <span
          className="rounded-full px-3 py-1.5 text-xs"
          style={{ background: 'rgba(0,0,0,0.35)' }}
          title={`Conexão: ${conexao}`}
        >
          {conexao === 'conectado' ? 'Ao vivo' : conexao === 'reconectando' ? 'Reconectando' : 'Offline'}
        </span>
        {estado.evento.som_ativado && !audioLiberado() && (
          <BotaoControle
            aoClicar={async () => setSomPronto(await liberarAudio())}
            titulo="Ativar som"
          >
            Ativar som
          </BotaoControle>
        )}
        <BotaoControle
          aoClicar={() => setReduzirLocal((v) => !v)}
          titulo="Alternar animações reduzidas"
        >
          {reduzir ? 'Animações off' : 'Animações on'}
        </BotaoControle>
        <BotaoControle aoClicar={alternarTelaCheia} titulo="Tela cheia">
          Tela cheia
        </BotaoControle>
      </div>
    </div>
  )
}

function BotaoControle({
  children,
  aoClicar,
  titulo,
}: {
  children: React.ReactNode
  aoClicar: () => void | Promise<void>
  titulo: string
}) {
  return (
    <button
      type="button"
      title={titulo}
      onClick={() => void aoClicar()}
      className="rounded-full px-3 py-1.5 text-xs font-medium transition hover:brightness-125"
      style={{ background: 'rgba(0,0,0,0.35)', color: 'var(--cor-texto)' }}
    >
      {children}
    </button>
  )
}

// ------------------------------------------------------------------ estados
function Aguardando({ estado }: { estado: TelaoEstado }) {
  return (
    <div className="animate-sobe-suave text-center">
      <p className="text-4xl font-bold leading-tight texto-ouro sm:text-6xl lg:text-7xl">
        {estado.evento.mensagem_boas_vindas}
      </p>
      <p className="mt-8 text-xl opacity-75 sm:text-3xl">O sorteio começa em instantes</p>
    </div>
  )
}

function ApresentacaoPremio({ estado }: { estado: TelaoEstado }) {
  const [imagemQuebrada, setImagemQuebrada] = useState<string | null>(null)
  if (!estado.premio) return null
  const { premio } = estado
  const comImagem = !!premio.imagem_url && imagemQuebrada !== premio.imagem_url
  return (
    <div className="grid w-full max-w-6xl animate-sobe-suave items-center gap-8 lg:grid-cols-2">
      <div className="mx-auto w-full max-w-md overflow-hidden rounded-lg border-2 borda-ouro p-3">
        <ImagemPremio
          url={premio.imagem_url}
          nome={premio.nome}
          grande
          aoFalhar={setImagemQuebrada}
          className="h-64 w-full rounded-lg sm:h-80 lg:h-96"
        />
        {comImagem && (
          <p className="mt-2 text-center text-sm italic opacity-70 sm:text-base">{AVISO_IMAGEM_ILUSTRATIVA}</p>
        )}
      </div>
      <div className="text-center lg:text-left">
        <p className="text-lg uppercase tracking-[0.12em] opacity-70 sm:text-xl">Próximo prêmio</p>
        <h2 className="mt-2 text-4xl font-bold leading-tight texto-ouro sm:text-6xl">
          {premio.nome}
        </h2>
        {premio.descricao && (
          <p className="mt-4 text-xl opacity-80 sm:text-2xl">{premio.descricao}</p>
        )}
        {premio.unidade_total > 1 && (
          <p className="mt-6 inline-block rounded-full border-2 borda-ouro px-5 py-2 text-lg font-semibold sm:text-xl">
            Unidade {premio.unidade_numero} de {premio.unidade_total}
          </p>
        )}
      </div>
    </div>
  )
}

// Rolos do Clássico: cores do evento (fundo, dourado da cor primária).
const CORES_ROLO_CLASSICO = {
  fundo: 'var(--cor-fundo)',
  borda: 'var(--cor-primaria)',
  digito: 'var(--cor-primaria)',
}

/** Rolos de número girando enquanto o servidor revela (como no tema claro). */
function Sorteando({
  estado,
  reduzir,
  somAtivo,
}: {
  estado: TelaoEstado
  reduzir: boolean
  somAtivo: boolean
}) {
  const digitos = Math.min(9, Math.max(1, estado.digitos_animacao ?? 4))
  const duracao = useMemo(() => msRestantes(estado), [estado])

  // O rufar e preso ao horario de revelacao: novas mensagens do servidor durante
  // a mesma animacao nao o reiniciam; sair da tela antes do fim o interrompe.
  const duracaoRef = useRef(duracao)
  duracaoRef.current = duracao
  useEffect(() => {
    if (!somAtivo) return
    return somRufar(duracaoRef.current, somDoEvento(estado.evento?.som_sorteio))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [somAtivo, estado.revelar_em])

  return <PainelRolos estado={estado} valor={null} digitos={digitos} reduzir={reduzir} />
}

/** Cartão do sorteio do Clássico: prêmio em cima, rolos, "Quem será?" embaixo. */
function PainelRolos({
  estado,
  valor,
  digitos,
  reduzir,
  atrasoMs = 0,
}: {
  estado: TelaoEstado
  valor: string | null
  digitos: number
  reduzir: boolean
  atrasoMs?: number
}) {
  return (
    <div className="w-full max-w-5xl text-center">
      {estado.premio && (
        <p className="mb-6 text-xl opacity-70 sm:text-2xl">
          Sorteando: <span className="font-semibold texto-ouro">{estado.premio.nome}</span>
          {estado.premio.unidade_total > 1 &&
            ` · unidade ${estado.premio.unidade_numero} de ${estado.premio.unidade_total}`}
        </p>
      )}

      <div className="flex min-h-44 items-center justify-center rounded-lg border-2 borda-ouro px-6 py-8 sm:min-h-60">
        {reduzir && valor === null ? (
          <p className="text-3xl font-bold opacity-80 sm:text-5xl">Sorteando...</p>
        ) : (
          <div style={{ marginTop: 'calc(-22 * var(--u))' }}>
            <Rolos valor={valor} digitos={digitos} atrasoMs={atrasoMs} cores={CORES_ROLO_CLASSICO} />
          </div>
        )}
      </div>

      <p className="mt-8 text-lg uppercase tracking-[0.15em] opacity-60 sm:text-2xl">
        {valor === null ? 'Quem será?' : 'Número sorteado'}
      </p>
    </div>
  )
}

/** Revelação: rolos param no número, nome sozinho e então o anúncio completo. */
function Resultado({
  estado,
  reduzir,
  somAtivo,
  aoMudarFase,
}: {
  estado: TelaoEstado
  reduzir: boolean
  somAtivo: boolean
  aoMudarFase: (fase: FaseRevelacao) => void
}) {
  const { fase, numero, digitos, atrasoMs } = useFaseRevelacao(estado, reduzir, somAtivo)
  useLayoutEffect(() => aoMudarFase(fase), [fase, aoMudarFase])
  const ganhador = estado.ganhador
  if (!ganhador) return null
  const premio = estado.premio

  if (fase === 'parando' && numero) {
    return <PainelRolos estado={estado} valor={numero} digitos={digitos} reduzir={reduzir} atrasoMs={atrasoMs} />
  }

  if (fase === 'nome') {
    return (
      <div className="w-full max-w-5xl animate-sobe-suave text-center">
        <p className="text-lg uppercase tracking-[0.2em] opacity-70 sm:text-2xl">Parabéns!</p>
        <p className="mt-4 break-words text-5xl font-bold leading-tight texto-ouro sm:text-7xl">{ganhador.nome}</p>
        {numero && (
          <p className="mt-6 inline-block rounded-full border-2 borda-ouro px-8 py-2 text-3xl font-bold tabular-nums sm:text-5xl">
            {numero}
          </p>
        )}
      </div>
    )
  }

  return (
    <>
      <Confete
        ativo
        reduzido={reduzir}
        cores={[estado.evento.cor_primaria, estado.evento.cor_texto, estado.evento.cor_destaque]}
        duracaoMs={2800}
        quantidade={45}
      />
      <AnuncioGanhador
        reduzir={reduzir}
        dados={{
          nome: ganhador.nome,
          setor: ganhador.setor,
          fotoUrl: ganhador.foto_url,
          numero: ganhador.numero_sorteio,
          matricula: ganhador.matricula_da_sorte,
          premioNome: premio?.nome ?? '',
          premioDescricao: premio?.descricao,
          premioImagemUrl: premio?.imagem_url ?? null,
          detalhePremio:
            premio && premio.unidade_total > 1 ? `Unidade ${premio.unidade_numero} de ${premio.unidade_total}` : null,
        }}
      />
    </>
  )
}

// ------------------------------------------------------------------ carrossel
function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean)
  const primeira = partes[0]?.[0] ?? ''
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : ''
  return (primeira + ultima).toUpperCase()
}

/** Foto do ganhador ou, sem foto, as iniciais sobre as cores do evento. */
function FotoGanhador({
  url,
  nome,
  className,
  estilo,
}: {
  url: string | null
  nome: string
  className: string
  estilo?: React.CSSProperties
}) {
  const [falhou, setFalhou] = useState(false)
  if (url && !falhou) {
    return (
      <img
        src={url}
        alt=""
        onError={() => setFalhou(true)}
        className={`rounded-full border-2 borda-ouro object-cover ${className}`}
        style={estilo}
      />
    )
  }
  return (
    <div
      aria-hidden="true"
      className={`flex items-center justify-center rounded-full border-2 borda-ouro font-bold texto-ouro ${className}`}
      style={{ background: 'rgba(255, 255, 255, 0.08)', ...estilo }}
    >
      <span style={{ fontSize: '38%' }}>{iniciais(nome)}</span>
    </div>
  )
}

function Carrossel({ estado, reduzir }: { estado: TelaoEstado; reduzir: boolean }) {
  const dados = estado.carrossel
  const { posicao, progresso } = usePosicaoCarrossel(dados, estado.servidor_agora)
  if (!dados || dados.total === 0) return null
  const numero = estado.bloco ? String(estado.bloco.numero).padStart(2, '0') : ''

  if (posicao >= dados.total) {
    return <ResumoCarrossel estado={estado} numero={numero} reduzir={reduzir} />
  }

  const slide = dados.slides[posicao]
  // Abaixo de 1 s por ganhador, a entrada animada (0,45 s) comeria o tempo do
  // slide: a troca passa a ser direta.
  const rapido = dados.duracao_s < 1
  return (
    <AnuncioGanhador
      key={posicao}
      reduzir={reduzir || rapido}
      subtitulo={`DO BLOCO ${numero}`}
      dados={{
        nome: slide.ganhador_nome,
        setor: slide.ganhador_setor,
        fotoUrl: slide.ganhador_foto_url,
        numero: slide.ganhador_numero,
        matricula: slide.ganhador_matricula_da_sorte,
        premioNome: slide.premio_nome,
        premioDescricao: slide.premio_descricao,
        premioImagemUrl: slide.premio_imagem_url,
      }}
      rodape={
        <div className="relative z-10 mx-auto mt-[3vh] flex max-w-3xl items-center gap-4">
          <span className="shrink-0 text-lg font-semibold tabular-nums opacity-80 sm:text-xl">
            {posicao + 1} de {dados.total}
          </span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/15">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.round(progresso * 100)}%`,
                background: 'var(--cor-primaria)',
                transition: progresso === 0 ? 'none' : 'width 0.2s linear',
              }}
            />
          </div>
          {dados.pausado && (
            <span className="shrink-0 rounded-full border borda-ouro px-3 py-1 text-sm uppercase tracking-widest">
              Pausado
            </span>
          )}
        </div>
      }
    />
  )
}

function ResumoCarrossel({
  estado,
  numero,
  reduzir,
}: {
  estado: TelaoEstado
  numero: string
  reduzir: boolean
}) {
  const slides = estado.carrossel?.slides ?? []
  // Mais ganhadores = mais colunas e pílulas menores, tudo proporcional à tela
  // (--u): cabe inteiro no telão, com o nome em até duas linhas (sem cortar).
  const { colunas, escala, largura } = gradeResumo(slides.length)
  const u = (n: number) => `calc(${n * escala} * var(--u))`
  return (
    <div className={`flex w-full flex-col items-center ${reduzir ? '' : 'animate-sobe-suave'}`}>
      <p className="text-center font-semibold uppercase tracking-[0.15em] opacity-70" style={{ fontSize: 'calc(30 * var(--u))' }}>
        Bloco {numero}
      </p>
      <h2 className="text-center font-exibicao font-bold texto-ouro" style={{ fontSize: 'calc(76 * var(--u))', lineHeight: 1.1 }}>
        Parabéns aos ganhadores!
      </h2>
      <ul
        className="grid"
        style={{
          width: `min(100%, calc(${largura} * var(--u)))`,
          marginTop: u(40),
          gap: u(14),
          gridTemplateColumns: `repeat(${colunas}, minmax(0, 1fr))`,
        }}
      >
        {slides.map((s, i) => (
          <li
            key={`${s.premio_nome}-${s.unidade_numero}-${i}`}
            className={`flex items-center rounded-lg border borda-ouro bg-white/5 ${reduzir ? '' : 'animate-slide-entra'}`}
            style={{
              gap: u(14),
              padding: `${u(12)} ${u(16)}`,
              ...(reduzir ? {} : { animationDelay: `${Math.min(i, 24) * 60}ms` }),
            }}
          >
            <FotoGanhador
              url={s.ganhador_foto_url}
              nome={s.ganhador_nome}
              className="shrink-0 border-2"
              estilo={{ width: u(64), height: u(64), fontSize: u(64) }}
            />
            <div className="min-w-0">
              <p className="line-clamp-2 break-words font-bold leading-tight texto-ouro" style={{ fontSize: u(24) }}>
                {s.ganhador_nome}
              </p>
              <p className="line-clamp-2 break-words opacity-80" style={{ fontSize: u(17), marginTop: u(2) }}>
                {s.ganhador_matricula_da_sorte ? (
                  <span className="tabular-nums">{ROTULO_MATRICULA_TELAO} {s.ganhador_matricula_da_sorte} · </span>
                ) : (
                  s.ganhador_numero != null && <span className="tabular-nums">Nº {s.ganhador_numero} · </span>
                )}
                {s.premio_nome}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Encerramento({ estado }: { estado: TelaoEstado }) {
  const galeria = estado.galeria
  const rolagemRef = useRef<HTMLDivElement | null>(null)

  const rolar = useCallback((direcao: number) => {
    rolagemRef.current?.scrollBy({ left: direcao * 420, behavior: 'smooth' })
  }, [])

  return (
    <div className="w-full animate-sobe-suave">
      <h2 className="text-center text-4xl font-bold leading-tight texto-ouro sm:text-6xl">
        {estado.evento.mensagem_encerramento}
      </h2>

      {galeria.length === 0 ? (
        <p className="mt-10 text-center text-xl opacity-70">Nenhum prêmio foi sorteado.</p>
      ) : (
        <>
          <p className="mt-6 text-center text-lg uppercase tracking-[0.12em] opacity-70 sm:text-xl">
            {galeria.length} ganhador(es)
          </p>
          <div
            ref={rolagemRef}
            className="mt-6 flex gap-4 overflow-x-auto pb-4"
            style={{ scrollbarWidth: 'thin' }}
          >
            {galeria.map((item, indice) => (
              <div
                key={`${item.premio_nome}-${item.unidade_numero}-${indice}`}
                className="w-56 shrink-0 rounded-lg border-2 borda-ouro p-3 text-center sm:w-64"
              >
                <ImagemPremio
                  url={item.premio_imagem_url}
                  nome={item.premio_nome}
                  className="h-28 w-full rounded-lg sm:h-32"
                />
                <p className="mt-3 truncate text-base font-semibold opacity-80">
                  {item.premio_nome}
                </p>
                <p className="mt-1 break-words text-lg font-bold texto-ouro">
                  {item.ganhador_nome}
                </p>
                {item.ganhador_matricula_da_sorte ? (
                  <p className="break-words text-base font-semibold tabular-nums opacity-90">
                    {ROTULO_MATRICULA_TELAO} {item.ganhador_matricula_da_sorte}
                  </p>
                ) : (
                  item.ganhador_numero != null && (
                    <p className="text-base font-semibold tabular-nums opacity-90">Nº {item.ganhador_numero}</p>
                  )
                )}
                <p className="truncate text-sm opacity-70">{item.ganhador_setor}</p>
              </div>
            ))}
          </div>
          {galeria.some((item) => item.premio_imagem_url) && (
            <p className="mb-3 text-center text-sm italic opacity-70">Imagens meramente ilustrativas</p>
          )}
          {galeria.length > 3 && (
            <div className="flex justify-center gap-3">
              <button
                type="button"
                onClick={() => rolar(-1)}
                className="rounded-full border-2 borda-ouro px-5 py-2 text-lg"
              >
                ←
              </button>
              <button
                type="button"
                onClick={() => rolar(1)}
                className="rounded-full border-2 borda-ouro px-5 py-2 text-lg"
              >
                →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
