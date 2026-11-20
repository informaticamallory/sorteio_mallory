import { useId, useState } from 'react'
import { enviarArquivo } from '../api'
import { ImagemPremio } from './ui'

const TIPOS_ACEITOS = 'image/jpeg,image/png,image/webp,image/gif'
const LIMITE_MB = 5

export default function UploadImagem({
  url,
  rotulo,
  aoMudar,
  altura = 'h-32',
}: {
  url: string | null
  rotulo: string
  aoMudar: (url: string | null) => void
  altura?: string
}) {
  const id = useId()
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')

  async function selecionar(arquivo: File | undefined) {
    if (!arquivo) return
    setErro('')
    if (!TIPOS_ACEITOS.split(',').includes(arquivo.type)) {
      setErro('Formato não aceito. Use JPG, PNG, WEBP ou GIF.')
      return
    }
    if (arquivo.size > LIMITE_MB * 1024 * 1024) {
      setErro(`A imagem precisa ter até ${LIMITE_MB} MB.`)
      return
    }
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

  return (
    <div>
      <span className="rotulo">{rotulo}</span>
      <div className="flex items-start gap-3">
        <div className={`w-32 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-50 ${altura}`}>
          <ImagemPremio url={url} nome={rotulo} className="h-full w-full text-slate-400" />
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
          <p className="text-xs text-slate-500">JPG, PNG, WEBP ou GIF, até {LIMITE_MB} MB.</p>
          {enviando && <p className="text-xs text-marca-700">Enviando imagem...</p>}
          {erro && <p className="text-xs text-rose-600">{erro}</p>}
          {url && (
            <button type="button" className="text-xs font-medium text-rose-600 hover:underline" onClick={() => aoMudar(null)}>
              Remover imagem
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
