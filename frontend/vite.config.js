import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      // Learner and staff photos are served by Django in dev.
      '/media': 'http://127.0.0.1:8000',
    },
  },
})
