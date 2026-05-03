import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

// Dev server proxy target (Compose sets API_PROXY_TARGET=http://api:8000).
const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
const srcDir = fileURLToPath(new URL('./src', import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': srcDir },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // Frontend calls `/api/...` so paths stay distinct from Vite assets; backend routes have no `/api` prefix.
      '/api': {
        target: apiProxyTarget,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
