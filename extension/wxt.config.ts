import { defineConfig } from 'wxt'

import { buildManifest } from './manifest.config'

export default defineConfig({
  manifestVersion: 3,
  manifest: () => buildManifest(),
})
