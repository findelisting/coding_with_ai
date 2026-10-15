import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Send API calls to the FastAPI backend, so no CORS setup is needed in dev.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
