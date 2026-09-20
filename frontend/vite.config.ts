/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// Hostnames the dev server answers to, beyond localhost. A reverse proxy
// forwards the original Host header, which Vite's host check rejects
// otherwise. Comma-separated, e.g. VITE_ALLOWED_HOSTS=boards.example.com
const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean)

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
})
