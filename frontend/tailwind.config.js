/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Superficies e texto neutros do painel.
        fundo: '#F7F8FA',
        borda: '#E5E7EB',
        grafite: {
          950: '#111111',
          900: '#1E1E1E', // menu lateral (grafite Mallory)
          800: '#2A2A2A',
          700: '#3A3A3A',
          600: '#5B6068',
          400: '#A1A1AA',
          300: '#D4D4D8',
        },
        // Cor institucional do painel: laranja Mallory (18/11/2026; antes, azul
        // provisorio). 400 e o laranja da logomarca; texto branco so sobre 600+
        // (#C94A00, contraste AA), igual as telas publicas.
        marca: {
          50: '#FFF4EC',
          100: '#FFE7D4',
          200: '#FFD3B0',
          300: '#FDAE7A',
          400: '#F16425',
          500: '#E65300',
          600: '#C94A00',
          700: '#A83E00',
          800: '#8A3300',
          900: '#6B2800',
        },
        // Identidade Mallory (Recepcao publica). `laranja` so em detalhes e
        // sobre o preto; texto branco usa `acao`/`profundo` (contraste AA).
        mallory: {
          preto: '#111111',
          grafite: '#1E1E1E',
          laranja: '#F16425', // da logomarca oficial (public/marca)
          escuro: '#E65300',
          acao: '#C94A00',
          profundo: '#A83E00',
          claro: '#FFF1E6',
          borda: '#FFD3B0',
          fundo: '#F5F6F8',
          texto: '#525866',
        },
      },
      boxShadow: {
        suave: '0 1px 2px rgba(17,17,17,0.04), 0 8px 24px rgba(17,17,17,0.06)',
      },
      fontFamily: {
        sans: ['Inter', '"Segoe UI"', 'system-ui', '-apple-system', 'Roboto', 'sans-serif'],
        exibicao: ['Inter', '"Segoe UI"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        DEFAULT: '6px',
        md: '6px',
        lg: '8px',
      },
      keyframes: {
        // Linha do leitor de QR Code subindo e descendo na moldura.
        varre: {
          '0%, 100%': { top: '6%' },
          '50%': { top: '92%' },
        },
        'sobe-suave': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'entra-vencedor': {
          '0%': { opacity: '0', transform: 'scale(0.97)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        // Carrossel dos ganhadores: troca suave de slide.
        'slide-entra': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        // Brilhos do anúncio do ganhador no telão.
        cintila: {
          '0%, 100%': { opacity: '0.35', transform: 'scale(0.8)' },
          '50%': { opacity: '1', transform: 'scale(1.15)' },
        },
      },
      animation: {
        varre: 'varre 2.2s ease-in-out infinite',
        'sobe-suave': 'sobe-suave 0.3s ease-out',
        'entra-vencedor': 'entra-vencedor 0.45s ease-out both',
        'slide-entra': 'slide-entra 0.5s ease-out both',
        cintila: 'cintila 2.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
