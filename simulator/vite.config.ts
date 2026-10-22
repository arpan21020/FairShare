import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, API calls go to the orchestrator on port 8001.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8001' },
  },
})
