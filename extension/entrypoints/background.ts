/**
 * Placeholder so WXT has an entrypoint to build. WXT refuses to build an empty
 * `entrypoints/`, which Task 1.2 step 5 asks for and its own verification step
 * contradicts — a build cannot produce `.output/chrome-mv3/` with nothing to
 * compile. The stub is the smaller of the two compromises.
 *
 * dev-note: Task 8.2 owns this file and replaces it with the real worker wiring
 * graph. Nothing here should grow — if you are reaching for message handlers or
 * storage, you are writing 8.2 early.
 */
export default defineBackground(() => {})
