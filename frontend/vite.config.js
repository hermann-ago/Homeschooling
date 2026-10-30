import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// `npm run build` output is served by the home server. For UI development,
// UI development uses the same home server. Enable Test mode in Settings before experimenting.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Preserve the browser-facing Host so the API can validate its Origin.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
