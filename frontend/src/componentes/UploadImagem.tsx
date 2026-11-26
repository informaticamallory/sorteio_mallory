import { useId, useState } from 'react'
import { enviarArquivo } from '../api'
import AjusteFoto from './AjusteFoto'
import Icone from './Icone'
import { ImagemPremio } from './ui'

const TIPOS_ACEITOS = 'image/jpeg,image/png,image/webp,image/gif'
const LIMITE_MB = 5

export default function UploadImagem({
  url,
  rotulo,
  aoMudar,
  altura = 'h-32',
  retrato = false,
}: {
  url: string | null
  rotulo: string
  aoMudar: (url: string | null) => void
  altura?: string
  /** Foto de perfil: abre o ajuste (enquadrar, zoom, girar) e salva o recorte quadrado. */
  retrato?: boolean
}) {
  const id = useId()
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  // Retrato: arquivo escolhido ou foto atual sendo enquadrada.
  const [ajustando, setAjustando] = useState<Blob | string | null>(null)

  async function enviar(arquivo: File) {
    setEnviando(true)
    try {
      const resposta = await enviarArquivo<{ url: string }>('/api/uploads/imagem', arquivo)
      aoMudar(resposta.url)
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao enviar a imagem')
    } finally {
      setEnviando(false)
    }
  }

  async function selecionar(arquivo: File | undefined) {
    if (!arquivo) return
    setErro('')
    if (!TIPOS_ACEITOS.split(',').includes(arquivo.type)) {
      setErro('Formato não aceito. Use JPG, PNG, WEBP ou GIF.')
      return
    }
    // No retrato o arquivo original não sobe: só o recorte (bem menor).
    if (retrato) {
      if (arquivo.size > 20 * 1024 * 1024) {
        setErro('A imagem é grande demais (máximo 20 MB).')
        return
      }
      setAjustando(arquivo)
      return
    }
    if (arquivo.size > LIMITE_MB * 1024 * 1024) {
      setErro(`A imagem precisa ter até ${LIMITE_MB} MB.`)
      return
    }
    await enviar(arquivo)
  }

  if (ajustando) {
    return (
      <div>
        <span className="rotulo">{rotulo}</span>
        <div className="rounded-lg border border-slate-200 p-3">
          <AjusteFoto
            fonte={ajustando}
            textoCancelar="Cancelar"
            aoCancelar={() => setAjustando(null)}
            aoConfirmar={async (recorte) => {
              await enviar(new File([recorte], 'foto.jpg', { type: 'image/jpeg' }))
              setAjustando(null)
            }}
          />
          {erro && <p className="mt-2 text-xs text-rose-600">{erro}</p>}
        </div>
      </div>
    )
  }

  return (
    <div>
      <span className="rotulo">{rotulo}</span>
      <div className="flex items-start gap-3">
        <div
          className={`shrink-0 overflow-hidden border border-slate-200 bg-slate-50 ${
            retrato ? 'h-32 w-32 rounded-xl' : `w-32 rounded-lg ${altura}`
          }`}
        >
          {retrato && url ? (
            // Como nas listas: preenche o quadrado (as fotos ajustadas já são quadradas).
            <img src={url} alt={rotulo} className="h-full w-full object-cover" />
          ) : (
            <ImagemPremio url={url} nome={rotulo} className="h-full w-full text-slate-400" />
          )}
        </div>
        <div className="flex-1 space-y-2">
          <input
            id={id}
            type="file"
            accept={TIPOS_ACEITOS}
            disabled={enviando}
            onChange={(e) => {
              void selecionar(e.target.files?.[0])
              e.target.value = ''
            }}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border file:border-slate-300
                       file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-medium
                       file:text-slate-700 hover:file:bg-slate-50"
          />
          <p className="text-xs text-slate-500">
            {retrato
              ? 'JPG, PNG, WEBP ou GIF. Depois de escolher, você ajusta o enquadramento.'
              : `JPG, PNG, WEBP ou GIF, até ${LIMITE_MB} MB.`}
          </p>
          {enviando && <p className="text-xs text-marca-700">Enviando imagem...</p>}
          {erro && <p className="text-xs text-rose-600">{erro}</p>}
          <div className="flex flex-wrap gap-3">
            {retrato && url && (
              <button
                type="button"
                className="inline-flex items-center gap-1 text-xs font-medium text-marca-700 hover:underline"
                onClick={() => {
                  setErro('')
                  setAjustando(url)
                }}
              >
                <Icone nome="recortar" className="h-3.5 w-3.5" /> Ajustar
              </button>
            )}
            {url && (
              <button type="button" className="text-xs font-medium text-rose-600 hover:underline" onClick={() => aoMudar(null)}>
                Remover imagem
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
