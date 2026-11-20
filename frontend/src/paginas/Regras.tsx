import { useCallback, useEffect, useState } from 'react'
import { requisitar } from '../api'
import { useAuth } from '../auth'
import { Aviso, Carregando } from '../componentes/ui'
import type { Evento, FaixaMatricula, ModoSorteio, MudancaRegra, ResumoRegras } from '../types'
import { usePainel } from './PainelLayout'

/** Nomes legíveis no histórico de alterações. */
const NOME_CAMPO: Record<string, string> = {
  modo_sorteio: 'Modo do sorteio',
  matricula_faixa_inicio: 'Faixa de matrículas (início)',
  matricula_faixa_fim: 'Faixa de matrículas (fim)',
}
const NOME_VALOR: Record<string, string> = {
  numero_sorte: 'Número da sorte',
  faixa_matricula: 'Faixa de matrículas',
  None: '—',
}

const TRATAMENTOS: { valor: Evento['tratamento_ausente']; titulo: string; detalhe: string }[] = [
  {
    valor: 'resortear',
    titulo: 'Anular e sortear novamente',
    detalhe: 'O resultado é anulado com justificativa e a unidade volta para o sorteio.',
  },
  {
    valor: 'pendente',
    titulo: 'Manter o prêmio pendente',
    detalhe: 'O ganhador fica registrado e o prêmio aguarda retirada posterior.',
  },
  {
    valor: 'bloquear',
    titulo: 'Ausentes não concorrem',
    detalhe: 'Somente quem tem presença confirmada entra no sorteio.',
  },
]

export default function Regras() {
  const { evento, recarregarEvento, recarregarResumo } = usePainel()
  const [resumo, setResumo] = useState<ResumoRegras | null>(null)
  const [historico, setHistorico] = useState<MudancaRegra[]>([])
  const [erro, setErro] = useState('')
  const [salvando, setSalvando] = useState(false)

  const carregar = useCallback(async () => {
    const [r, h] = await Promise.all([
      requisitar<ResumoRegras>(`/api/events/${evento.id}/regras/resumo`),
      requisitar<MudancaRegra[]>(`/api/events/${evento.id}/regras/historico`),
    ])
    setResumo(r)
    setHistorico(h)
  }, [evento.id])

  useEffect(() => {
    void carregar().catch((e) => setErro(e instanceof Error ? e.message : 'Falha ao carregar'))
  }, [carregar])

  async function alterar(campos: Partial<Evento>) {
    setSalvando(true)
    setErro('')
    try {
      await requisitar(`/api/events/${evento.id}/regras`, { metodo: 'PATCH', corpo: campos })
      await recarregarEvento()
      await recarregarResumo()
      await carregar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao salvar a regra')
    } finally {
      setSalvando(false)
    }
  }

  async function confirmar() {
    await requisitar(`/api/events/${evento.id}/regras/confirmar`, { metodo: 'POST' })
    await recarregarEvento()
    await carregar()
  }

  if (!resumo) return <Carregando />

  return (
    <div className="space-y-4">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {resumo.primeiro_sorteio_realizado && (
        <Aviso tipo="atencao">
          O evento já teve sorteios. Alterações nas regras a partir de agora ficam registradas no
          histórico abaixo e passam a valer nas próximas rodadas.
        </Aviso>
      )}

      <section className="cartao p-5">
        <h2 className="mb-1 font-semibold text-slate-900">Resumo das regras</h2>
        <p className="mb-4 text-sm text-slate-500">
          Confira este resumo com a plateia antes do primeiro sorteio.
        </p>
        <ul className="space-y-2">
          {resumo.itens.map((item) => (
            <li key={item} className="flex gap-2 text-sm text-slate-700">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
              {item}
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
          <p className="text-sm text-slate-600">
            Participantes elegíveis agora: <strong>{resumo.elegiveis_agora}</strong>
          </p>
          {resumo.confirmadas_em ? (
            <span className="etiqueta bg-emerald-100 text-emerald-800">
              Regras confirmadas em {new Date(resumo.confirmadas_em + 'Z').toLocaleString('pt-BR')}
            </span>
          ) : (
            <button type="button" className="btn-primario" onClick={() => void confirmar()}>
              Confirmar regras e liberar o evento
            </button>
          )}
        </div>
      </section>

      <ModoDoSorteio evento={evento} salvando={salvando} aoSalvar={alterar} />

      <section className="cartao divide-y divide-slate-100">
        <div className="flex items-start justify-between gap-4 p-5">
          <div>
            <h3 className="font-medium text-slate-900">Uma pessoa pode ganhar mais de uma vez</h3>
            <p className="text-sm text-slate-500">
              Desativado, quem já ganhou sai da lista de elegíveis nas rodadas seguintes.
            </p>
          </div>
          <Interruptor
            ligado={evento.permite_multiplas_vitorias}
            desabilitado={salvando}
            aoMudar={(v) => void alterar({ permite_multiplas_vitorias: v })}
          />
        </div>

        <div className="flex items-start justify-between gap-4 p-5">
          <div>
            <h3 className="font-medium text-slate-900">
              Somente presença confirmada pode concorrer
            </h3>
            <p className="text-sm text-slate-500">
              Ativado, apenas quem foi marcado como presente entra no sorteio.
            </p>
          </div>
          <Interruptor
            ligado={evento.exige_presenca}
            desabilitado={salvando}
            aoMudar={(v) => void alterar({ exige_presenca: v })}
          />
        </div>

        <div className="p-5">
          <h3 className="font-medium text-slate-900">Se o ganhador não estiver presente</h3>
          <div className="mt-3 grid gap-2">
            {TRATAMENTOS.map((opcao) => (
              <label
                key={opcao.valor}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
                  evento.tratamento_ausente === opcao.valor
                    ? 'border-marca-500 bg-marca-50'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <input
                  type="radio"
                  name="tratamento"
                  className="mt-1 h-4 w-4 accent-marca-800"
                  checked={evento.tratamento_ausente === opcao.valor}
                  disabled={salvando}
                  onChange={() => void alterar({ tratamento_ausente: opcao.valor })}
                />
                <span>
                  <span className="block text-sm font-medium text-slate-900">{opcao.titulo}</span>
                  <span className="block text-sm text-slate-500">{opcao.detalhe}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex items-start justify-between gap-4 p-5">
          <div>
            <h3 className="font-medium text-slate-900">
              Quem teve resultado anulado por ausência pode concorrer de novo
            </h3>
            <p className="text-sm text-slate-500">
              Desativado, essa pessoa sai das rodadas seguintes.
            </p>
          </div>
          <Interruptor
            ligado={evento.ausente_pode_concorrer_novamente}
            desabilitado={salvando}
            aoMudar={(v) => void alterar({ ausente_pode_concorrer_novamente: v })}
          />
        </div>
      </section>

      <section className="cartao p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Histórico de alterações</h2>
        {historico.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhuma regra foi alterada até agora.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {historico.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-2 border-b border-slate-100 pb-2">
                <span className="font-mono text-xs text-slate-400">
                  {new Date(item.criado_em + 'Z').toLocaleString('pt-BR')}
                </span>
                <span className="text-slate-700">
                  <strong>{NOME_CAMPO[item.campo] ?? item.campo}</strong>:{' '}
                  {NOME_VALOR[item.valor_anterior] ?? item.valor_anterior} →{' '}
                  {NOME_VALOR[item.valor_novo] ?? item.valor_novo}
                </span>
                <span className="text-slate-500">por {item.usuario_nome}</span>
                {item.apos_primeiro_sorteio && (
                  <span className="etiqueta bg-amber-100 text-amber-800">Após o 1º sorteio</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

const MODOS: { valor: ModoSorteio; titulo: string; detalhe: string }[] = [
  {
    valor: 'numero_sorte',
    titulo: 'Número da sorte (padrão)',
    detalhe: 'Todos os elegíveis concorrem com a mesma chance. O telão mostra o nome e o número da sorte do ganhador.',
  },
  {
    valor: 'faixa_matricula',
    titulo: 'Faixa de matrículas',
    detalhe:
      'Só concorrem os elegíveis com matrícula dentro da faixa (ex.: 1 a 4999), todos com a mesma chance. A matrícula passa a ser o número da sorte: aparece no Cartão da Sorte, na consulta da recepção e no telão.',
  },
]

function ModoDoSorteio({
  evento,
  salvando,
  aoSalvar,
}: {
  evento: Evento
  salvando: boolean
  aoSalvar: (campos: Partial<Evento>) => Promise<void>
}) {
  const { pode } = useAuth()
  const podeEditar = pode('definir_regras')
  const [modo, setModo] = useState<ModoSorteio>(evento.modo_sorteio)
  const [inicio, setInicio] = useState(evento.matricula_faixa_inicio?.toString() ?? '')
  const [fim, setFim] = useState(evento.matricula_faixa_fim?.toString() ?? '')
  const [previa, setPrevia] = useState<FaixaMatricula | null>(null)

  // Volta ao que está salvo quando o evento muda (salvou, outra aba etc.).
  useEffect(() => {
    setModo(evento.modo_sorteio)
    setInicio(evento.matricula_faixa_inicio?.toString() ?? '')
    setFim(evento.matricula_faixa_fim?.toString() ?? '')
  }, [evento.modo_sorteio, evento.matricula_faixa_inicio, evento.matricula_faixa_fim])

  const numInicio = /^\d{1,9}$/.test(inicio) ? Number(inicio) : null
  const numFim = /^\d{1,9}$/.test(fim) ? Number(fim) : null
  const faixaValida = numInicio !== null && numFim !== null && numInicio <= numFim

  useEffect(() => {
    if (modo !== 'faixa_matricula' || !podeEditar) return
    const params = new URLSearchParams()
    if (numInicio !== null) params.set('inicio', String(numInicio))
    if (numFim !== null) params.set('fim', String(numFim))
    const espera = window.setTimeout(() => {
      requisitar<FaixaMatricula>(`/api/events/${evento.id}/regras/faixa-matricula?${params.toString()}`)
        .then(setPrevia)
        .catch(() => setPrevia(null))
    }, 250)
    return () => window.clearTimeout(espera)
  }, [modo, numInicio, numFim, evento.id, podeEditar])

  const salvo =
    evento.modo_sorteio === 'faixa_matricula' &&
    evento.matricula_faixa_inicio === numInicio &&
    evento.matricula_faixa_fim === numFim

  function escolher(valor: ModoSorteio) {
    setModo(valor)
    // Número da sorte não precisa de mais nada: salva na hora.
    if (valor === 'numero_sorte' && evento.modo_sorteio !== 'numero_sorte') void aoSalvar({ modo_sorteio: 'numero_sorte' })
  }

  return (
    <section className="cartao p-5">
      <h2 className="mb-1 font-semibold text-slate-900">Modo do sorteio</h2>
      <p className="mb-3 text-sm text-slate-500">
        Vale para todos os sorteios deste evento. A escolha do ganhador continua aleatória e auditada; cada resultado
        registra o modo usado.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {MODOS.map((opcao) => (
          <label
            key={opcao.valor}
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
              modo === opcao.valor ? 'border-marca-500 bg-marca-50' : 'border-slate-200 hover:bg-slate-50'
            }`}
          >
            <input
              type="radio"
              name="modo-sorteio"
              className="mt-1 h-4 w-4 accent-marca-800"
              checked={modo === opcao.valor}
              disabled={salvando || !podeEditar}
              onChange={() => escolher(opcao.valor)}
            />
            <span>
              <span className="block text-sm font-medium text-slate-900">
                {opcao.titulo}
                {evento.modo_sorteio === opcao.valor && (
                  <span className="etiqueta ml-2 bg-emerald-100 text-emerald-800">Em uso</span>
                )}
              </span>
              <span className="block text-sm text-slate-500">{opcao.detalhe}</span>
            </span>
          </label>
        ))}
      </div>

      {modo === 'faixa_matricula' && (
        <div className="mt-4 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="faixa-inicio" className="rotulo">
                Matrícula inicial
              </label>
              <input
                id="faixa-inicio"
                inputMode="numeric"
                className="campo w-36 font-mono"
                value={inicio}
                disabled={!podeEditar}
                onChange={(e) => setInicio(e.target.value.replace(/\D/g, '').slice(0, 9))}
                placeholder="ex.: 1"
              />
            </div>
            <div>
              <label htmlFor="faixa-fim" className="rotulo">
                Matrícula final
              </label>
              <input
                id="faixa-fim"
                inputMode="numeric"
                className="campo w-36 font-mono"
                value={fim}
                disabled={!podeEditar}
                onChange={(e) => setFim(e.target.value.replace(/\D/g, '').slice(0, 9))}
                placeholder="ex.: 4999"
              />
            </div>
            {previa?.menor_matricula != null && previa.maior_matricula != null && podeEditar && (
              <button
                type="button"
                className="btn-sutil"
                onClick={() => {
                  setInicio(String(previa.menor_matricula))
                  setFim(String(previa.maior_matricula))
                }}
              >
                Usar todas ({previa.menor_matricula} a {previa.maior_matricula})
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500">Zeros à esquerda não contam: 00026 é a matrícula 26.</p>

          {numInicio !== null && numFim !== null && numInicio > numFim && (
            <Aviso tipo="erro">A matrícula inicial precisa ser menor ou igual à final.</Aviso>
          )}

          {previa && faixaValida && (
            <div className="space-y-2 text-sm">
              <p className="text-slate-700">
                <strong>{previa.dentro_da_faixa}</strong> de {previa.participantes_ativos} participantes ativos têm
                matrícula na faixa. Presença e as demais regras continuam valendo.
              </p>
              {(previa.fora_da_faixa > 0 || previa.matricula_nao_numerica > 0) && (
                <Aviso tipo="atencao">
                  {previa.fora_da_faixa > 0 && (
                    <>
                      {previa.fora_da_faixa} participante(s) com matrícula fora da faixa <strong>não concorrem</strong>.{' '}
                    </>
                  )}
                  {previa.matricula_nao_numerica > 0 && (
                    <>
                      {previa.matricula_nao_numerica} participante(s) com letras ou símbolos na matrícula{' '}
                      <strong>nunca concorrem</strong> neste modo.
                    </>
                  )}
                </Aviso>
              )}
              {previa.dentro_da_faixa === 0 && (
                <Aviso tipo="erro">Ninguém tem matrícula nessa faixa: o sorteio ficará bloqueado.</Aviso>
              )}
            </div>
          )}

          {podeEditar && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn-primario"
                disabled={salvando || !faixaValida || salvo}
                onClick={() =>
                  void aoSalvar({
                    modo_sorteio: 'faixa_matricula',
                    matricula_faixa_inicio: numInicio,
                    matricula_faixa_fim: numFim,
                  })
                }
              >
                {salvo ? 'Faixa em uso' : 'Usar faixa de matrículas'}
              </button>
              {evento.modo_sorteio !== 'faixa_matricula' && (
                <span className="text-xs text-slate-500">
                  Até salvar, o sorteio continua no modo número da sorte.
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function Interruptor({
  ligado,
  aoMudar,
  desabilitado,
}: {
  ligado: boolean
  aoMudar: (v: boolean) => void
  desabilitado?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={ligado}
      disabled={desabilitado}
      onClick={() => aoMudar(!ligado)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50 ${
        ligado ? 'bg-emerald-500' : 'bg-slate-300'
      }`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
          ligado ? 'left-[22px]' : 'left-0.5'
        }`}
      />
    </button>
  )
}
