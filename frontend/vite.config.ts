import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// In dev, /api is proxied to the FastAPI backend (override with BOB_API_PROXY).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: process.env.BOB_API_PROXY ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
})
