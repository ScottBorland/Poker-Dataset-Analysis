import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/query': 'http://127.0.0.1:8000',
      '/sql': 'http://127.0.0.1:8000',
      '/fingerprints': 'http://127.0.0.1:8000',
      '/spots': 'http://127.0.0.1:8000',
      '/hands': 'http://127.0.0.1:8000',
      '/hand-builder': 'http://127.0.0.1:8000',
      '/solve': 'http://127.0.0.1:8000',
    },
  },
})
