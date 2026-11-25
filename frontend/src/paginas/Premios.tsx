import { useCallback, useEffect, useState } from 'react'
import { baixarArquivo, enviarArquivo, requisitar } from '../api'
import UploadImagem from '../componentes/UploadImagem'
import { Aviso, Carregando, ImagemPremio, Modal, Vazio } from '../componentes/ui'
import type { Premio } from '../types'
import { usePainel } from './PainelLayout'
import Icone from '../componentes/Icone'

interface FormPremio {
  id?: number
  nome: string
  descricao: string
  imagem_url: string | null
  quantidade: number
}

const VAZIO: FormPremio = { nome: '', descricao: '', imagem_url: null, quantidade: 1 }

// Modo de visualização escolhido por quem usa (fica salvo neste navegador).
type Visualizacao = 'lista' | 'colunas'
const CHAVE_VISUALIZACAO = 'sorteio.premios_visualizacao'

function lerVisualizacao(): Visualizacao {
  try {
    return localStorage.getItem(CHAVE_VISUALIZACAO) === 'colunas' ? 'colunas' : 'lista'
  } catch {
    return 'lista'
  }
}

function classeUnidade(status: string): string {
  return status === 'disponivel'
    ? 'bg-sky-100 text-sky-800'
    : status === 'sorteado'
      ? 'bg-amber-100 text-amber-800'
      : 'bg-emerald-100 text-emerald-800'
}

export default function Premios() {
  const { evento, recarregarResumo } = usePainel()
  const [lista, setLista] = useState<Premio[] | null>(null)
  const [form, setForm] = useState<FormPremio | null>(null)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [visualizacao, setVisualizacao] = useState<Visualizacao>(lerVisualizacao)
  const [importando, setImportando] = useState(false)

  const carregar = useCallback(async () => {
    try {
      setLista(await requisitar<Premio[]>(`/api/events/${evento.id}/premios`))
      setErro('')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao carregar prêmios')
    }
  }, [evento.id])

  useEffect(() => {
    void carregar()
  }, [carregar])

  function escolherVisualizacao(modo: Visualizacao) {
    setVisualizacao(modo)
    try {
      localStorage.setItem(CHAVE_VISUALIZACAO, modo)
    } catch {
      /* fica só nesta tela */
    }
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    setSalvando(true)
    setErro('')
    try {
      const corpo = {
        nome: form.nome,
        descricao: form.descricao || null,
        imagem_url: form.imagem_url,
        quantidade: form.quantidade,
      }
      if (form.id) {
        await requisitar(`/api/events/${evento.id}/premios/${form.id}`, {
          metodo: 'PATCH',
          corpo,
        })
      } else {
        await requisitar(`/api/events/${evento.id}/premios`, { metodo: 'POST', corpo })
      }
      setForm(null)
      await carregar()
      await recarregarResumo()
    } catch (erroSalvar) {
      setErro(erroSalvar instanceof Error ? erroSalvar.message : 'Falha ao salvar')
    } finally {
      setSalvando(false)
    }
  }

  async function mover(indice: number, direcao: -1 | 1) {
    if (!lista) return
    const destino = indice + direcao
    if (destino < 0 || destino >= lista.length) return
    const nova = [...lista]
    ;[nova[indice], nova[destino]] = [nova[destino], nova[indice]]
    setLista(nova)
    await requisitar(`/api/events/${evento.id}/premios/reordenar`, {
      metodo: 'POST',
      corpo: { ordem: nova.map((p) => p.id) },
    })
    await carregar()
  }

  /** Abre o formulário já preenchido com uma cópia: é só conferir e salvar. */
  function duplicar(premio: Premio) {
    setAviso('')
    setForm({
      nome: `${premio.nome} (cópia)`.slice(0, 200),
      descricao: premio.descricao ?? '',
      imagem_url: premio.imagem_url,
      quantidade: premio.quantidade,
    })
  }

  async function excluir(premio: Premio) {
    const ganhadores = premio.unidades.filter((u) => u.status !== 'disponivel').length
    const avisoGanhadores =
      ganhadores > 0
        ? `\n\n${ganhadores} unidade(s) já têm ganhador. Os resultados continuam no Histórico e na Central de Entregas; as unidades que faltam sortear saem do sorteio.`
        : ''
    if (!confirm(`Excluir o prêmio "${premio.nome}"?${avisoGanhadores}`)) return
    setErro('')
    try {
      await requisitar(`/api/events/${evento.id}/premios/${premio.id}`, { metodo: 'DELETE' })
      await carregar()
      await recarregarResumo()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao excluir')
    }
  }

  function acoes(premio: Premio, indice: number, total: number) {
    const classe = 'rounded px-2 py-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30'
    return (
      <div className="flex shrink-0 gap-1">
        <button type="button" className={classe} disabled={indice === 0} onClick={() => void mover(indice, -1)} title="Subir">
          <Icone nome="acima" className="h-4 w-4" />
        </button>
        <button type="button" className={classe} disabled={indice === total - 1} onClick={() => void mover(indice, 1)} title="Descer">
          <Icone nome="abaixo" className="h-4 w-4" />
        </button>
        <button
          type="button"
          className={classe}
          title="Editar"
          onClick={() =>
            setForm({
              id: premio.id,
              nome: premio.nome,
              descricao: premio.descricao ?? '',
              imagem_url: premio.imagem_url,
              quantidade: premio.quantidade,
            })
          }
        >
          <Icone nome="editar" className="h-4 w-4" />
        </button>
        <button type="button" className={classe} title="Duplicar (cria uma cópia para você ajustar)" onClick={() => duplicar(premio)}>
          <Icone nome="copiar" className="h-4 w-4" />
        </button>
        <button type="button" className="rounded px-2 py-1 text-rose-500 hover:bg-rose-50" title="Excluir" onClick={() => void excluir(premio)}>
          <Icone nome="excluir" className="h-4 w-4" />
        </button>
      </div>
    )
  }

  const botaoModo = (modo: Visualizacao, rotulo: string, icone: 'lista' | 'grade') => (
    <button
      type="button"
      onClick={() => escolherVisualizacao(modo)}
      aria-pressed={visualizacao === modo}
      title={`Ver em ${rotulo.toLowerCase()}`}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${
        visualizacao === modo ? 'bg-white text-marca-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'
      }`}
    >
      <Icone nome={icone} className="h-4 w-4" />
      {rotulo}
    </button>
  )

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {aviso && <Aviso tipo="sucesso">{aviso}</Aviso>}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">A ordem define a sequência de apresentação durante o evento.</p>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg bg-slate-100 p-1" role="group" aria-label="Modo de visualização">
            {botaoModo('lista', 'Lista', 'lista')}
            {botaoModo('colunas', 'Colunas', 'grade')}
          </div>
          <button type="button" className="btn-neutro" onClick={() => setImportando(true)}>
            <Icone nome="baixar" className="h-4 w-4 rotate-180" />
            Importar planilha
          </button>
          <button type="button" className="btn-primario" onClick={() => setForm({ ...VAZIO })}>
            Novo prêmio
          </button>
        </div>
      </div>

      {lista === null ? (
        <Carregando />
      ) : lista.length === 0 ? (
        <Vazio titulo="Nenhum prêmio cadastrado" descricao="Cadastre os prêmios ou importe uma planilha antes do evento." />
      ) : visualizacao === 'colunas' ? (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {lista.map((premio, indice) => {
            const disponiveis = premio.unidades.filter((u) => u.status === 'disponivel').length
            return (
              <li key={premio.id} className="cartao flex flex-col overflow-hidden">
                <div className="aspect-[4/3] w-full border-b border-slate-200 bg-slate-50 p-3">
                  <ImagemPremio url={premio.imagem_url} nome={premio.nome} className="h-full w-full text-slate-400" />
                </div>
                <div className="flex flex-1 flex-col gap-2 p-3">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-slate-900">
                      <span className="mr-1.5 text-sm text-slate-400">#{indice + 1}</span>
                      {premio.nome}
                    </h3>
                    {premio.descricao && <p className="line-clamp-2 text-sm text-slate-500">{premio.descricao}</p>}
                  </div>
                  <p className="text-xs text-slate-600">
                    {premio.quantidade} unidade(s) · <span className="text-sky-700">{disponiveis} disponível(is)</span>
                    {premio.quantidade - disponiveis > 0 && (
                      <span className="text-amber-700"> · {premio.quantidade - disponiveis} sorteada(s)</span>
                    )}
                  </p>
                  <div className="mt-auto flex justify-end border-t border-slate-100 pt-2">{acoes(premio, indice, lista.length)}</div>
                </div>
              </li>
            )
          })}
        </ul>
      ) : (
        <ul className="space-y-3">
          {lista.map((premio, indice) => (
            <li key={premio.id} className="cartao p-4">
              <div className="flex gap-4">
                <div className="h-24 w-24 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                  <ImagemPremio url={premio.imagem_url} nome={premio.nome} className="h-full w-full text-slate-400" />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="font-semibold text-slate-900">
                        <span className="mr-2 text-sm text-slate-400">#{indice + 1}</span>
                        {premio.nome}
                      </h3>
                      {premio.descricao && <p className="mt-0.5 text-sm text-slate-500">{premio.descricao}</p>}
                    </div>
                    {acoes(premio, indice, lista.length)}
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {premio.unidades.map((unidade) => (
                      <span
                        key={unidade.id}
                        className={`etiqueta gap-1 ${classeUnidade(unidade.status)}`}
                        title={unidade.ganhador_nome ?? 'Disponível'}
                      >
                        {premio.quantidade > 1 && `Un. ${unidade.numero} · `}
                        {unidade.ganhador_nome ?? 'Disponível'}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal titulo={form?.id ? 'Editar prêmio' : 'Novo prêmio'} aberto={form !== null} aoFechar={() => setForm(null)}>
        {form && (
          <form onSubmit={salvar} className="space-y-4">
            <div>
              <label className="rotulo" htmlFor="pr-nome">
                Nome do prêmio
              </label>
              <input
                id="pr-nome"
                className="campo"
                required
                autoFocus
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
              />
            </div>
            <div>
              <label className="rotulo" htmlFor="pr-descricao">
                Descrição (opcional)
              </label>
              <textarea
                id="pr-descricao"
                className="campo"
                rows={2}
                value={form.descricao}
                onChange={(e) => setForm({ ...form, descricao: e.target.value })}
              />
            </div>
            <div>
              <label className="rotulo" htmlFor="pr-quantidade">
                Quantidade de unidades
              </label>
              <input
                id="pr-quantidade"
                type="number"
                min={1}
                max={500}
                className="campo"
                value={form.quantidade}
                onChange={(e) => setForm({ ...form, quantidade: Number(e.target.value) })}
              />
              <p className="mt-1 text-xs text-slate-500">
                Cada unidade é sorteada em uma rodada própria, com ganhador identificado.
              </p>
            </div>
            <UploadImagem
              url={form.imagem_url}
              rotulo="Imagem do produto"
              aoMudar={(url) => setForm({ ...form, imagem_url: url })}
            />
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" className="btn-neutro" onClick={() => setForm(null)}>
                Cancelar
              </button>
              <button type="submit" className="btn-primario" disabled={salvando}>
                {salvando ? 'Salvando...' : 'Salvar'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <ModalImportarPremios
        aberto={importando}
        eventId={evento.id}
        aoFechar={() => setImportando(false)}
        aoConcluir={async (texto) => {
          setImportando(false)
          setAviso(texto)
          await carregar()
          await recarregarResumo()
        }}
      />
    </div>
  )
}

interface LinhaPrevia {
  linha: number
  nome: string
  descricao: string | null
  quantidade: number
  erros: string[]
  ja_existe: boolean
  quantidade_atual: number | null
}

interface ResultadoImportacao {
  criados: number
  ignorados: number
  atualizados: number
  nao_atualizados: string[]
}

/** Importação por planilha: lê, mostra a prévia e só grava ao confirmar. */
function ModalImportarPremios({
  aberto,
  eventId,
  aoFechar,
  aoConcluir,
}: {
  aberto: boolean
  eventId: number
  aoFechar: () => void
  aoConcluir: (mensagem: string) => Promise<void>
}) {
  const [linhas, setLinhas] = useState<LinhaPrevia[] | null>(null)
  const [avisos, setAvisos] = useState<string[]>([])
  const [atualizar, setAtualizar] = useState(false)
  const [erro, setErro] = useState('')
  const [lendo, setLendo] = useState(false)
  const [gravando, setGravando] = useState(false)

  useEffect(() => {
    if (!aberto) {
      setLinhas(null)
      setAvisos([])
      setAtualizar(false)
      setErro('')
    }
  }, [aberto])

  async function ler(arquivo: File | undefined) {
    if (!arquivo) return
    setErro('')
    setLendo(true)
    try {
      const previa = await enviarArquivo<{ linhas: LinhaPrevia[]; avisos?: string[] }>(
        `/api/events/${eventId}/premios/importar/previa`,
        arquivo,
      )
      setLinhas(previa.linhas)
      setAvisos(previa.avisos ?? [])
    } catch (e) {
      setLinhas(null)
      setAvisos([])
      setErro(e instanceof Error ? e.message : 'Falha ao ler a planilha')
    } finally {
      setLendo(false)
    }
  }

  const validas = linhas?.filter((l) => l.erros.length === 0) ?? []
  const novas = validas.filter((l) => !l.ja_existe)
  // Já cadastrados cuja quantidade na planilha é diferente da atual.
  const divergentes = validas.filter((l) => l.ja_existe && l.quantidade_atual !== null && l.quantidade_atual !== l.quantidade)
  const enviar = atualizar ? [...novas, ...divergentes] : novas

  async function confirmar() {
    if (enviar.length === 0) return
    setGravando(true)
    setErro('')
    try {
      const feito = await requisitar<ResultadoImportacao>(`/api/events/${eventId}/premios/importar/confirmar`, {
        metodo: 'POST',
        corpo: {
          linhas: enviar.map((l) => ({ nome: l.nome, descricao: l.descricao, quantidade: l.quantidade })),
          atualizar_existentes: atualizar,
        },
      })
      const partes = [`${feito.criados} prêmio(s) importado(s)`]
      if (feito.atualizados) partes.push(`${feito.atualizados} com a quantidade atualizada`)
      if (feito.ignorados) partes.push(`${feito.ignorados} já existia(m) e ficou(aram) como estava(m)`)
      if (feito.nao_atualizados.length)
        partes.push(`não deu para diminuir (já sorteado): ${feito.nao_atualizados.join(', ')}`)
      await aoConcluir(`${partes.join('; ')}. Coloque as imagens em Editar.`)
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao importar')
    } finally {
      setGravando(false)
    }
  }

  return (
    <Modal titulo="Importar prêmios" aberto={aberto} aoFechar={aoFechar} largura="max-w-3xl">
      <div className="space-y-4">
        <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
          <p className="mb-1 font-medium text-slate-800">Colunas: nome (obrigatória), descrição e quantidade</p>
          <p>
            Quantidade em branco vale 1. Prêmios com o mesmo nome de um já cadastrado não são duplicados; se a
            quantidade for diferente, você pode atualizá-la. As imagens são colocadas depois, em Editar.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => void baixarArquivo('/api/premios/modelo.xlsx', 'modelo-premios.xlsx')}>
              <Icone nome="baixar" className="h-4 w-4" /> Baixar modelo XLSX
            </button>
            <button type="button" className="btn-neutro px-3 py-1.5" onClick={() => void baixarArquivo('/api/premios/modelo.csv', 'modelo-premios.csv')}>
              <Icone nome="baixar" className="h-4 w-4" /> Baixar modelo CSV
            </button>
          </div>
        </div>

        <div>
          <label className="rotulo" htmlFor="arquivo-premios">
            Planilha (.xlsx ou .csv)
          </label>
          <input
            id="arquivo-premios"
            type="file"
            accept=".xlsx,.csv"
            className="campo"
            onChange={(e) => void ler(e.target.files?.[0])}
          />
          {lendo && <p className="mt-1 text-xs text-slate-500">Lendo a planilha...</p>}
        </div>

        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {avisos.map((a) => (
          <Aviso key={a} tipo="atencao">
            {a}
          </Aviso>
        ))}

        {divergentes.length > 0 && (
          <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-marca-600"
              checked={atualizar}
              onChange={(e) => setAtualizar(e.target.checked)}
            />
            <span>
              <span className="font-semibold">
                Atualizar a quantidade de {divergentes.length} prêmio(s) já cadastrado(s)
              </span>
              <span className="block text-xs text-amber-800">
                Usa a quantidade da planilha. Unidades já sorteadas nunca são removidas.
              </span>
            </span>
          </label>
        )}

        {linhas && (
          <div className="max-h-80 overflow-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Linha</th>
                  <th className="px-3 py-2">Prêmio</th>
                  <th className="px-3 py-2">Qtd.</th>
                  <th className="px-3 py-2">Situação</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {linhas.map((l) => (
                  <tr key={l.linha}>
                    <td className="px-3 py-1.5 text-slate-500">{l.linha}</td>
                    <td className="px-3 py-1.5">
                      <span className="font-medium text-slate-900">{l.nome || '—'}</span>
                      {l.descricao && <span className="block text-xs text-slate-500">{l.descricao}</span>}
                    </td>
                    <td className="px-3 py-1.5 tabular-nums">{l.quantidade || '—'}</td>
                    <td className="px-3 py-1.5">
                      {l.erros.length > 0 ? (
                        <span className="text-rose-700">{l.erros.join('; ')}</span>
                      ) : l.ja_existe ? (
                        l.quantidade_atual !== null && l.quantidade_atual !== l.quantidade ? (
                          <span className="text-amber-700">
                            {atualizar
                              ? `Já cadastrado: ${l.quantidade_atual} → ${l.quantidade} un.`
                              : `Já cadastrado com ${l.quantidade_atual} un. (fica como está)`}
                          </span>
                        ) : (
                          <span className="text-slate-500">Já cadastrado (fica de fora)</span>
                        )
                      ) : (
                        <span className="text-emerald-700">Pronto para importar</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-neutro" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="button" className="btn-primario" disabled={enviar.length === 0 || gravando} onClick={() => void confirmar()}>
            {gravando
              ? 'Importando...'
              : atualizar && divergentes.length > 0
                ? `Importar ${novas.length} e atualizar ${divergentes.length}`
                : `Importar ${novas.length} prêmio(s)`}
          </button>
        </div>
      </div>
    </Modal>
  )
}
