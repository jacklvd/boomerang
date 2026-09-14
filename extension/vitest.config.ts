import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
  },
  /* Mirrors the `@/*` alias WXT generates into .wxt/tsconfig.json. Without it
     tsc resolves a module the test runner cannot, and the two disagree about
     whether the code compiles. */
  resolve: {
    alias: { '@': fileURLToPath(new URL('.', import.meta.url)) },
  },
})
