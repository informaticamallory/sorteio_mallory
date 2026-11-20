import { useState } from 'react'

/**
 * Logomarca oficial Mallory (versao branca, para fundo preto).
 *
 * O arquivo NAO e desenhado aqui: coloque o oficial em
 * `frontend/public/marca/mallory-branca.svg` (ou `.png`). Enquanto ele nao
 * existir, aparece apenas o texto "Sorteios Mallory", sem imitar a marca.
 */
const FONTES = ['/marca/mallory-branca.svg', '/marca/mallory-branca.png']

export default function LogoMallory({ className = 'h-7 w-auto' }: { className?: string }) {
  const [indice, setIndice] = useState(0)
  if (indice >= FONTES.length) {
    return <span className="whitespace-nowrap text-sm font-semibold text-white">Sorteios Mallory</span>
  }
  return (
    <img
      src={FONTES[indice]}
      alt="Mallory"
      className={className}
      onError={() => setIndice((i) => i + 1)}
    />
  )
}
