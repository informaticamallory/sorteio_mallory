import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tipagem mínima do Node, para não adicionar @types/node só por este arquivo.
declare const process: { env: Record<string, string | undefined> }

// Backend usado pelo servidor de desenvolvimento. API_URL permite apontar para
// outra instancia (ex.: uma copia de validacao) sem mexer no servidor do evento.
const API_URL = process.env.API_URL ?? 'http://127.0.0.1:8000'

// host: true publica o servidor de desenvolvimento na rede local, para que o
// organizador possa operar o painel pelo celular enquanto o telao fica no projetor.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: Number(process.env.PORT ?? 5173),
    proxy: {
      '/api': { target: API_URL, changeOrigin: true },
      '/uploads': { target: API_URL, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
