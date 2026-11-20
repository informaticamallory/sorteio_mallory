const CHAVE_TOKEN = 'sorteio.token'

/** Disparado quando o servidor recusa a sessão (401); o app volta ao login. */
export const EVENTO_SESSAO_ENCERRADA = 'sorteio:sessao-encerrada'

export class ErroApi extends Error {
  status: number
  constructor(mensagem: string, status: number) {
    super(mensagem)
    this.status = status
  }
}

export function lerToken(): string | null {
  try {
    return localStorage.getItem(CHAVE_TOKEN)
  } catch {
    return null
  }
}

export function gravarToken(token: string | null) {
  try {
    if (token) localStorage.setItem(CHAVE_TOKEN, token)
    else localStorage.removeItem(CHAVE_TOKEN)
  } catch {
    /* navegador sem storage: a sessao dura apenas enquanto a aba estiver aberta */
  }
}

async function extrairErro(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json()
    if (typeof corpo?.detail === 'string') return corpo.detail
    if (Array.isArray(corpo?.detail)) {
      return corpo.detail
        .map((d: { loc?: string[]; msg?: string }) => {
          const campo = d.loc?.slice(1).join('.') ?? ''
          return campo ? `${campo}: ${d.msg}` : d.msg
        })
        .join('; ')
    }
  } catch {
    /* resposta sem corpo JSON */
  }
  return `Falha na requisicao (HTTP ${resposta.status})`
}

interface Opcoes {
  metodo?: string
  corpo?: unknown
  autenticado?: boolean
}

export async function requisitar<T>(caminho: string, opcoes: Opcoes = {}): Promise<T> {
  const { metodo = 'GET', corpo, autenticado = true } = opcoes
  const cabecalhos: Record<string, string> = {}
  if (corpo !== undefined) cabecalhos['Content-Type'] = 'application/json'
  if (autenticado) {
    const token = lerToken()
    if (token) cabecalhos.Authorization = `Bearer ${token}`
  }

  const resposta = await fetch(caminho, {
    method: metodo,
    headers: cabecalhos,
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  })

  if (resposta.status === 401 && autenticado) {
    gravarToken(null)
    window.dispatchEvent(new Event(EVENTO_SESSAO_ENCERRADA))
    throw new ErroApi('Sessão encerrada. Entre novamente.', 401)
  }
  if (!resposta.ok) throw new ErroApi(await extrairErro(resposta), resposta.status)
  if (resposta.status === 204) return undefined as T
  return (await resposta.json()) as T
}

export async function enviarArquivo<T>(caminho: string, arquivo: File, campo = 'arquivo'): Promise<T> {
  const dados = new FormData()
  dados.append(campo, arquivo)
  const cabecalhos: Record<string, string> = {}
  const token = lerToken()
  if (token) cabecalhos.Authorization = `Bearer ${token}`

  const resposta = await fetch(caminho, { method: 'POST', headers: cabecalhos, body: dados })
  if (!resposta.ok) throw new ErroApi(await extrairErro(resposta), resposta.status)
  return (await resposta.json()) as T
}

/** Envia um formulario multipart sem sessao (autocadastro). */
export async function enviarFormulario<T>(
  caminho: string,
  campos: Record<string, string>,
  arquivos: Record<string, { conteudo: Blob; nome: string }> = {},
): Promise<T> {
  const dados = new FormData()
  for (const [chave, valor] of Object.entries(campos)) dados.append(chave, valor)
  for (const [chave, arquivo] of Object.entries(arquivos)) {
    dados.append(chave, arquivo.conteudo, arquivo.nome)
  }
  const resposta = await fetch(caminho, { method: 'POST', body: dados })
  if (!resposta.ok) throw new ErroApi(await extrairErro(resposta), resposta.status)
  return (await resposta.json()) as T
}

/** Baixa um arquivo protegido por token, preservando o nome sugerido pelo servidor. */
export async function baixarArquivo(caminho: string, nomePadrao: string): Promise<void> {
  const cabecalhos: Record<string, string> = {}
  const token = lerToken()
  if (token) cabecalhos.Authorization = `Bearer ${token}`

  const resposta = await fetch(caminho, { headers: cabecalhos })
  if (!resposta.ok) throw new ErroApi(await extrairErro(resposta), resposta.status)

  const disposicao = resposta.headers.get('Content-Disposition') ?? ''
  const encontrado = /filename="?([^";]+)"?/i.exec(disposicao)
  const nome = encontrado?.[1] ?? nomePadrao

  const blob = await resposta.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = nome
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

/** Le um arquivo protegido por token como Blob (ex.: QR Code em PNG). */
export async function lerBlob(caminho: string): Promise<Blob> {
  const cabecalhos: Record<string, string> = {}
  const token = lerToken()
  if (token) cabecalhos.Authorization = `Bearer ${token}`
  const resposta = await fetch(caminho, { headers: cabecalhos })
  if (!resposta.ok) throw new ErroApi(await extrairErro(resposta), resposta.status)
  return resposta.blob()
}

/** Envia um arquivo (Blob) autenticado, com o nome informado. */
export async function enviarBlob<T>(caminho: string, conteudo: Blob, nome: string, campo = 'foto'): Promise<T> {
  const dados = new FormData()
  dados.append(campo, conteudo, nome)
  const cabecalhos: Record<string, string> = {}
  const token = lerToken()
  if (token) cabecalhos.Authorization = `Bearer ${token}`
  const resposta = await fetch(caminho, { method: 'POST', headers: cabecalhos, body: dados })
  if (!resposta.ok) throw new ErroApi(await extrairErro(resposta), resposta.status)
  return (await resposta.json()) as T
}

/** Chave de idempotencia: um clique = uma chave, reutilizada em novas tentativas. */
export function novaChaveIdempotencia(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}
