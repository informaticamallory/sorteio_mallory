/**
 * Mistura aleatória dos prêmios de um bloco (botão do dado no "Organizar").
 *
 * Embaralha a sequência sem repetir o mesmo prêmio duas vezes seguidas sempre
 * que isso for possível. Quando um prêmio tem mais da metade das unidades,
 * repetir é inevitável e a mistura fica só aleatória.
 *
 * A ordem dos prêmios não interfere em quem ganha: cada sorteio continua
 * escolhendo o ganhador no servidor, entre todos os elegíveis.
 */

function embaralhar<T>(lista: T[], aleatorio: () => number): T[] {
  const copia = [...lista]
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(aleatorio() * (i + 1))
    ;[copia[i], copia[j]] = [copia[j], copia[i]]
  }
  return copia
}

/** Ainda dá para terminar sem repetir, sabendo que `ultimo` acabou de sair? */
function semRepetirAinda(restantes: number[], ultimo: number): boolean {
  const total = restantes.reduce((soma, n) => soma + n, 0)
  const maior = Math.max(0, ...restantes)
  if (maior > Math.ceil(total / 2)) return false
  // Total ímpar com o maior no limite: o maior precisa vir primeiro, então não pode ser o último.
  return !(total % 2 === 1 && maior === (total + 1) / 2 && restantes[ultimo] === maior)
}

export function misturarAleatorio<T>(
  itens: T[],
  premioDe: (item: T) => number,
  aleatorio: () => number = Math.random,
): T[] {
  const porPremio = new Map<number, T[]>()
  for (const item of itens) {
    const chave = premioDe(item)
    const grupo = porPremio.get(chave)
    if (grupo) grupo.push(item)
    else porPremio.set(chave, [item])
  }
  // As unidades de um mesmo prêmio também saem em ordem aleatória.
  const grupos = [...porPremio.values()].map((g) => embaralhar(g, aleatorio))
  const restantes = grupos.map((g) => g.length)
  const evitarRepeticao = Math.max(0, ...restantes) <= Math.ceil(itens.length / 2)

  const saida: T[] = []
  let ultimo = -1
  for (let passo = 0; passo < itens.length; passo++) {
    const disponiveis = restantes.map((_, g) => g).filter((g) => restantes[g] > 0)
    let candidatos = disponiveis
    if (evitarRepeticao) {
      const viaveis = disponiveis.filter((g) => {
        if (g === ultimo) return false
        restantes[g]--
        const ok = semRepetirAinda(restantes, g)
        restantes[g]++
        return ok
      })
      if (viaveis.length > 0) candidatos = viaveis
    }
    // Sorteio ponderado pelo que falta de cada prêmio: espalha naturalmente.
    const peso = candidatos.reduce((soma, g) => soma + restantes[g], 0)
    let marca = aleatorio() * peso
    let escolhido = candidatos[candidatos.length - 1]
    for (const g of candidatos) {
      marca -= restantes[g]
      if (marca < 0) {
        escolhido = g
        break
      }
    }
    const grupo = grupos[escolhido]
    saida.push(grupo[grupo.length - restantes[escolhido]])
    restantes[escolhido]--
    ultimo = escolhido
  }
  return saida
}
