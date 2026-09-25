import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run build` output is served by the home server. For UI development,
// `npm run dev` proxies API calls to a home server on port 8000.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
