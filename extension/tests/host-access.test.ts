import { describe, expect, it, vi } from 'vitest'

import { FakeChromePermissions, PermissionGestureError } from './fakes/chrome-permissions'
import {
  hasStandingAccess,
  isOfferable,
  patternFor,
  requestStandingAccess,
  revokeStandingAccess,
} from '../src/permissions/host-access'

const ORIGIN = 'https://www.nordstrom.com'

/* `RETAILER_ORIGINS` is empty by design, so `isOfferable` is false for
   everything. These tests stub it to prove the gate works both ways — the
   module must be correct on the day the list is populated, not only today. */
const withRetailers = (...patterns: string[]) =>
  vi.doMock('@/manifest.config', () => ({ RETAILER_ORIGINS: patterns }))

describe('patternFor', () => {
  it('asks for exactly the origin, never a wildcard host', () => {
    expect(patternFor(ORIGIN)).toBe('https://www.nordstrom.com/*')
    expect(patternFor(ORIGIN)).not.toContain('*.')
  })
})

describe('isOfferable', () => {
  /* The shipped list is empty, so nothing is offerable and the screen is never
     shown. That is the correct behaviour today, not a missing feature — and it
     is what stops E2 rendering a button Chrome would refuse. */
  it('offers nothing while no retailer is supported', () => {
    expect(isOfferable(ORIGIN)).toBe(false)
    expect(isOfferable('https://example.com')).toBe(false)
  })

  it('matches an exact declared origin once one exists', async () => {
    vi.resetModules()
    withRetailers('https://www.nordstrom.com/*')
    const mod = await import('../src/permissions/host-access')
    expect(mod.isOfferable(ORIGIN)).toBe(true)
    expect(mod.isOfferable('https://other.com')).toBe(false)
  })

  /* A subdomain wildcard must match on a dot boundary. `*.nordstrom.com`
     matching `evilnordstrom.com` is the classic version of this bug. */
  it('does not let a host wildcard escape its domain', async () => {
    vi.resetModules()
    withRetailers('https://*.nordstrom.com/*')
    const mod = await import('../src/permissions/host-access')
    expect(mod.isOfferable('https://www.nordstrom.com')).toBe(true)
    expect(mod.isOfferable('https://nordstrom.com')).toBe(true)
    expect(mod.isOfferable('https://evilnordstrom.com')).toBe(false)
    expect(mod.isOfferable('https://nordstrom.com.attacker.net')).toBe(false)
  })
})

describe('requestStandingAccess', () => {
  const offerable = async () => {
    vi.resetModules()
    withRetailers('https://www.nordstrom.com/*')
    return import('../src/permissions/host-access')
  }

  it('refuses an origin the manifest never declared', async () => {
    const permissions = new FakeChromePermissions()
    expect(await requestStandingAccess(permissions, ORIGIN)).toBe('not-offerable')
    expect(await hasStandingAccess(permissions, ORIGIN)).toBe(false)
  })

  it('grants inside a user gesture', async () => {
    const mod = await offerable()
    const permissions = new FakeChromePermissions()
    const result = await permissions.duringGesture(() =>
      mod.requestStandingAccess(permissions, ORIGIN),
    )
    expect(result).toBe('granted')
    expect(await mod.hasStandingAccess(permissions, ORIGIN)).toBe(true)
  })

  /* The whole of D7 rests on this: the extension cannot acquire standing access
     without the user acting, even if some later code forgets and calls it on a
     timer. Reported rather than swallowed — it means the user saw nothing. */
  it('reports a call made outside a user gesture, and grants nothing', async () => {
    const mod = await offerable()
    const permissions = new FakeChromePermissions()
    expect(await mod.requestStandingAccess(permissions, ORIGIN)).toBe('no-gesture')
    expect(await mod.hasStandingAccess(permissions, ORIGIN)).toBe(false)
  })

  it('keeps a decline distinct from a mis-call', async () => {
    const mod = await offerable()
    const permissions = new FakeChromePermissions()
    permissions.denyNextRequest()
    const result = await permissions.duringGesture(() =>
      mod.requestStandingAccess(permissions, ORIGIN),
    )
    expect(result).toBe('denied')
    expect(await mod.hasStandingAccess(permissions, ORIGIN)).toBe(false)
  })

  it('lets an unexpected failure surface rather than reporting a denial', async () => {
    const mod = await offerable()
    const broken = {
      contains: async () => false,
      request: async () => {
        throw new Error('Chrome is on fire')
      },
      remove: async () => true,
    }
    await expect(mod.requestStandingAccess(broken, ORIGIN)).rejects.toThrow('on fire')
  })
})

describe('revokeStandingAccess', () => {
  it('gives the permission back', async () => {
    const permissions = new FakeChromePermissions()
    permissions.grant(patternFor(ORIGIN))
    expect(await hasStandingAccess(permissions, ORIGIN)).toBe(true)
    await revokeStandingAccess(permissions, ORIGIN)
    expect(await hasStandingAccess(permissions, ORIGIN)).toBe(false)
  })
})

describe('the gesture rule itself', () => {
  it('closes the window again after the handler returns', async () => {
    const permissions = new FakeChromePermissions()
    await permissions.duringGesture(async () => {})
    await expect(permissions.request({ origins: [patternFor(ORIGIN)] })).rejects.toThrow(
      PermissionGestureError,
    )
  })
})
