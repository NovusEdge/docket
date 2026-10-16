import path from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import license from 'rollup-plugin-license'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  // `npm run dev` proxies the API to a running `docket graph --web --port 7347`.
  server: { proxy: { '/api': 'http://127.0.0.1:7347' } },
  build: {
    outDir: '../docket/web/dist',
    emptyOutDir: true,
    rollupOptions: {
      plugins: [
        license({
          thirdParty: { output: path.resolve(import.meta.dirname, '../docket/web/dist/THIRD_PARTY_LICENSES.txt') },
        }),
      ],
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
