import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the Django API runs on :8000; Vite proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    chunkSizeWarningLimit: 1100, // maplibre-gl alone is ~1 MB minified
    rollupOptions: {
      output: { manualChunks: { maplibre: ['maplibre-gl'] } },
    },
  },
})
