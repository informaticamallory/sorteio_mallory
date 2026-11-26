import { useEffect, useState } from 'react'
import { requisitar } from '../api'
import PortalQrCode from '../componentes/PortalQrCode'
import UploadImagem from '../componentes/UploadImagem'
import { Aviso } from '../componentes/ui'
import type { Evento } from '../types'
import { usePainel } from './PainelLayout'

const FUSOS = [
  'America/Sao_Paulo',
  'America/Manaus',
  'America/Belem',
  'America/Cuiaba',
  'America/Rio_Branco',
  'America/Fortaleza',
  'UTC',
]

type Formulario = Pick<
  Evento,
  | 'nome'
  | 'empresa_nome'
  | 'logo_url'
  | 'cor_fundo'
  | 'cor_primaria'
  | 'cor_texto'
  | 'cor_destaque'
  | 'mensagem_boas_vindas'
  | 'mensagem_encerramento'
  | 'regras_participacao'
  | 'som_ativado'
  | 'reduzir_animacoes'
  | 'duracao_animacao_ms'
  | 'fuso_horario'
  | 'carrossel_segundos'
  | 'recepcao_publica_ativa'
  | 'autocadastro_ativo'
  | 'autocadastro_inicio'
  | 'autocadastro_fim'
>

/** "2026-12-01T21:00:00" (UTC do banco) -> "2026-12-01T18:00" (campo local). */
function paraCampoLocal(utc: string | null): string {
  if (!utc) return ''
  const data = new Date(utc.endsWith('Z') ? utc : `${utc}Z`)
  const local = new Date(data.getTime() - data.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

/** Campo local -> ISO em UTC (o backend grava UTC). Vazio remove o limite. */
function deCampoLocal(valor: string): string | null {
  return valor ? new Date(valor).toISOString() : null
}

function Cor({
  rotulo,
  valor,
  aoMudar,
}: {
  rotulo: string
  valor: string
  aoMudar: (v: string) => void
}) {
  return (
    <div>
      <span className="rotulo">{rotulo}</span>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={rotulo}
          value={valor}
          onChange={(e) => aoMudar(e.target.value)}
          className="h-10 w-14 cursor-pointer rounded border border-slate-300 bg-white p-1"
        />
        <input
          className="campo font-mono uppercase"
          value={valor}
          onChange={(e) => aoMudar(e.target.value)}
          maxLength={7}
        />
      </div>
    </div>
  )
}

export default function Configuracao() {
  const { evento, recarregarEvento } = usePainel()
  const [form, setForm] = useState<Formulario | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [mensagem, setMensagem] = useState('')
  const [erro, setErro] = useState('')

  useEffect(() => {
    setForm({
      nome: evento.nome,
      empresa_nome: evento.empresa_nome,
      logo_url: evento.logo_url,
      cor_fundo: evento.cor_fundo,
      cor_primaria: evento.cor_primaria,
      cor_texto: evento.cor_texto,
      cor_destaque: evento.cor_destaque,
      mensagem_boas_vindas: evento.mensagem_boas_vindas,
      mensagem_encerramento: evento.mensagem_encerramento,
      regras_participacao: evento.regras_participacao,
      som_ativado: evento.som_ativado,
      reduzir_animacoes: evento.reduzir_animacoes,
      duracao_animacao_ms: evento.duracao_animacao_ms,
      fuso_horario: evento.fuso_horario,
      carrossel_segundos: evento.carrossel_segundos,
      recepcao_publica_ativa: evento.recepcao_publica_ativa,
      autocadastro_ativo: evento.autocadastro_ativo,
      autocadastro_inicio: evento.autocadastro_inicio,
      autocadastro_fim: evento.autocadastro_fim,
    })
  }, [evento])

  if (!form) return null
  const atualizar = (campos: Partial<Formulario>) => setForm({ ...form, ...campos })

  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    setSalvando(true)
    setErro('')
    setMensagem('')
    try {
      await requisitar(`/api/events/${evento.id}`, { metodo: 'PATCH', corpo: form })
      await recarregarEvento()
      setMensagem('Configuração salva. O telão foi atualizado automaticamente.')
    } catch (erroSalvar) {
      setErro(erroSalvar instanceof Error ? erroSalvar.message : 'Falha ao salvar')
    } finally {
      setSalvando(false)
    }
  }

  const urlTelao = `${window.location.origin}/telao/${evento.telao_token}`

  return (
    <form onSubmit={salvar} className="space-y-5">
      {mensagem && <Aviso tipo="sucesso">{mensagem}</Aviso>}
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <section className="cartao p-5">
        <h2 className="mb-4 font-semibold text-slate-900">Identificação</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="rotulo" htmlFor="cfg-nome">
              Nome do evento
            </label>
            <input
              id="cfg-nome"
              className="campo"
              required
              value={form.nome}
              onChange={(e) => atualizar({ nome: e.target.value })}
            />
          </div>
          <div>
            <label className="rotulo" htmlFor="cfg-empresa">
              Nome da empresa
            </label>
            <input
              id="cfg-empresa"
              className="campo"
              value={form.empresa_nome}
              onChange={(e) => atualizar({ empresa_nome: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <UploadImagem
              url={form.logo_url}
              rotulo="Logo da empresa"
              aoMudar={(url) => atualizar({ logo_url: url })}
            />
          </div>
        </div>
      </section>

      <section className="cartao p-5">
        <h2 className="mb-1 font-semibold text-slate-900">Cores da apresentação</h2>
        <p className="mb-4 text-sm text-slate-500">
          Mantenha bom contraste entre fundo e texto para leitura à distância.
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Cor rotulo="Fundo" valor={form.cor_fundo} aoMudar={(v) => atualizar({ cor_fundo: v })} />
          <Cor
            rotulo="Destaque (dourado)"
            valor={form.cor_primaria}
            aoMudar={(v) => atualizar({ cor_primaria: v })}
          />
          <Cor rotulo="Texto" valor={form.cor_texto} aoMudar={(v) => atualizar({ cor_texto: v })} />
          <Cor
            rotulo="Realce secundário"
            valor={form.cor_destaque}
            aoMudar={(v) => atualizar({ cor_destaque: v })}
          />
        </div>
        <div
          className="mt-4 rounded-lg p-5 text-center"
          style={{ background: form.cor_fundo, color: form.cor_texto }}
        >
          <p className="text-sm opacity-80">Prévia do telão</p>
          <p className="text-2xl font-semibold" style={{ color: form.cor_primaria }}>
            Parabéns, Maria de Souza!
          </p>
        </div>
      </section>

      <section className="cartao p-5">
        <h2 className="mb-4 font-semibold text-slate-900">Mensagens e regras</h2>
        <div className="space-y-4">
          <div>
            <label className="rotulo" htmlFor="cfg-boas-vindas">
              Mensagem de boas-vindas
            </label>
            <textarea
              id="cfg-boas-vindas"
              className="campo"
              rows={2}
              value={form.mensagem_boas_vindas}
              onChange={(e) => atualizar({ mensagem_boas_vindas: e.target.value })}
            />
          </div>
          <div>
            <label className="rotulo" htmlFor="cfg-encerramento">
              Mensagem de encerramento
            </label>
            <textarea
              id="cfg-encerramento"
              className="campo"
              rows={2}
              value={form.mensagem_encerramento}
              onChange={(e) => atualizar({ mensagem_encerramento: e.target.value })}
            />
          </div>
          <div>
            <label className="rotulo" htmlFor="cfg-regras">
              Regras de participação (texto exibido ao público)
            </label>
            <textarea
              id="cfg-regras"
              className="campo"
              rows={4}
              value={form.regras_participacao}
              onChange={(e) => atualizar({ regras_participacao: e.target.value })}
            />
          </div>
        </div>
      </section>

      <section className="cartao p-5">
        <h2 className="mb-4 font-semibold text-slate-900">Apresentação</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="rotulo" htmlFor="cfg-duracao">
              Duração da animação de suspense: {(form.duracao_animacao_ms / 1000).toFixed(1).replace('.', ',')}s
            </label>
            <input
              id="cfg-duracao"
              type="range"
              min={500}
              max={20000}
              step={500}
              value={form.duracao_animacao_ms}
              onChange={(e) => atualizar({ duracao_animacao_ms: Number(e.target.value) })}
              className="w-full accent-marca-800"
            />
          </div>
          <div>
            <label className="rotulo" htmlFor="cfg-carrossel">
              Tempo de cada ganhador no carrossel: {String(form.carrossel_segundos).replace('.', ',')}s
            </label>
            <input
              id="cfg-carrossel"
              type="range"
              min={0.5}
              max={30}
              step={0.5}
              value={form.carrossel_segundos}
              onChange={(e) => atualizar({ carrossel_segundos: Number(e.target.value) })}
              className="w-full accent-marca-800"
            />
            <p className="mt-1 text-xs text-slate-500">
              Mínimo de 0,5 segundo. Vale a partir da próxima apresentação.
            </p>
          </div>
          <div>
            <label className="rotulo" htmlFor="cfg-fuso">
              Fuso horário do evento
            </label>
            <select
              id="cfg-fuso"
              className="campo"
              value={form.fuso_horario}
              onChange={(e) => atualizar({ fuso_horario: e.target.value })}
            >
              {FUSOS.map((fuso) => (
                <option key={fuso} value={fuso}>
                  {fuso}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slate-500">
              Os horários são gravados em UTC e exibidos neste fuso.
            </p>
          </div>
          <label className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-marca-800"
              checked={form.som_ativado}
              onChange={(e) => atualizar({ som_ativado: e.target.checked })}
            />
            <span className="text-sm text-slate-700">Som ativado no telão</span>
          </label>
          <label className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-marca-800"
              checked={form.reduzir_animacoes}
              onChange={(e) => atualizar({ reduzir_animacoes: e.target.checked })}
            />
            <span className="text-sm text-slate-700">Reduzir animações (acessibilidade)</span>
          </label>
        </div>
      </section>

      <section className="cartao p-5">
        <h2 className="mb-1 font-semibold text-slate-900">Recepção sem login (check-in e consulta)</h2>
        <p className="mb-4 text-sm text-slate-500">
          Libera o botão <strong>Recepção</strong> da tela inicial: qualquer aparelho confirma a presença
          pela matrícula e consulta o número do sorteio, sem senha. Deixe fechada até o dia do evento, para
          ninguém fazer check-in antes da hora. Fechada, a equipe logada continua marcando presença em{' '}
          <strong>Credenciamento</strong>.
        </p>
        <label className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 sm:w-fit">
          <input
            type="checkbox"
            className="h-4 w-4 accent-marca-800"
            checked={form.recepcao_publica_ativa}
            onChange={(e) => atualizar({ recepcao_publica_ativa: e.target.checked })}
          />
          <span className="text-sm text-slate-700">Recepção aberta</span>
          <span
            className={`etiqueta ${
              evento.recepcao_publica_ativa ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'
            }`}
          >
            {evento.recepcao_publica_ativa ? 'Aberta agora' : 'Fechada agora'}
          </span>
        </label>
        <p className="mt-2 text-xs text-slate-500">Salve a configuração para aplicar.</p>
      </section>

      <section className="cartao p-5">
        <h2 className="mb-1 font-semibold text-slate-900">Portal do Colaborador (cadastro pelo QR Code)</h2>
        <p className="mb-4 text-sm text-slate-500">
          O colaborador lê o QR Code, informa matrícula, data de nascimento e os 5 primeiros dígitos
          do CPF (conferidos com a planilha importada), confirma os dados, adiciona uma foto se quiser e
          cria a senha. Depois vê o número da sorte, os prêmios e os avisos. O cadastro não confirma
          presença nem registra pulseira: isso continua no check-in da Recepção. Só vale o primeiro
          cadastro; para refazer, o organizador libera em Credenciamento.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-marca-800"
              checked={form.autocadastro_ativo}
              onChange={(e) => atualizar({ autocadastro_ativo: e.target.checked })}
            />
            <span className="text-sm text-slate-700">Cadastro pelo celular aberto</span>
          </label>
          <div>
            <label className="rotulo" htmlFor="cfg-cad-inicio">
              Disponível a partir de (opcional)
            </label>
            <input
              id="cfg-cad-inicio"
              type="datetime-local"
              className="campo"
              value={paraCampoLocal(form.autocadastro_inicio)}
              onChange={(e) => atualizar({ autocadastro_inicio: deCampoLocal(e.target.value) })}
            />
          </div>
          <div>
            <label className="rotulo" htmlFor="cfg-cad-fim">
              Disponível até (opcional)
            </label>
            <input
              id="cfg-cad-fim"
              type="datetime-local"
              className="campo"
              value={paraCampoLocal(form.autocadastro_fim)}
              onChange={(e) => atualizar({ autocadastro_fim: deCampoLocal(e.target.value) })}
            />
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Salve a configuração para aplicar a abertura e o período. O QR Code não contém dados pessoais.
        </p>
        <div className="mt-4 border-t border-slate-100 pt-4">
          <PortalQrCode key={`${evento.autocadastro_ativo}-${evento.autocadastro_inicio}-${evento.autocadastro_fim}`} eventoId={evento.id} eventoNome={evento.nome} />
        </div>
      </section>

      <section className="cartao p-5">
        <h2 className="mb-1 font-semibold text-slate-900">Link do telão</h2>
        <p className="mb-3 text-sm text-slate-500">
          Abra este endereço no computador ligado ao projetor. Ele não dá acesso ao painel nem à
          lista de participantes.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input className="campo font-mono text-xs" readOnly value={urlTelao} />
          <button
            type="button"
            className="btn-neutro shrink-0"
            onClick={() => void navigator.clipboard?.writeText(urlTelao)}
          >
            Copiar
          </button>
          <button
            type="button"
            className="btn-neutro shrink-0"
            onClick={async () => {
              if (!confirm('Gerar um novo link invalida o link atual. Continuar?')) return
              await requisitar(`/api/events/${evento.id}/telao/novo-token`, { metodo: 'POST' })
              await recarregarEvento()
            }}
          >
            Gerar novo link
          </button>
        </div>
      </section>

      <div className="sticky bottom-0 -mx-4 border-t border-borda bg-white px-4 py-3 sm:-mx-6 sm:px-6">
        <button type="submit" className="btn-primario w-full sm:w-auto" disabled={salvando}>
          {salvando ? 'Salvando...' : 'Salvar configuração'}
        </button>
      </div>
    </form>
  )
}
