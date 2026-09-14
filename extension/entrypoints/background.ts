/**
 * Placeholder so WXT has an entrypoint to build — WXT refuses to build an empty
 * `entrypoints/`, and a build has to produce `.output/chrome-mv3/` for the
 * manifest test to assert against.
 *
 * dev-note: the real worker wiring graph replaces this wholesale. Nothing here
 * should grow — if you are reaching for message handlers or storage, that work
 * belongs in the worker, not in the stub that exists to satisfy a bundler.
 */
export default defineBackground(() => {})
