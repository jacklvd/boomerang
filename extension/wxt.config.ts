import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'wxt'

import { buildManifest } from './manifest.config'

/* dev-note: `@vitejs/plugin-react` is wired directly rather than through
   `@wxt-dev/module-react`. The module pins plugin-react 6, which requires Vite
   8, while WXT 0.20 ships Vite 7 — so the module cannot load. Its only other
   job is registering React auto-imports, which this workspace does not use.
   Revisit when WXT moves to Vite 8. */
export default defineConfig({
  manifestVersion: 3,
  manifest: () => buildManifest(),
  vite: () => ({ plugins: [react(), tailwindcss()] }),
})
