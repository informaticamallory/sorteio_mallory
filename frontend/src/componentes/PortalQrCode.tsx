import { useCallback, useEffect, useState } from 'react'
import { lerBlob, requisitar } from '../api'
import type { PortalSituacao } from '../types'
import { Aviso } from './ui'

/**
 * Link e QR Code do cadastro pelo celular (Portal do Colaborador).
 * `compacto`: sem a situação, o campo do link e o "Copiar link" (quem usa já
 * mostra isso numa linha própria, como o Credenciamento).
 */
export default function PortalQrCode({
  eventoId,
  eventoNome,
  compacto = false,
}: {
  eventoId: number
  eventoNome: string
  compacto?: boolean
}) {
  const [situacao, setSituacao] = useState<PortalSituacao | null>(null)
  const [qr, setQr] = useState<string | null>(null)
  const [erro, setErro] = useState('')
  const [copiado, setCopiado] = useState(false)

  const origem = encodeURIComponent(window.location.origin)
  const base = `/api/events/${eventoId}/portal`

  const carregar = useCallback(async () => {
    try {
      setSituacao(await requisitar<PortalSituacao>(`${base}?origem=${origem}`))
      const blob = await lerBlob(`${base}/qrcode.png?origem=${origem}&escala=12`)
      setQr((anterior) => {
        if (anterior) URL.revokeObjectURL(anterior)
        return URL.createObjectURL(blob)
      })
      setErro('')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao gerar o QR Code')
    }
  }, [base, origem])

  useEffect(() => {
    void carregar()
  }, [carregar])

  useEffect(() => () => {
    if (qr) URL.revokeObjectURL(qr)
  }, [qr])

  function baixar() {
    if (!qr) return
    const link = document.createElement('a')
    link.href = qr
    link.download = `qrcode-cadastro-evento-${eventoId}.png`
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  function imprimir() {
    if (!qr || !situacao) return
    const janela = window.open('', '_blank', 'width=720,height=900')
    if (!janela) return
    const doc = janela.document
    doc.title = 'QR Code do cadastro'
    const estilo = doc.createElement('style')
    estilo.textContent =
      'body{font-family:Arial,sans-serif;text-align:center;padding:40px;color:#111}' +
      'h1{font-size:28px;margin:0 0 4px}p{margin:6px 0;color:#444}' +
      // display:block centraliza a imagem sozinha na linha (inline ela dividia a
      // linha com o texto seguinte e ficava deslocada).
      'img{display:block;width:420px;height:420px;margin:32px auto 0}' +
      '.faixa{height:8px;background:#F16425;border-radius:4px;margin:0 auto 24px;width:120px}'
    doc.head.appendChild(estilo)
    const faixa = doc.createElement('div')
    faixa.className = 'faixa'
    const titulo = doc.createElement('h1')
    titulo.textContent = 'Cadastro para o Sorteio'
    const nome = doc.createElement('p')
    nome.textContent = eventoNome
    const instrucao = doc.createElement('p')
    instrucao.textContent = 'Aponte a câmera do celular para o código e siga as instruções.'
    const imagem = doc.createElement('img')
    imagem.src = qr
    imagem.alt = 'QR Code do cadastro'
    // So o QR Code: o link impresso nao e exibido (quem quiser o endereco usa
    // "Copiar link" no painel).
    doc.body.append(faixa, titulo, nome, instrucao, imagem)
    imagem.onload = () => {
      janela.focus()
      janela.print()
    }
  }

  async function copiar() {
    if (!situacao) return
    try {
      await navigator.clipboard.writeText(situacao.url_cadastro)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    } catch {
      setErro('Não foi possível copiar. Selecione o link e copie manualmente.')
    }
  }

  if (erro && !situacao) return <Aviso tipo="erro">{erro}</Aviso>
  if (!situacao) return <p className="text-sm text-slate-500">Gerando QR Code...</p>

  const semIdentificacao = situacao.participantes - situacao.com_identificacao

  return (
    <div className="space-y-3">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="flex shrink-0 justify-center">
          {qr ? (
            <img
              src={qr}
              alt={`QR Code: ${situacao.url_cadastro}`}
              className={`h-44 w-44 rounded-lg border border-slate-200 bg-white p-1 ${situacao.aberto ? '' : 'opacity-40'}`}
            />
          ) : (
            <div className="h-44 w-44 rounded-lg border border-slate-200 bg-slate-50" />
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          {!compacto && (
            <>
              <p className="text-sm">
                Situação:{' '}
                {situacao.aberto ? (
                  <span className="etiqueta bg-emerald-50 text-emerald-700">Cadastro aberto</span>
                ) : situacao.ativo ? (
                  <span className="etiqueta bg-amber-50 text-amber-800">Fora do período</span>
                ) : (
                  <span className="etiqueta bg-slate-100 text-slate-600">Cadastro desativado</span>
                )}
              </p>
              <input className="campo font-mono text-xs" readOnly value={situacao.url_cadastro} aria-label="Link do cadastro" />
            </>
          )}
          <div className="flex flex-wrap gap-2">
            {!compacto && (
              <button type="button" className="btn-neutro" onClick={() => void copiar()}>
                {copiado ? 'Copiado!' : 'Copiar link'}
              </button>
            )}
            <button type="button" className="btn-neutro" onClick={baixar} disabled={!qr}>
              Baixar PNG
            </button>
            <button type="button" className="btn-neutro" onClick={imprimir} disabled={!qr}>
              Imprimir
            </button>
          </div>
          {situacao.aviso_endereco && <p className="text-xs text-amber-800">{situacao.aviso_endereco}</p>}
          <p className="text-xs text-slate-500">
            {situacao.com_identificacao} de {situacao.participantes} participantes com CPF e nascimento importados ·{' '}
            {situacao.cadastrados} já cadastrados.
          </p>
          {semIdentificacao > 0 && (
            <p className="text-xs text-amber-800">
              {semIdentificacao} participante(s) sem CPF e nascimento não conseguem se cadastrar pelo QR Code.
              Reimporte a planilha com essas colunas e marque “Completar CPF e nascimento”.
            </p>
          )}
          {!situacao.push_disponivel && situacao.push_motivo && (
            <p className="text-xs text-slate-500">Notificações no celular: {situacao.push_motivo}</p>
          )}
        </div>
      </div>
    </div>
  )
}
