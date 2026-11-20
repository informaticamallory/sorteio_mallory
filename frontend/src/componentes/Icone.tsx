/**
 * Icones lineares monocromaticos (traco 1.75, 24x24), desenhados para o
 * sistema. Herdam a cor do texto (currentColor). Sem biblioteca externa.
 */
const CAMINHOS = {
  inicio: 'M3 12 12 4l9 8M5 10v10h5v-6h4v6h5V10',
  painel: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z',
  sorteio: 'M4 5h16v14H4zM9 9.5h.01M15 9.5h.01M12 12h.01M9 14.5h.01M15 14.5h.01',
  recepcao: 'M4 13h4l2 3h4l2-3h4M4 13l2-8h12l2 8v6H4z',
  credenciamento: 'M8 4h8v3H8zM6 6H5v14h14V6h-1M9 13a3 3 0 1 0 6 0 3 3 0 0 0-6 0M8 19c.6-1.8 2.1-3 4-3s3.4 1.2 4 3',
  blocos: 'M12 3 3 8l9 5 9-5zM3 12.5l9 5 9-5M3 17l9 5 9-5',
  participantes: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M3 20c.7-3.4 3-5.5 6-5.5s5.3 2.1 6 5.5M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14.8c1.6.7 2.6 2.4 3 5.2',
  premios: 'M4 9h16v4H4zM5 13h14v8H5zM12 9v12M12 9S10.5 4 8 4a2.5 2.5 0 0 0 0 5M12 9s1.5-5 4-5a2.5 2.5 0 0 1 0 5',
  regras: 'M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2',
  historico: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2',
  relatorio: 'M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6',
  configuracao: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1',
  telao: 'M3 5h18v12H3zM8 21h8M12 17v4',
  usuarios: 'M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M3 21c.8-3.8 3.6-6 7-6 1.3 0 2.5.3 3.5.9M17 15v6M14 18h6',
  eventos: 'M4 6h16v14H4zM4 10h16M8 3v5M16 3v5',
  senha: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
  sair: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
  menu: 'M4 6h16M4 12h16M4 18h16',
  fechar: 'M6 6l12 12M18 6 6 18',
  voltar: 'M15 18l-6-6 6-6',
  avancar: 'M9 18l6-6-6-6',
  acima: 'M18 15l-6-6-6 6',
  abaixo: 'M6 9l6 6 6-6',
  externo: 'M14 4h6v6M20 4l-9 9M18 14v6H4V6h6',
  check: 'M5 12.5 10 17l9-10',
  editar: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  excluir: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  bloquear: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M5.6 5.6l12.8 12.8',
  restaurar: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5',
  sino: 'M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a2 2 0 0 0 3.4 0',
  busca: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14M20 20l-4-4',
  play: 'M7 5v14l11-7z',
  pausa: 'M8 5v14M16 5v14',
  anterior: 'M18 6 10 12l8 6zM6 6v12',
  proximo: 'M6 6l8 6-8 6zM18 6v12',
  repetir: 'M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3',
  parar: 'M6 6h12v12H6z',
  alerta: 'M12 9v4M12 17h.01M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0',
  camera: 'M4 7h3l2-3h6l2 3h3v13H4zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
  scanner: 'M4 8.5V6a2 2 0 0 1 2-2h2.5M15.5 4H18a2 2 0 0 1 2 2v2.5M20 15.5V18a2 2 0 0 1-2 2h-2.5M8.5 20H6a2 2 0 0 1-2-2v-2.5M7.5 12h9',
  lanterna: 'M8 3h8v4l-2 3v11h-4V10L8 7zM8 7h8M12 13v2',
  imagem: 'M4 4h16v16H4zM4 16l5-5 4 4 3-3 4 4M15 9h.01',
  baixar: 'M12 4v12M7 11l5 5 5-5M4 20h16',
  entregas: 'M3 7.5 12 3l9 4.5v9L12 21l-9-4.5zM3 7.5l9 4.5 9-4.5M12 12v9',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 11v5M12 8h.01',
  mais: 'M12 5v14M5 12h14',
  pessoa:'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M4 21c.8-4 4-6.5 8-6.5s7.2 2.5 8 6.5',
  bilhete: 'M3 7h18v3a2 2 0 0 0 0 4v3H3v-3a2 2 0 0 0 0-4zM9 7v2M9 11v2M9 15v2',
  celular: 'M7 3h10v18H7zM11 18h2',
  seta: 'M5 12h14M13 6l6 6-6 6',
  cracha: 'M4 7h16v13H4zM10 4h4v5h-4zM9 15a2 2 0 1 0 0-4 2 2 0 0 0 0 4M6 18c.5-1.4 1.6-2.2 3-2.2s2.5.8 3 2.2M14 12h3.5M14 15h3.5',
} as const

export type NomeIcone = keyof typeof CAMINHOS

export default function Icone({
  nome,
  className = 'h-4 w-4',
  titulo,
}: {
  nome: NomeIcone
  className?: string
  /** Texto para leitores de tela quando o icone esta sozinho. */
  titulo?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
      aria-hidden={titulo ? undefined : true}
      role={titulo ? 'img' : undefined}
    >
      {titulo && <title>{titulo}</title>}
      <path d={CAMINHOS[nome]} />
    </svg>
  )
}
