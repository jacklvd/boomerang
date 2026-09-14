/**
 * The in-page half of order ingestion: walk the live DOM into a bounded tree.
 *
 * Architecture step 3 is "the extension extracts a bounded, sanitized order
 * subtree and sends it to the API" — step 4, normalization, happens
 * server-side. So nothing here parses an order. This decides what is even
 * *eligible* to leave the page, and `sanitize()` decides what actually does.
 *
 * ## This function is serialized
 *
 * It is handed to `chrome.scripting.executeScript` as `func`, which stringifies
 * it and evaluates it in the page. It therefore closes over nothing: no
 * imports, no module constants, no helpers outside its own body. Adding one
 * silently breaks it at runtime in a way `tsc` cannot see — the jsdom test that
 * calls it directly is what catches that.
 *
 * ## Two things it must never do
 *
 * Never read the value of a form control. Not password, not payment, not
 * anything — a value the user typed is not order data, and the cheapest way to
 * never leak one is to never hold one.
 *
 * Never capture an image's data. A QR code and a barcode are both `<img>`, and
 * a `data:` URI carries the artifact itself.
 */

export type CapturedNode = {
  tag: string
  attrs: Record<string, string>
  /** Own text only — a node's text is not repeated inside its ancestors. */
  text?: string
  children?: CapturedNode[]
}

export type Capture = {
  root: CapturedNode | null
  nodeCount: number
  /** True when a cap stopped the walk, so the server knows the tree is partial. */
  truncated: boolean
}

/**
 * Does an injection result actually have the shape this module promises?
 *
 * `executeScript` types `result` as `any`, and a page can answer with something
 * that is not a capture at all: a page-side throw surfaces as an error object,
 * a frame Chrome entered but did not run our function in returns whatever it
 * had. Casting instead would hand `sanitize` garbage, and a report counting
 * zero redactions in a tree it never understood is worse than no report.
 *
 * The top level is the whole check. Everything below `root` was built by
 * `captureOrderSubtree` in one pass or does not exist — a tree that starts
 * right does not go wrong halfway down, and validating every node would be a
 * parser guarding against a bug we would rather fix than tolerate.
 */
export function isCapture(value: unknown): value is Capture {
  if (typeof value !== 'object' || value === null) return false
  const { root, nodeCount, truncated } = value as Capture
  if (typeof nodeCount !== 'number' || typeof truncated !== 'boolean') return false
  return root === null || (typeof root === 'object' && typeof root.tag === 'string')
}

export const CAPTURE_LIMITS = {
  maxNodes: 1500,
  maxDepth: 24,
  maxTextPerNode: 240,
  maxAttrLength: 120,
} as const

export function captureOrderSubtree(): Capture {
  /* Inlined rather than imported: see the note above about serialization.
     Keep these in step with CAPTURE_LIMITS — the test asserts they match. */
  const MAX_NODES = 1500
  const MAX_DEPTH = 24
  const MAX_TEXT = 240
  const MAX_ATTR = 120

  /* Carry no content whatever the rest of the rules say. */
  const SKIP_TAGS = new Set([
    'script',
    'style',
    'noscript',
    'template',
    'svg',
    'canvas',
    'iframe',
    'object',
    'embed',
    'video',
    'audio',
    'picture',
    'source',
    'link',
    'meta',
    'head',
    'base',
  ])

  /* Structural hints the parser needs, and nothing that carries a value. */
  const KEEP_ATTRS = ['class', 'id', 'role', 'type', 'data-testid', 'itemprop', 'datetime']

  let nodeCount = 0
  let truncated = false

  const walk = (element: Element, depth: number): CapturedNode | null => {
    const tag = element.tagName.toLowerCase()
    if (SKIP_TAGS.has(tag)) return null

    if (nodeCount >= MAX_NODES || depth > MAX_DEPTH) {
      truncated = true
      return null
    }
    nodeCount += 1

    const attrs: Record<string, string> = {}
    for (const name of KEEP_ATTRS) {
      const value = element.getAttribute(name)
      if (value) attrs[name] = value.slice(0, MAX_ATTR)
    }

    /* A control's presence and kind are structure; its contents are the user's.
       `autocomplete` is the standards-defined declaration of what a field is
       for, which is what lets the guard recognise a payment or address field
       without a heuristic. */
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      const autocomplete = element.getAttribute('autocomplete')
      if (autocomplete) attrs.autocomplete = autocomplete.slice(0, MAX_ATTR)
      return { tag, attrs }
    }

    /* An image's src may be the artifact itself — a QR code, a barcode, a
       label. Its dimensions and alt text are enough to know one is there. */
    if (tag === 'img') {
      const alt = element.getAttribute('alt')
      if (alt) attrs.alt = alt.slice(0, MAX_ATTR)
      return { tag, attrs }
    }

    if (tag === 'a') {
      const href = element.getAttribute('href') ?? ''
      /* Query strings and fragments are where signed tokens live, so the path
         survives and everything after it does not. A non-http scheme —
         `javascript:`, `data:`, `mailto:` — is dropped whole. */
      try {
        const url = new URL(href, document.baseURI)
        if (url.protocol === 'http:' || url.protocol === 'https:') {
          attrs.href = `${url.origin}${url.pathname}`.slice(0, MAX_ATTR)
        }
      } catch {
        /* Not a resolvable URL. Nothing worth carrying. */
      }
    }

    const children: CapturedNode[] = []
    let text = ''

    for (const child of Array.from(element.childNodes)) {
      if (child.nodeType === 3) {
        text += child.textContent ?? ''
      } else if (child.nodeType === 1) {
        const captured = walk(child as Element, depth + 1)
        if (captured) children.push(captured)
      }
    }

    const node: CapturedNode = { tag, attrs }
    const trimmed = text.replace(/\s+/g, ' ').trim()
    if (trimmed) node.text = trimmed.slice(0, MAX_TEXT)
    if (children.length > 0) node.children = children
    return node
  }

  const root = document.body ? walk(document.body, 0) : null
  return { root, nodeCount, truncated }
}
