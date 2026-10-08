import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const rootDir = import.meta.dirname

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./frontend/src/__tests__/setup.ts'],
    include: ['./frontend/src/**/*.spec.ts'],
    // Node >=24 ships a built-in (file-backed) localStorage global that shadows
    // jsdom's implementation and resolves to `undefined` without --localstorage-file.
    // Disable it so the jsdom environment owns Web Storage.
    execArgv: ['--no-experimental-webstorage'],
  },
  resolve: {
    alias: {
      '@': path.resolve(rootDir, './frontend/src'),
      '@apps': path.resolve(rootDir, '../'),
    },
  },
})
