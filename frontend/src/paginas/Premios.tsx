import { useCallback, useEffect, useState } from 'react'
import { requisitar } from '../api'
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

export default function Premios() {
  const { evento, recarregarResumo } = usePainel()
  const [lista, setLista] = useState<Premio[] | null>(null)
  const [form, setForm] = useState<FormPremio | null>(null)
  const [erro, setErro] = useState('')
  const [salvando, setSalvando] = useState(false)

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

  async function excluir(premio: Premio) {
    const ganhadores = premio.unidades.filter((u) => u.status !== 'disponivel').length
    const aviso =
      ganhadores > 0
        ? `\n\n${ganhadores} unidade(s) já têm ganhador. Os resultados continuam no Histórico e na Central de Entregas; as unidades que faltam sortear saem do sorteio.`
        : ''
    if (!confirm(`Excluir o prêmio "${premio.nome}"?${aviso}`)) return
    setErro('')
    try {
      await requisitar(`/api/events/${evento.id}/premios/${premio.id}`, { metodo: 'DELETE' })
      await carregar()
      await recarregarResumo()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao excluir')
    }
  }

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          A ordem define a sequência de apresentação durante o evento.
        </p>
        <button type="button" className="btn-primario" onClick={() => setForm({ ...VAZIO })}>
          Novo prêmio
        </button>
      </div>

      {lista === null ? (
        <Carregando />
      ) : lista.length === 0 ? (
        <Vazio titulo="Nenhum prêmio cadastrado" descricao="Cadastre os prêmios antes do evento." />
      ) : (
        <ul className="space-y-3">
          {lista.map((premio, indice) => (
            <li key={premio.id} className="cartao p-4">
              <div className="flex gap-4">
                <div className="h-24 w-24 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                  <ImagemPremio
                    url={premio.imagem_url}
                    nome={premio.nome}
                    className="h-full w-full text-slate-400"
                  />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="font-semibold text-slate-900">
                        <span className="mr-2 text-sm text-slate-400">#{indice + 1}</span>
                        {premio.nome}
                      </h3>
                      {premio.descricao && (
                        <p className="mt-0.5 text-sm text-slate-500">{premio.descricao}</p>
                      )}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"
                        disabled={indice === 0}
                        onClick={() => void mover(indice, -1)}
                        title="Subir"
                      >
                        <Icone nome="acima" className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30"
                        disabled={indice === lista.length - 1}
                        onClick={() => void mover(indice, 1)}
                        title="Descer"
                      >
                        <Icone nome="abaixo" className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100"
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
                      <button
                        type="button"
                        className="rounded px-2 py-1 text-rose-500 hover:bg-rose-50"
                        title="Excluir"
                        onClick={() => void excluir(premio)}
                      >
                        <Icone nome="excluir" className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {premio.unidades.map((unidade) => (
                      <span
                        key={unidade.id}
                        className={`etiqueta gap-1 ${
                          unidade.status === 'disponivel'
                            ? 'bg-sky-100 text-sky-800'
                            : unidade.status === 'sorteado'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                        }`}
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

      <Modal
        titulo={form?.id ? 'Editar prêmio' : 'Novo prêmio'}
        aberto={form !== null}
        aoFechar={() => setForm(null)}
      >
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
    </div>
  )
}
