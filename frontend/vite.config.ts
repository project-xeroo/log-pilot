import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const gateway = process.env.GATEWAY_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // API calls live under /api so they never collide with SPA routes
      // like /feed or /search; the prefix is stripped before the gateway.
      '/api': {
        target: gateway,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      '/ws': {
        target: gateway.replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
