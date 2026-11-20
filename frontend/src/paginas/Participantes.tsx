import { useCallback, useEffect, useState } from 'react'
import { baixarArquivo, enviarArquivo, requisitar } from '../api'
import UploadImagem from '../componentes/UploadImagem'
import { Aviso, Carregando, Modal, Vazio } from '../componentes/ui'
import type { Participante, PreviaImportacao } from '../types'
import { usePainel } from './PainelLayout'
import Icone from '../componentes/Icone'

interface FormParticipante {
  id?: number
  nome: string
  matricula: string
  setor: string
  foto_url: string | null
  pulseira: string
}

const VAZIO: FormParticipante = { nome: '', matricula: '', setor: '', foto_url: null, pulseira: '' }

// Mesma regra do backend (schemas.normalizar_pulseira).
const PULSEIRA_RE = /^[A-Z0-9-]{1,40}$/

function normalizarPulseira(valor: string): string {
  return valor.trim().toUpperCase()
}

export default function Participantes() {
  const { evento, recarregarResumo } = usePainel()
  const [lista, setLista] = useState<Participante[] | null>(null)
  const [setores, setSetores] = useState<string[]>([])
  const [busca, setBusca] = useState('')
  const [setor, setSetor] = useState('')
  const [presenca, setPresenca] = useState('todos')
  const [participacao, setParticipacao] = useState('todos')
  const [erro, setErro] = useState('')

  const [form, setForm] = useState<FormParticipante | null>(null)
  const [erroForm, setErroForm] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [motivoAlvo, setMotivoAlvo] = useState<Participante | null>(null)
  const [motivo, setMotivo] = useState('')
  const [importando, setImportando] = useState(false)
  const [zerando, setZerando] = useState(false)

  const carregar = useCallback(async () => {
    try {
      const parametros = new URLSearchParams({ busca, setor, presenca, participacao })
      setLista(
        await requisitar<Participante[]>(
          `/api/events/${evento.id}/participantes?${parametros.toString()}`,
        ),
      )
      setErro('')
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao carregar participantes')
    }
  }, [evento.id, busca, setor, presenca, participacao])

  useEffect(() => {
    const atraso = setTimeout(() => void carregar(), 250)
    return () => clearTimeout(atraso)
  }, [carregar])

  useEffect(() => {
    void requisitar<string[]>(`/api/events/${evento.id}/participantes/setores`).then(setSetores)
  }, [evento.id, lista])

  function problemaNaPulseira(atual: FormParticipante): string {
    const pulseira = normalizarPulseira(atual.pulseira)
    if (!pulseira) return ''
    if (!PULSEIRA_RE.test(pulseira)) return 'Pulseira: use até 40 letras, números ou hífen.'
    // Conferência rápida na lista carregada. A garantia é a restrição do banco:
    // a lista pode estar filtrada, e o backend responde 409 se houver conflito.
    const dono = lista?.find((p) => p.pulseira === pulseira && p.id !== atual.id)
    if (dono) return `A pulseira ${pulseira} já está com ${dono.nome}.`
    return ''
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    const problema = problemaNaPulseira(form)
    if (problema) {
      setErroForm(problema)
      return
    }
    setSalvando(true)
    setErroForm('')
    const pulseira = normalizarPulseira(form.pulseira) || null
    try {
      if (form.id) {
        await requisitar(`/api/events/${evento.id}/participantes/${form.id}`, {
          metodo: 'PATCH',
          corpo: {
            nome: form.nome,
            matricula: form.matricula,
            setor: form.setor,
            foto_url: form.foto_url,
            pulseira,
          },
        })
      } else {
        await requisitar(`/api/events/${evento.id}/participantes`, {
          metodo: 'POST',
          corpo: { ...form, pulseira, presente: false },
        })
      }
      setForm(null)
      await carregar()
      await recarregarResumo()
    } catch (erroSalvar) {
      setErroForm(erroSalvar instanceof Error ? erroSalvar.message : 'Falha ao salvar')
    } finally {
      setSalvando(false)
    }
  }

  function abrirFormulario(dados: FormParticipante) {
    setErroForm('')
    setForm(dados)
  }

  async function alternarPresenca(p: Participante) {
    await requisitar(`/api/events/${evento.id}/participantes/${p.id}/presenca`, {
      metodo: 'POST',
      corpo: { presente: !p.presente },
    })
    await carregar()
    await recarregarResumo()
  }

  async function confirmarMotivo(e: React.FormEvent) {
    e.preventDefault()
    if (!motivoAlvo) return
    await requisitar(`/api/events/${evento.id}/participantes/${motivoAlvo.id}/participacao`, {
      metodo: 'POST',
      corpo: { participando: !motivoAlvo.participando, motivo: motivo.trim() },
    })
    setMotivoAlvo(null)
    setMotivo('')
    await carregar()
    await recarregarResumo()
  }

  const total = lista?.length ?? 0
  const presentes = lista?.filter((p) => p.presente).length ?? 0

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          <strong>{total}</strong> participante(s) na lista &middot; <strong>{presentes}</strong>{' '}
          com presença confirmada
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-sutil text-rose-700"
            onClick={() => setZerando(true)}
          >
            Zerar lista
          </button>
          <button type="button" className="btn-neutro" onClick={() => setImportando(true)}>
            Importar planilha
          </button>
          <button type="button" className="btn-primario" onClick={() => abrirFormulario({ ...VAZIO })}>
            Novo participante
          </button>
        </div>
      </div>

      <div className="cartao grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="rotulo" htmlFor="f-busca">
            Buscar por nome ou matrícula
          </label>
          <input
            id="f-busca"
            className="campo"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Ex.: Maria ou 00123"
          />
        </div>
        <div>
          <label className="rotulo" htmlFor="f-setor">
            Setor
          </label>
          <select id="f-setor" className="campo" value={setor} onChange={(e) => setSetor(e.target.value)}>
            <option value="">Todos</option>
            {setores.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="rotulo" htmlFor="f-presenca">
            Presença
          </label>
          <select
            id="f-presenca"
            className="campo"
            value={presenca}
            onChange={(e) => setPresenca(e.target.value)}
          >
            <option value="todos">Todos</option>
            <option value="presentes">Presentes</option>
            <option value="ausentes">Ausentes</option>
          </select>
        </div>
        <div>
          <label className="rotulo" htmlFor="f-participacao">
            Participação
          </label>
          <select
            id="f-participacao"
            className="campo"
            value={participacao}
            onChange={(e) => setParticipacao(e.target.value)}
          >
            <option value="todos">Todos</option>
            <option value="ativos">Participando</option>
            <option value="excluidos">Excluídos</option>
          </select>
        </div>
      </div>

      {lista === null ? (
        <Carregando />
      ) : lista.length === 0 ? (
        <Vazio
          titulo="Nenhum participante encontrado"
          descricao="Ajuste os filtros, cadastre manualmente ou importe uma planilha."
        />
      ) : (
        <div className="cartao overflow-hidden">
          <ul className="divide-y divide-slate-100">
            {lista.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 p-3 sm:flex-nowrap">
                <div className="h-10 w-10 shrink-0 overflow-hidden rounded-full bg-slate-200">
                  {p.foto_url ? (
                    <img src={p.foto_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <span className="flex h-full w-full items-center justify-center text-sm font-semibold text-slate-500">
                      {p.nome.slice(0, 1).toUpperCase()}
                    </span>
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-slate-900">
                    <span className="truncate">{p.nome}</span>
                    {p.ja_ganhou && (
                      <span className="etiqueta bg-marca-500/20 text-marca-600">Já ganhou</span>
                    )}
                    {!p.participando && (
                      <span className="etiqueta bg-rose-100 text-rose-800">Fora do sorteio</span>
                    )}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    Matrícula {p.matricula}
                    {p.numero_sorteio ? ` · Nº ${p.numero_sorteio}` : ''}
                    {p.pulseira ? ` · Pulseira ${p.pulseira}` : ''}
                    {p.setor ? ` · ${p.setor}` : ''}
                    {!p.participando && p.motivo_participacao ? ` · ${p.motivo_participacao}` : ''}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void alternarPresenca(p)}
                    className={`etiqueta cursor-pointer px-3 py-1.5 ${
                      p.presente
                        ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {p.presente ? <><Icone nome="check" className="h-3.5 w-3.5" /> Presente</> : 'Ausente'}
                  </button>
                  <button
                    type="button"
                    className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
                    title="Editar"
                    onClick={() =>
                      abrirFormulario({
                        id: p.id,
                        nome: p.nome,
                        matricula: p.matricula,
                        setor: p.setor,
                        foto_url: p.foto_url,
                        pulseira: p.pulseira ?? '',
                      })
                    }
                  >
                    <Icone nome="editar" className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
                    title={p.participando ? 'Excluir da participação' : 'Reincluir na participação'}
                    onClick={() => {
                      setMotivoAlvo(p)
                      setMotivo('')
                    }}
                  >
                    <Icone nome={p.participando ? 'bloquear' : 'restaurar'} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ----------------------------------------------- cadastro manual */}
      <Modal
        titulo={form?.id ? 'Editar participante' : 'Novo participante'}
        aberto={form !== null}
        aoFechar={() => setForm(null)}
      >
        {form && (
          <form onSubmit={salvar} className="space-y-4">
            <div>
              <label className="rotulo" htmlFor="p-nome">
                Nome
              </label>
              <input
                id="p-nome"
                className="campo"
                required
                autoFocus
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="rotulo" htmlFor="p-matricula">
                  Matrícula
                </label>
                <input
                  id="p-matricula"
                  className="campo font-mono"
                  required
                  value={form.matricula}
                  onChange={(e) => setForm({ ...form, matricula: e.target.value })}
                  placeholder="00123"
                />
                <p className="mt-1 text-xs text-slate-500">Zeros à esquerda são preservados.</p>
              </div>
              <div>
                <label className="rotulo" htmlFor="p-setor">
                  Setor
                </label>
                <input
                  id="p-setor"
                  className="campo"
                  list="lista-setores"
                  value={form.setor}
                  onChange={(e) => setForm({ ...form, setor: e.target.value })}
                />
                <datalist id="lista-setores">
                  {setores.map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
              </div>
            </div>
            <div>
              <label className="rotulo" htmlFor="p-pulseira">
                Número da pulseira (opcional)
              </label>
              <input
                id="p-pulseira"
                className="campo font-mono uppercase"
                maxLength={40}
                autoComplete="off"
                value={form.pulseira}
                onChange={(e) => {
                  setErroForm('')
                  setForm({ ...form, pulseira: e.target.value })
                }}
                placeholder="0042"
                aria-describedby="p-pulseira-ajuda"
              />
              <p id="p-pulseira-ajuda" className="mt-1 text-xs text-slate-500">
                Única neste evento. Letras, números ou hífen; zeros à esquerda são preservados.
                {form.id ? ' A troca fica registrada na auditoria.' : ''}
              </p>
            </div>
            <UploadImagem
              url={form.foto_url}
              rotulo="Foto (opcional)"
              aoMudar={(url) => setForm({ ...form, foto_url: url })}
            />
            {erroForm && <Aviso tipo="erro">{erroForm}</Aviso>}
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

      {/* ----------------------------------------------- motivo inclusão/exclusão */}
      <Modal
        titulo={motivoAlvo?.participando ? 'Excluir da participação' : 'Reincluir na participação'}
        aberto={motivoAlvo !== null}
        aoFechar={() => setMotivoAlvo(null)}
      >
        {motivoAlvo && (
          <form onSubmit={confirmarMotivo} className="space-y-4">
            <p className="text-sm text-slate-600">
              {motivoAlvo.participando
                ? `${motivoAlvo.nome} deixará de concorrer nas próximas rodadas.`
                : `${motivoAlvo.nome} voltará a concorrer nas próximas rodadas.`}
            </p>
            <div>
              <label className="rotulo" htmlFor="motivo">
                Motivo (obrigatório, fica registrado no histórico)
              </label>
              <textarea
                id="motivo"
                className="campo"
                rows={3}
                required
                minLength={3}
                autoFocus
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-neutro" onClick={() => setMotivoAlvo(null)}>
                Cancelar
              </button>
              <button type="submit" className="btn-primario">
                Confirmar
              </button>
            </div>
          </form>
        )}
      </Modal>

      <ModalImportacao
        aberto={importando}
        eventId={evento.id}
        aoFechar={() => setImportando(false)}
        aoConcluir={async () => {
          setImportando(false)
          await carregar()
          await recarregarResumo()
        }}
      />

      <ModalZerar
        aberto={zerando}
        eventId={evento.id}
        aoFechar={() => setZerando(false)}
        aoZerar={async () => {
          await carregar()
          await recarregarResumo()
        }}
        aoImportar={() => {
          setZerando(false)
          setImportando(true)
        }}
      />
    </div>
  )
}

// --------------------------------------------------------------- zerar lista
const FRASE_ZERAR = 'ZERAR'

interface ResultadoZerar {
  removidos: number
  mantidos: { nome: string; matricula: string; motivo: string }[]
  backup: string | null
}

function ModalZerar({
  aberto,
  eventId,
  aoFechar,
  aoZerar,
  aoImportar,
}: {
  aberto: boolean
  eventId: number
  aoFechar: () => void
  aoZerar: () => Promise<void>
  aoImportar: () => void
}) {
  const [frase, setFrase] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [resultado, setResultado] = useState<ResultadoZerar | null>(null)

  useEffect(() => {
    if (!aberto) {
      setFrase('')
      setErro('')
      setResultado(null)
    }
  }, [aberto])

  async function zerar(e: React.FormEvent) {
    e.preventDefault()
    setEnviando(true)
    setErro('')
    try {
      setResultado(
        await requisitar<ResultadoZerar>(`/api/events/${eventId}/participantes/zerar`, {
          metodo: 'POST',
          corpo: { confirmacao: frase },
        }),
      )
      await aoZerar()
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Falha ao zerar a lista')
    } finally {
      setEnviando(false)
    }
  }

  const confirmado = frase.trim().toUpperCase() === FRASE_ZERAR

  return (
    <Modal titulo="Zerar lista de participantes" aberto={aberto} aoFechar={aoFechar}>
      {resultado ? (
        <div className="space-y-4">
          <Aviso tipo="sucesso">
            {resultado.removidos} participante(s) removido(s).
            {resultado.backup && ` Cópia de segurança: ${resultado.backup}.`}
          </Aviso>
          {resultado.mantidos.length > 0 && (
            <div className="text-sm text-slate-600">
              <p className="mb-1 font-medium text-slate-800">
                Mantidos ({resultado.mantidos.length}):
              </p>
              <ul className="list-disc space-y-0.5 pl-5">
                {resultado.mantidos.map((m) => (
                  <li key={m.matricula}>
                    {m.nome} ({m.matricula}): {m.motivo}
                  </li>
                ))}
              </ul>
              <p className="mt-2">
                Na nova planilha, marque <strong>Atualizar dados de quem já existe</strong> e{' '}
                <strong>Atualizar identificação</strong> para corrigir também estes cadastros.
              </p>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-neutro" onClick={aoFechar}>
              Fechar
            </button>
            <button type="button" className="btn-primario" onClick={aoImportar}>
              Importar planilha
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={zerar} className="space-y-4">
          <div className="space-y-2 text-sm text-slate-600">
            <p>
              Apaga todos os participantes do evento para você importar a planilha de novo. Use
              antes do evento.
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>
                <strong>Continuam na lista:</strong> quem tem resultado no histórico de sorteios
                (inclusive anulado) e quem já fez o autocadastro.
              </li>
              <li>
                Quem for apagado perde o número da sorte e a presença; ao reimportar, recebe um
                número novo.
              </li>
              <li>Antes de apagar, o sistema salva uma cópia de segurança do banco.</li>
            </ul>
          </div>
          {erro && <Aviso tipo="erro">{erro}</Aviso>}
          <div>
            <label className="rotulo" htmlFor="frase-zerar">
              Para confirmar, digite {FRASE_ZERAR}
            </label>
            <input
              id="frase-zerar"
              className="campo"
              autoComplete="off"
              autoFocus
              value={frase}
              onChange={(e) => setFrase(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-neutro" onClick={aoFechar}>
              Cancelar
            </button>
            <button type="submit" className="btn-perigo" disabled={!confirmado || enviando}>
              {enviando ? 'Zerando...' : 'Zerar lista'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

// --------------------------------------------------------------- importação
function ModalImportacao({
  aberto,
  eventId,
  aoFechar,
  aoConcluir,
}: {
  aberto: boolean
  eventId: number
  aoFechar: () => void
  aoConcluir: () => Promise<void>
}) {
  const [previa, setPrevia] = useState<PreviaImportacao | null>(null)
  const [erro, setErro] = useState('')
  const [carregandoPrevia, setCarregandoPrevia] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const [atualizarExistentes, setAtualizarExistentes] = useState(false)
  const [atualizarIdentificacao, setAtualizarIdentificacao] = useState(false)
  const [resultado, setResultado] = useState<{
    criados: number
    atualizados: number
    identificacoes_atualizadas: number
    ignorados: number
  } | null>(null)

  useEffect(() => {
    if (!aberto) {
      setPrevia(null)
      setErro('')
      setAtualizarExistentes(false)
      setAtualizarIdentificacao(false)
      setResultado(null)
    }
  }, [aberto])

  async function analisar(arquivo: File | undefined) {
    if (!arquivo) return
    setErro('')
    setCarregandoPrevia(true)
    try {
      setPrevia(
        await enviarArquivo<PreviaImportacao>(
          `/api/events/${eventId}/participantes/importar/previa`,
          arquivo,
        ),
      )
    } catch (e) {
      setPrevia(null)
      setErro(e instanceof Error ? e.message : 'Falha ao ler a planilha')
    } finally {
      setCarregandoPrevia(false)
    }
  }

  async function confirmar() {
    if (!previa) return
    setConfirmando(true)
    setErro('')
    try {
      const linhas = previa.linhas
        .filter((l) => l.erros.length === 0)
        .map((l) => ({
          nome: l.nome,
          matricula: l.matricula,
          setor: l.setor,
          // Codigos protegidos calculados no servidor (o CPF nunca passa por aqui).
          codigo_identificacao: l.codigo_identificacao,
          codigo_cpf: l.codigo_cpf,
        }))
      setResultado(
        await requisitar(`/api/events/${eventId}/participantes/importar/confirmar`, {
          metodo: 'POST',
          corpo: {
            linhas,
            atualizar_existentes: atualizarExistentes,
            atualizar_identificacao: atualizarIdentificacao,
          },
        }),
      )
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao importar')
    } finally {
      setConfirmando(false)
    }
  }

  const importaveis = previa?.linhas.filter((l) => l.erros.length === 0).length ?? 0
  // Setor é opcional: planilha sem setor não mostra a coluna vazia.
  const temSetor = previa?.linhas.some((l) => l.setor) ?? false

  return (
    <Modal titulo="Importar participantes" aberto={aberto} aoFechar={aoFechar} largura="max-w-3xl">
      <div className="space-y-4">
        <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
          <p className="mb-2 font-medium text-slate-800">
            Colunas: nome e matrícula (ou código); opcionais: data de nascimento, CPF e setor
          </p>
          <p className="mb-1">
            Data de nascimento e CPF são opcionais, mas sem eles o colaborador não consegue se
            cadastrar pelo QR Code. O sistema <strong>não guarda</strong> o CPF nem a data: grava só um
            código protegido para conferir a identidade. Matrículas 00026, 026 e 26 contam como a mesma.
          </p>
          <p className="mb-3">
            Formate matrícula e CPF como <strong>texto</strong> na planilha para não perder os zeros à
            esquerda.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-neutro"
              onClick={() => void baixarArquivo('/api/participantes/modelo.xlsx', 'modelo.xlsx')}
            >
              Baixar modelo XLSX
            </button>
            <button
              type="button"
              className="btn-neutro"
              onClick={() => void baixarArquivo('/api/participantes/modelo.csv', 'modelo.csv')}
            >
              Baixar modelo CSV
            </button>
          </div>
        </div>

        <div>
          <label className="rotulo" htmlFor="arquivo-import">
            Arquivo CSV ou XLSX
          </label>
          <input
            id="arquivo-import"
            type="file"
            accept=".csv,.xlsx,.xlsm,text/csv"
            onChange={(e) => {
              void analisar(e.target.files?.[0])
              e.target.value = ''
            }}
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border file:border-slate-300
                       file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-medium
                       file:text-slate-700 hover:file:bg-slate-50"
          />
        </div>

        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {carregandoPrevia && <Carregando texto="Analisando planilha..." />}

        {resultado && (
          <div className="space-y-3">
            <Aviso tipo="sucesso">
              Importação concluída: {resultado.criados} criado(s), {resultado.atualizados} com nome/setor
              atualizados, {resultado.identificacoes_atualizadas} com CPF e nascimento completados e{' '}
              {resultado.ignorados} ignorado(s).
            </Aviso>
            <div className="flex justify-end">
              <button type="button" className="btn-primario" onClick={() => void aoConcluir()}>
                Concluir
              </button>
            </div>
          </div>
        )}

        {previa && !resultado && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {[
                ['Linhas', previa.total_linhas, 'bg-slate-100 text-slate-800'],
                ['Válidas', previa.validas, 'bg-emerald-100 text-emerald-800'],
                ['Com erro', previa.com_erro, 'bg-rose-100 text-rose-800'],
                ['Duplicadas', previa.duplicadas, 'bg-amber-100 text-amber-800'],
                ['Com CPF e nasc.', previa.com_identificacao, 'bg-sky-100 text-sky-800'],
              ].map(([rotulo, valor, classe]) => (
                <div key={String(rotulo)} className={`rounded-lg p-3 text-center ${classe}`}>
                  <p className="text-lg font-semibold tabular-nums">{valor as number}</p>
                  <p className="text-xs font-medium">{rotulo as string}</p>
                </div>
              ))}
            </div>

            {previa.duplicadas > 0 && (
              <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-amber-600"
                  checked={atualizarExistentes}
                  onChange={(e) => setAtualizarExistentes(e.target.checked)}
                />
                <span className="text-amber-900">
                  Atualizar nome e setor de matrículas que já existem neste evento. Sem marcar, elas
                  são ignoradas.
                </span>
              </label>
            )}
            {previa.linhas.some((l) => l.ja_existe_no_evento && l.tem_identificacao && !l.erros.length) && (
              <label className="flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-sky-700"
                  checked={atualizarIdentificacao}
                  onChange={(e) => setAtualizarIdentificacao(e.target.checked)}
                />
                <span className="text-sky-900">
                  Completar CPF e nascimento de quem já existe neste evento (necessário para o cadastro
                  pelo QR Code). Não muda nome, setor, número da sorte nem histórico.
                </span>
              </label>
            )}

            <div className="max-h-72 overflow-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Linha</th>
                    <th className="px-3 py-2">Nome</th>
                    <th className="px-3 py-2">Matrícula</th>
                    {temSetor && <th className="px-3 py-2">Setor</th>}
                    <th className="px-3 py-2">CPF e nasc.</th>
                    <th className="px-3 py-2">Situação</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {previa.linhas.map((l) => (
                    <tr key={l.linha} className={l.erros.length ? 'bg-rose-50' : ''}>
                      <td className="px-3 py-2 text-slate-400">{l.linha}</td>
                      <td className="px-3 py-2">{l.nome || '—'}</td>
                      <td className="px-3 py-2 font-mono">{l.matricula || '—'}</td>
                      {temSetor && <td className="px-3 py-2">{l.setor || '—'}</td>}
                      <td className="px-3 py-2 text-xs">
                        {l.tem_identificacao ? (
                          <span className="text-emerald-700">Válidos</span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {l.erros.length > 0 ? (
                          <span className="text-rose-700">{l.erros.join('; ')}</span>
                        ) : l.ja_existe_no_evento ? (
                          <span className="text-amber-700">Já existe no evento</span>
                        ) : (
                          <span className="text-emerald-700">OK</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end gap-2">
              <button type="button" className="btn-neutro" onClick={aoFechar}>
                Cancelar
              </button>
              <button
                type="button"
                className="btn-primario"
                disabled={confirmando || importaveis === 0}
                onClick={() => void confirmar()}
              >
                {confirmando ? 'Importando...' : `Importar ${importaveis} participante(s)`}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
