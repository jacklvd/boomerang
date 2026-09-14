// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from 'vitest'

import { captureOrderSubtree, CAPTURE_LIMITS, type CapturedNode } from '../src/extract/capture'

const render = (html: string) => {
  document.body.innerHTML = html
}

const flatten = (root: CapturedNode | null): CapturedNode[] => {
  const out: CapturedNode[] = []
  const walk = (n: CapturedNode) => {
    out.push(n)
    n.children?.forEach(walk)
  }
  if (root) walk(root)
  return out
}

const serialized = JSON.stringify.bind(JSON)

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('form controls', () => {
  it('never carries a value the user typed', () => {
    render(`
      <input type="password" value="hunter2" placeholder="Password">
      <input type="text" value="4111111111111111" autocomplete="cc-number">
      <textarea>my shipping notes</textarea>
      <select><option selected>Visa ending 1111</option></select>
    `)
    const json = serialized(captureOrderSubtree())
    for (const secret of ['hunter2', '4111111111111111', 'my shipping notes', 'Visa ending']) {
      expect(json, secret).not.toContain(secret)
    }
  })

  it('keeps the kind of control and what the page declares it holds', () => {
    render('<input type="text" autocomplete="cc-number">')
    const input = flatten(captureOrderSubtree().root).find((n) => n.tag === 'input')
    expect(input?.attrs).toMatchObject({ type: 'text', autocomplete: 'cc-number' })
  })

  it('descends into no control, so an option label cannot leak', () => {
    render('<select><option>Card ending 4242</option></select>')
    expect(serialized(captureOrderSubtree())).not.toContain('4242')
  })
})

describe('images', () => {
  /* A QR code and a barcode are both <img>, and a data: URI is the artifact
     itself rather than a reference to it. */
  it('never carries an image source', () => {
    render('<img alt="Your return QR code" src="data:image/png;base64,iVBORw0KGgoAAAA">')
    const json = serialized(captureOrderSubtree())
    expect(json).not.toContain('data:image')
    expect(json).not.toContain('iVBORw0')
    expect(json).toContain('Your return QR code')
  })
})

describe('links', () => {
  it('keeps the path and drops the query and fragment', () => {
    render('<a href="https://shop.example/returns/label?token=SECRET#frag">Label</a>')
    const link = flatten(captureOrderSubtree().root).find((n) => n.tag === 'a')
    expect(link?.attrs.href).toBe('https://shop.example/returns/label')
  })

  it('carries no href at all for a non-http scheme', () => {
    render(`
      <a href="javascript:steal()">a</a>
      <a href="data:text/html,<b>x</b>">b</a>
      <a href="mailto:jack@example.com">c</a>
    `)
    const json = serialized(captureOrderSubtree())
    expect(json).not.toContain('javascript:')
    expect(json).not.toContain('data:text')
    expect(json).not.toContain('mailto:')
  })
})

describe('excluded elements', () => {
  it('carries nothing from a script, style, svg or iframe', () => {
    render(`
      <script>window.token = "SECRET"</script>
      <style>.x { color: red }</style>
      <svg><title>SVGTITLE</title></svg>
      <iframe srcdoc="<b>FRAMED</b>"></iframe>
      <p>Wool Overcoat</p>
    `)
    const json = serialized(captureOrderSubtree())
    for (const excluded of ['SECRET', 'color: red', 'SVGTITLE', 'FRAMED']) {
      expect(json, excluded).not.toContain(excluded)
    }
    expect(json).toContain('Wool Overcoat')
  })
})

describe('text', () => {
  it('attributes text to the node that owns it, not to its ancestors', () => {
    render('<div><span>Wool Overcoat</span><span>$180.00</span></div>')
    const nodes = flatten(captureOrderSubtree().root)
    const div = nodes.find((n) => n.tag === 'div')
    expect(div?.text).toBeUndefined()
    expect(nodes.filter((n) => n.text).map((n) => n.text)).toEqual(['Wool Overcoat', '$180.00'])
  })

  it('collapses whitespace and caps the length of one node', () => {
    render(`<p>Wool    Overcoat\n\n  Charcoal</p><p>${'x'.repeat(500)}</p>`)
    const texts = flatten(captureOrderSubtree().root)
      .map((n) => n.text)
      .filter(Boolean) as string[]
    expect(texts[0]).toBe('Wool Overcoat Charcoal')
    expect(texts[1]!.length).toBe(CAPTURE_LIMITS.maxTextPerNode)
  })
})

describe('bounds', () => {
  it('stops at the node cap and says so', () => {
    render(`<div>${'<p>row</p>'.repeat(CAPTURE_LIMITS.maxNodes + 50)}</div>`)
    const capture = captureOrderSubtree()
    expect(capture.truncated).toBe(true)
    expect(capture.nodeCount).toBeLessThanOrEqual(CAPTURE_LIMITS.maxNodes)
  })

  it('stops at the depth cap rather than following a pathological tree', () => {
    const deep = Array.from({ length: CAPTURE_LIMITS.maxDepth + 10 })
      .reduce<string>((inner) => `<div>${inner}</div>`, '<p>deep</p>')
    render(deep)
    const capture = captureOrderSubtree()
    expect(capture.truncated).toBe(true)
    expect(serialized(capture)).not.toContain('deep')
  })

  it('caps a single attribute', () => {
    render(`<div class="${'c'.repeat(400)}"><p>x</p></div>`)
    const div = flatten(captureOrderSubtree().root).find((n) => n.attrs.class)
    expect(div!.attrs.class!.length).toBe(CAPTURE_LIMITS.maxAttrLength)
  })
})

/**
 * The function is handed to `chrome.scripting.executeScript` as `func`, which
 * stringifies it and evaluates it in the page — so it must close over nothing.
 * `tsc` cannot see that constraint. Rebuilding it from its own source and
 * running it is the only check that does.
 */
describe('serialization', () => {
  it('still works when rebuilt from its own source, closing over nothing', () => {
    render('<div class="order"><p>Wool Overcoat</p></div>')
    const rebuilt = new Function(`return (${captureOrderSubtree.toString()})`)() as typeof captureOrderSubtree
    expect(rebuilt()).toEqual(captureOrderSubtree())
  })

  it('names no import in its source', () => {
    const source = captureOrderSubtree.toString()
    expect(source).not.toMatch(/\bCAPTURE_LIMITS\b/)
    expect(source).not.toMatch(/\bimport\b/)
  })

  /* The inlined constants are the price of that constraint, so something has
     to notice when the two copies drift apart. */
  it('inlines the same limits the module exports', () => {
    const source = captureOrderSubtree.toString()
    expect(source).toContain(`= ${CAPTURE_LIMITS.maxNodes}`)
    expect(source).toContain(`= ${CAPTURE_LIMITS.maxDepth}`)
    expect(source).toContain(`= ${CAPTURE_LIMITS.maxTextPerNode}`)
    expect(source).toContain(`= ${CAPTURE_LIMITS.maxAttrLength}`)
  })
})
