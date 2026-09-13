import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { DASHBOARD_ORIGIN, assertReleaseOrigin, buildManifest } from '../manifest.config'

const manifest = buildManifest(false)
const serialized = JSON.stringify(manifest)

describe('manifest permission posture', () => {
  it('requests exactly activeTab, scripting and storage at install', () => {
    expect(manifest.permissions).toEqual(['activeTab', 'scripting', 'storage'])
  })

  it('never mentions <all_urls> anywhere', () => {
    expect(serialized).not.toContain('<all_urls>')
  })

  it('does not request unlimitedStorage', () => {
    expect(serialized).not.toContain('unlimitedStorage')
  })

  it('declares no host permissions as required', () => {
    expect(manifest).not.toHaveProperty('host_permissions')
  })

  it('allows no remote script', () => {
    expect(manifest.content_security_policy.extension_pages).toBe(
      "script-src 'self'; object-src 'self'",
    )
  })
})

describe('externally_connectable', () => {
  const matches = manifest.externally_connectable.matches

  it('contains only the configured dashboard origin', () => {
    expect(matches).toEqual([`${DASHBOARD_ORIGIN}/*`])
  })

  it('uses a concrete host, never a host wildcard', () => {
    // The trailing path wildcard is required by Chrome; a host wildcard is not.
    for (const pattern of matches) {
      const host = pattern.replace(/^\w+:\/\//, '').split('/')[0]
      expect(host).not.toContain('*')
    }
  })

  it('never names a retailer origin', () => {
    for (const pattern of matches) {
      expect(pattern.startsWith(DASHBOARD_ORIGIN)).toBe(true)
    }
  })
})

describe('release origin guard', () => {
  it('rejects a localhost origin in a production build', () => {
    expect(() => assertReleaseOrigin('http://localhost:3000', true)).toThrow(
      /concrete production dashboard origin/,
    )
    expect(() => assertReleaseOrigin('http://127.0.0.1:3000', true)).toThrow()
  })

  it('allows localhost outside a release build', () => {
    expect(() => assertReleaseOrigin('http://localhost:3000', false)).not.toThrow()
  })

  it('allows a concrete origin in a release build', () => {
    expect(() => assertReleaseOrigin('https://app.boomerang.example', true)).not.toThrow()
  })
})

/**
 * The tests above check the source object. These check what WXT actually wrote,
 * because WXT injects into the manifest — `version`, the background service
 * worker, and in dev mode extra permissions for hot reloading. Only the built
 * artifact proves the posture of the thing that gets loaded.
 *
 * `bun run test` builds first so this file is always present.
 */
describe('built manifest', () => {
  const builtPath = new URL('../.output/chrome-mv3/manifest.json', import.meta.url)
  const built = JSON.parse(readFileSync(builtPath, 'utf8'))

  it('is manifest v3', () => {
    expect(built.manifest_version).toBe(3)
  })

  it('still requests exactly the three install permissions after WXT injection', () => {
    expect(built.permissions).toEqual(['activeTab', 'scripting', 'storage'])
  })

  it('carries no host permissions and no <all_urls>', () => {
    expect(built).not.toHaveProperty('host_permissions')
    expect(JSON.stringify(built)).not.toContain('<all_urls>')
  })

  it('keeps externally_connectable pinned to the dashboard origin', () => {
    expect(built.externally_connectable.matches).toEqual([`${DASHBOARD_ORIGIN}/*`])
  })

  it('has no key yet — Task 1.4 adds it', () => {
    expect(built).not.toHaveProperty('key')
  })
})
