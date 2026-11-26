import { useEffect, useRef, useState } from 'react'
import AjusteFoto from './AjusteFoto'

export interface FotoPronta {
  conteudo: Blob
  nome: string
  url: string
}

const LADO_MAXIMO = 1280
const LIMITE_ORIGINAL = 20 * 1024 * 1024

/** Câmera ao vivo só existe em contexto seguro (HTTPS ou localhost). */
function cameraAoVivoDisponivel(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  )
}

function mensagemDeErroDaCamera(erro: unknown): string {
  const nome = erro instanceof DOMException ? erro.name : ''
  if (nome === 'NotAllowedError' || nome === 'SecurityError')
    return 'O acesso à câmera foi negado. Libere a câmera nas permissões do navegador ou use “Tirar foto com o celular”.'
  if (nome === 'NotFoundError' || nome === 'OverconstrainedError')
    return 'Nenhuma câmera foi encontrada neste aparelho. Envie uma foto da galeria.'
  if (nome === 'NotReadableError')
    return 'A câmera está sendo usada por outro aplicativo. Feche-o e tente de novo.'
  return 'Não foi possível abrir a câmera. Use “Tirar foto com o celular” ou envie da galeria.'
}

/** Reduz e normaliza para JPEG antes do envio (rede do evento costuma ser lenta). */
async function prepararImagem(origem: Blob): Promise<Blob> {
  const url = URL.createObjectURL(origem)
  try {
    const imagem = await new Promise<HTMLImageElement>((resolver, rejeitar) => {
      const img = new Image()
      img.onload = () => resolver(img)
      img.onerror = () => rejeitar(new Error('imagem'))
      img.src = url
    })
    const escala = Math.min(1, LADO_MAXIMO / Math.max(imagem.naturalWidth, imagem.naturalHeight))
    const largura = Math.max(1, Math.round(imagem.naturalWidth * escala))
    const altura = Math.max(1, Math.round(imagem.naturalHeight * escala))
    const tela = document.createElement('canvas')
    tela.width = largura
    tela.height = altura
    tela.getContext('2d')?.drawImage(imagem, 0, 0, largura, altura)
    return await new Promise<Blob>((resolver, rejeitar) =>
      tela.toBlob((blob) => (blob ? resolver(blob) : rejeitar(new Error('jpeg'))), 'image/jpeg', 0.85),
    )
  } finally {
    URL.revokeObjectURL(url)
  }
}

export default function CapturaFoto({
  foto,
  aoMudar,
}: {
  foto: FotoPronta | null
  aoMudar: (foto: FotoPronta | null) => void
}) {
  const [modo, setModo] = useState<'escolha' | 'camera' | 'ajuste'>('escolha')
  const [erro, setErro] = useState('')
  const [processando, setProcessando] = useState(false)
  // Imagem escolhida/capturada, antes do enquadramento (fica para "Ajustar de novo").
  const [original, setOriginal] = useState<Blob | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const fluxoRef = useRef<MediaStream | null>(null)
  const aoVivo = cameraAoVivoDisponivel()

  const pararCamera = () => {
    fluxoRef.current?.getTracks().forEach((t) => t.stop())
    fluxoRef.current = null
  }
  useEffect(() => pararCamera, [])

  async function abrirCamera() {
    setErro('')
    try {
      const fluxo = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 1280 } },
        audio: false,
      })
      fluxoRef.current = fluxo
      setModo('camera')
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = fluxo
          void videoRef.current.play().catch(() => undefined)
        }
      })
    } catch (e) {
      setErro(mensagemDeErroDaCamera(e))
    }
  }

  async function usar(origem: Blob) {
    setProcessando(true)
    setErro('')
    try {
      const jpeg = await prepararImagem(origem)
      if (foto) URL.revokeObjectURL(foto.url)
      aoMudar({ conteudo: jpeg, nome: 'foto.jpg', url: URL.createObjectURL(jpeg) })
    } catch {
      setErro('Não foi possível ler esta imagem. Use uma foto JPG ou PNG.')
    } finally {
      setProcessando(false)
    }
  }

  function capturar() {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const tela = document.createElement('canvas')
    tela.width = video.videoWidth
    tela.height = video.videoHeight
    const contexto = tela.getContext('2d')
    if (!contexto) return
    // Espelha como a pessoa se vê na pré-visualização da câmera frontal.
    contexto.translate(tela.width, 0)
    contexto.scale(-1, 1)
    contexto.drawImage(video, 0, 0)
    tela.toBlob((blob) => {
      pararCamera()
      if (blob) ajustar(blob)
      else setModo('escolha')
    }, 'image/jpeg', 0.9)
  }

  /** Abre o enquadramento (arrastar, zoom, girar) antes de usar a foto. */
  function ajustar(origem: Blob) {
    setErro('')
    setOriginal(origem)
    setModo('ajuste')
  }

  function aoEscolherArquivo(evento: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = evento.target.files?.[0]
    evento.target.value = ''
    if (!arquivo) return
    if (!arquivo.type.startsWith('image/')) {
      setErro('O arquivo escolhido não é uma imagem.')
      return
    }
    if (arquivo.size > LIMITE_ORIGINAL) {
      setErro('A imagem é grande demais (máximo 20 MB).')
      return
    }
    ajustar(arquivo)
  }

  function refazer() {
    if (foto) URL.revokeObjectURL(foto.url)
    aoMudar(null)
    setOriginal(null)
    setModo('escolha')
    setErro('')
  }

  if (modo === 'ajuste' && original) {
    return (
      <AjusteFoto
        portal
        fonte={original}
        aoConfirmar={async (recorte) => {
          await usar(recorte)
          setModo('escolha')
        }}
        aoCancelar={() => {
          setModo('escolha')
          if (!foto) setOriginal(null)
        }}
        textoCancelar={foto ? 'Cancelar' : 'Escolher outra'}
      />
    )
  }

  if (foto) {
    return (
      <div className="space-y-4 text-center">
        <img
          src={foto.url}
          alt="Pré-visualização da sua foto"
          className="mx-auto aspect-square w-48 rounded-full border-4 border-mallory-claro object-cover ring-2 ring-mallory-laranja"
        />
        <p className="text-sm text-slate-600">Seu rosto está bem visível? Se não, ajuste ou tire outra.</p>
        {original && (
          <button type="button" className="rec-btn-neutro w-full" onClick={() => setModo('ajuste')}>
            Ajustar enquadramento
          </button>
        )}
        <button type="button" className="rec-btn-neutro w-full" onClick={refazer}>
          Refazer foto
        </button>
      </div>
    )
  }

  if (modo === 'camera') {
    return (
      <div className="space-y-3">
        <div className="relative mx-auto aspect-square w-full max-w-[280px] overflow-hidden rounded-xl bg-mallory-preto">
          <video
            ref={videoRef}
            playsInline
            muted
            className="h-full w-full -scale-x-100 object-cover"
          />
        </div>
        <button type="button" className="rec-btn-primario w-full" onClick={capturar}>
          Capturar foto
        </button>
        <button
          type="button"
          className="rec-btn-neutro w-full"
          onClick={() => {
            pararCamera()
            setModo('escolha')
          }}
        >
          Cancelar
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {erro && (
        <p role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
          {erro}
        </p>
      )}
      {processando && <p className="text-sm text-slate-500">Preparando a foto...</p>}
      {aoVivo && (
        <button type="button" className="rec-btn-primario w-full" onClick={() => void abrirCamera()}>
          Abrir câmera
        </button>
      )}
      {/* capture="user" abre a câmera nativa do celular, inclusive sem HTTPS. */}
      <label className={`${aoVivo ? 'rec-btn-neutro' : 'rec-btn-primario'} w-full cursor-pointer`}>
        Tirar foto com o celular
        <input type="file" accept="image/*" capture="user" className="sr-only" onChange={aoEscolherArquivo} />
      </label>
      <label className="rec-btn-neutro w-full cursor-pointer">
        Escolher da galeria
        <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={aoEscolherArquivo} />
      </label>
    </div>
  )
}
