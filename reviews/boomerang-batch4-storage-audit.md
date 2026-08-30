# Batch 4 Storage Audit

Scope: `design/boomerang-low-level-design.md` §3.4 and §5.2, and `plan/boomerang-plan.md` Batch 4
Task 4.6–4.14, cross-checked against `design/boomerang-requirements.md` and
`design/boomerang-high-level-design.md` where they touch these. Audit only — nothing else in the
repository was modified. This document is the only file written.

## Headline

**2 Must findings, in scope.** Batch 4 as written is not executable by a coding agent with no other
context: Task 4.7 cannot pass its own stated verification step given its own stated prerequisites
(Finding 1), and the eviction contract §5.2 declares "narrow and absolute" is violated by the one
place downstream (Task 8.2) that actually calls it for routine ingestion (Finding 2, which sits just
outside the literal Batch 4 task range but is the load-bearing citing site for the §5.2 rule this
audit was scoped to check). This is not zero, and this review cycle should not stop here.

## Findings

### Must — 1. Task 4.7's `single-set-law.test.ts` cannot be written or pass at the point the plan places it

**Section:** `plan/boomerang-plan.md` Task 4.7, step 7 (lines 2050–2065) and its Verification (line
2071); cross-checked against Task 4.7's own Prerequisites and the Task Status Tracker (lines
4031–4037) and the plan's own "Critical Path" diagram (lines 4107–4126).

Task 4.7's **Prerequisites** are stated as `Task 4.6` only, and the tracker confirms it:

> `| 4.7 | StorageCoordinator.transact — the serialising queue | 4.6 | 4.6, 4.12 (coordinator.ts) | [ ] |`

Yet step 7 requires Task 4.7 itself to create `tests/storage/single-set-law.test.ts` with five rows,
"each row driving **the real call** against the Task 2.6 fake and asserting `set` was called
**exactly once**":

> - `PickupRepository.save_intent` — the pickup and its `ConsentStamp`;
> - `PickupRepository.promote` — the intent and the confirmed booking;
> - `ReturnDriver`'s `transition` — the return request and the driver session;
> - the §4.5 already-collected branch — the pickup's `Collected` and the request's `LabelPrinted`;
> - `clear_all` — three collections and the address.

And the task's own Verification section requires this to pass as part of completing Task 4.7:

> `cd extension && bun run test tests/storage/single-set-law.test.ts` — five rows, each asserting a
> single `set` call.
> - Split any one of the five into two `set` calls — that row fails; revert.

None of the five rows can execute a real call at the point Task 4.7 sits in the dependency graph:

- `PickupRepository.save_intent`/`promote` are built in **Task 4.10**, which lists `Task 4.7` as its
  own prerequisite (line 2136) — it runs *after* 4.7, not before.
- `ReturnRepository` (needed for the §4.5 already-collected branch, which touches both `PICKUP` and
  `RETURN_REQUEST`) is built in **Task 4.9**, also a downstream consumer of 4.7 (line 2108).
- `StorageCoordinator.clear_all` is built in **Task 4.12**, which requires Tasks 4.8–4.11 to already
  exist (line 2207) — three layers downstream of 4.7.
- `ReturnDriver.transition` does not exist anywhere in `extension/src/` until **Task 6.6** (line
  2719), two full batches later. `extension/src/driver/driver.ts` is not created until then.

The plan's own critical-path diagram makes the same gap visible independently of the task text:

> ```
>  →  4.6  storage keys, rebuild, and barrel    [extension/src/storage]
>  →  4.7  StorageCoordinator.transact          [extension/src/storage]
>  →  4.9  ReturnRepository                     [extension/src/storage]
>  →  6.6  ReturnDriver, transition, start      [extension/src/driver]
>  ...
> ```
> (lines 4109–4113)

Task 4.6 does stub the four repository module bodies with `throw new Error("not implemented")` (Task
4.6 step 4), so at Task 4.7's execution point `PickupRepository.save_intent` exists as a function
that throws on every call — calling it from a test asserting a successful single `set` cannot pass.
`ReturnDriver` is not even stubbed at that point; nothing in `src/driver/` exists until Batch 6, so a
test importing it would fail to compile, not merely fail to pass.

No later task revisits or extends `tests/storage/single-set-law.test.ts` — it is named nowhere else
in the plan (`grep -n "single-set-law" plan/boomerang-plan.md` returns only the two Task 4.7 lines
above). So there is no task anywhere in the plan whose prerequisites are satisfied at the moment it
is asked to write and pass all five rows.

**This is not an ambiguity a competent agent could resolve by judgment call** — it is a hard
contradiction between what Task 4.7 is told to verify and what code exists when it runs. An
implementing agent following the plan literally will either fail Task 4.7's verification step, or
quietly narrow the scope (e.g. write only the rows it can satisfy, or fake the missing calls), which
is exactly the "wrong call... silent" failure mode this audit was commissioned to catch — the design
correctly states the law and the correct five invariants (§8.2, line 2680, matches Task 4.7's five
rows exactly), but the plan places its sole enforcement point at a point in the DAG where it cannot
be enforced.

**Recommended fix (for a future round, not made here):** either move step 7's file-creation to a task
that runs after 4.9, 4.10, 4.12 and — for the `ReturnDriver` row — after 6.6 (which breaks Batch 4's
self-containment and the very barrel-parallelization win Task 4.6 was rewritten to buy), or split the
single-set-law suite so each row lands in the task that first makes its real call possible, with a
final "collect and verify all five" checkpoint task added after Task 7.10 (where the last row's real
call, `cancel_pickup`'s already-collected branch, is actually implemented — see Task 7.10, line
3304). The second option is more consistent with the plan's other cross-batch test-consolidation
patterns.

### Must — 2. Task 8.2 calls `evict_to_fit` from the worker for routine ingestion, which §5.2 forbids absolutely, and uses the wrong evictor for the job

**Section:** `design/boomerang-low-level-design.md` §5.2 (in scope), cited against
`plan/boomerang-plan.md` Task 8.2 (Batch 8 — outside the literal Batch 4 task range, but this is the
only call site in the entire plan for the eviction rule this audit was scoped to check, so it is
reported here rather than silently dropped).

§5.2 states the rule as absolute, in these exact words:

> The rule that follows is narrow and absolute: `evict_to_fit` is callable **only** from the
> coordinator's quota-rejection path, never from a repository, never from the worker, and never from
> a second transaction.

§5.2's table also draws the two evictors as answering different, mutually exclusive triggers:

> | Eviction, by count | `evict_if_over_cap` runs after every ingest, ordered by `first_seen_at`,
> skipping orders with a non-terminal return or an unsettled pickup |
> | Eviction, by bytes | `evict_to_fit` runs only on a quota rejection, same order and same skip
> rule, until the store has freed what the write needs |

§4.1's own sequence diagram for ordinary ingestion draws the count-based evictor, not the byte-based
one:

> `SW->>SW: persist, then evict if over cap` (line 1439)

Task 8.2, step 4 — the only place in the plan that wires up ingestion — reads:

> Implement §4.1 ingestion: receive the extracted payload → `POST /orders/ingest` → validate →
> `evict_to_fit` then `OrderRepository.upsert` inside one `transact` → notify the popup.
> (line 3383)

This is wrong on two independent axes:

1. **Wrong evictor.** Routine ingestion should call `evict_if_over_cap` (count-based, unconditional,
   run *after* persisting, per §4.1's diagram), not `evict_to_fit` (byte-based, reactive to an actual
   quota rejection). Task 8.2 never mentions `evict_if_over_cap` at all — it is defined in Task 4.12
   and then never called anywhere in the plan.
2. **Wrong trigger and wrong caller.** Even granting `evict_to_fit` were the right evictor here, §5.2
   makes calling it unconditionally from the worker's own ingestion handler exactly the case its
   "narrow and absolute" rule forbids ("never from the worker"). `evict_to_fit` is specified as
   something the *coordinator* invokes internally, only after its own `set` has actually been
   rejected for quota — not something a caller runs pre-emptively before attempting a write.

The practical consequence if Task 8.2 is implemented as written: the extension's order store would
never enforce `MAX_STORED_ORDERS` (the count cap) during normal use — `evict_if_over_cap` is defined
but has no caller anywhere in the plan — and every ingest would instead run a byte-margin eviction
pass keyed to the incoming write's size, which is a different and much weaker guarantee than the one
FR-3.1.5 and §5.2 specify.

**Confidence:** high. Both quotes are unambiguous and the contradiction is direct — this is not a
plan/design disagreement to be resolved by picking a side; the design's language ("narrow and
absolute") explicitly anticipates and forbids exactly what the plan's only wiring task does.

### Should — 3. `single-set-law.test.ts`'s five rows omit eviction's own order+return cross-record delete

**Section:** `design/boomerang-low-level-design.md` §3.4, cross-checked against Task 4.7 step 7 and
Task 4.12.

§3.4 states, of the mechanical test for "invariant": *"if the worker died between them, is the
resulting store a state some section of this document declares unreachable?"* It then separately
states, of eviction:

> `ReturnRepository.delete(item_ids)` exists because ... eviction has to take return requests with
> the orders they belong to ... a `RETURN_REQUEST` keyed to an item whose order is gone is
> unreachable ... and would sit in the quota forever.

By the document's own mechanical test, deleting an order without deleting its (non-active) return
requests in the same `set` produces exactly the "unreachable" state §3.4 names — so this pair
qualifies as a sixth invariant under the law. Neither §8.2's enumeration (line 2680) nor Task 4.7
step 7's five named rows include it, and Task 4.12's own unit test list (step 6) does not assert this
pairing's atomicity either — the closest listed test, "eviction inside a `transact` does not
deadlock," checks re-entrancy, not the single-`set` property.

This is very likely safe in practice — eviction's deletes naturally happen inside one evictor
callback the same way `clear_all`'s do — but the law's own stated purpose ("the point of the law is
that the *next* multi-record write is correct by default") is exactly what a missing row undermines:
if a future refactor split the order delete and the return delete into two `set` calls, nothing in
`single-set-law.test.ts` would catch it, because eviction is not one of its rows. Low-to-medium
severity; recommend adding it as a sixth row when Finding 1 is resolved.

### Should — 4. Six Reference lines in Batch 4 cite the wrong Low-Level Design section

**Section:** `plan/boomerang-plan.md` Tasks 4.6, 4.7, 4.8, 4.9, 4.10, 4.11.

Every storage task in Track C cites "Low-Level Design §5.1" in its Reference line:

> - Task 4.6, line 2002: `Reference: Low-Level Design §5.1, §3.4; requirements FR-3.1.5, FR-3.4.5a, NFR-6.5; decision D19.`
> - Task 4.7, line 2067: `Reference: Low-Level Design §3.4, §4.3, §5.1, §7.2, §8.2.`
> - Task 4.8, line 2097: `Reference: Low-Level Design §3.4, §5.1; requirements FR-3.1.5.`
> - Task 4.9, line 2125: `Reference: Low-Level Design §3.4, §5.1; requirements FR-3.3.9, FR-3.3.10.`
> - Task 4.10, line 2168: `Reference: Low-Level Design §3.4, §5.1; requirements FR-3.4.3, FR-3.4.4, FR-3.4.5, FR-3.4.5a.`
> - Task 4.11, line 2195: `Reference: Low-Level Design §3.5, §4.4, §5.1; requirements FR-3.3.5, FR-3.4.2.`

But Low-Level Design §5.1 is **"The server has none"** — a four-line paragraph stating the server
has no ORM, no migrations, no connection pool, no transaction boundaries. It has nothing to do with
the extension. The section that actually contains the key layout, atomicity rule, eviction behaviour,
derived-state rules and rebuild carve-out every one of these six tasks describes is **§5.2, "The
extension's store"** — the section this audit was scoped to review. This reads as a mechanical
mix-up, plausibly from the fact that both the requirements document and the low-level design number
their server/extension split the same way (requirements §5.1 = server config, §5.2 = extension
config), so a citation generator matching on section number rather than title landed on the wrong
document's §5.1.

**Impact:** low — every one of these tasks also correctly cites §3.4, and each instruction's body
restates the relevant §5.2 content inline, so an implementing agent is not actually starved of
context. But an agent that follows the citation to consult §5.1 directly will find it irrelevant, and
the mis-citation is systematic (6 of 6 storage tasks) rather than a one-off typo, which is exactly the
class of small, cheap, easy-to-miss defect this audit exists to surface. A one-line six-occurrence
find/replace (`Low-Level Design §5.1` → `Low-Level Design §5.2`, scoped to Task 4.6–4.11) fixes it.

## What did *not* turn out to be a finding (checked and dropped)

- **`ReadOnlyStore`'s seven members.** Verified identical, member-for-member and in the same order,
  across the §3.4 class diagram (lines 1227–1242), the §3.4 prose (line 1245), the §3.5 types table
  (line 1333), §5.2's usage note (lines 2525–2528), §8.2's test row (line 2678), and plan Task 4.7
  steps 5–6 (lines 2031, 2046) and Task 8.3's citation (line 3417). No divergence found.
- **The `Cancelled`→`Abandoned` vocabulary change.** Verified consistent across requirements (lines
  160–171, 285–289), high-level design (lines 324–367), low-level design (§3.4 lines 1701–1716, §5.2,
  §10 decision log line 3225), and the plan (lines 855–860, 2158, 3287). No document still names
  `Cancelled`.
- **`promote` as a single-set-law row.** Initially looked wrong — `promote` only ever touches the
  `PICKUP` record's own fields, and §3.4 explicitly says a many-field write to *one* record is not an
  invariant needing the law. But `BOOKED_ADDRESS` is its own ERD entity in a `PICKUP ||--|| BOOKED_ADDRESS`
  relationship (high-level design line 211, requirements line 65), not a field — so `promote` genuinely
  writes two records and its inclusion in the five rows is correct.
- **`evict_to_fit` running inside the failing `transact` rather than through it.** Per this audit's
  brief, already checked and dropped as a false positive in round 7; re-verified against §5.2's own
  argument (lines 1990–1999) and found sound *for `evict_to_fit` itself*. (Finding 2 above is a
  different claim: that a different task calls the wrong evictor from the wrong place, not that
  `evict_to_fit`'s own bypass of `transact` is unsound.)
- **The four eviction/settlement constants.** `MAX_STORED_ORDERS`, `PICKUP_SETTLED_AFTER_DAYS`,
  `BOOKING_ABANDONED_AFTER_HOURS`, `STORAGE_EVICTION_MARGIN_BYTES` are all declared in requirements
  §5.2 (lines 1058–1067) with defaults, and the low-level design's own decision-log table (lines
  2486–2493) cross-checks the same four values. Consistent.

## Verdict: is Batch 4 executable as written?

**No, not as a self-contained batch.** Finding 1 means Task 4.7 — the second task in Batch 4's
critical chain, and the one every other storage task depends on — cannot satisfy its own stated
verification step using only what its own stated prerequisites provide. A coding agent handed Task
4.7 in isolation (the plan's stated model: "handed to coding agents with no other context") will hit
this immediately, either failing the task or silently under-delivering it. Everything else in Batch 4
Track C (Tasks 4.8–4.12, and the plan's parallelization case for the barrel-file rewrite, Task 4.6
step 4's "Why this changed" note) is sound and was the correct fix for what it targeted — the barrel
rewrite genuinely does make 4.8–4.11 mutually parallel, and nothing in this audit found fault with
that mechanism itself.

Finding 2 means that even if Batch 4 is patched and lands cleanly, the eviction design it builds is
not actually reachable correctly from anywhere in the current plan — Batch 8's Task 8.2 is the only
wiring for ingestion-time eviction, and it wires the wrong evictor in the wrong place. This does not
block Batch 4's own execution, but it means Batch 4's storage layer, if built exactly to spec, would
still not be exercised correctly by the rest of the plan as currently written.

## Where plan and design disagree, and which is right

- **Task 4.7 vs. its own prerequisites (Finding 1):** not a plan/design disagreement — both plan and
  design agree on what the law requires and which five things are invariants (§8.2 and Task 4.7 step
  7 name the identical five). The defect is purely in the plan's task sequencing, not in a
  disagreement over content. The design is silent on where the test should live in the batch order;
  the plan invented the placement and got it wrong.
- **Task 8.2 vs. §5.2 (Finding 2):** a direct disagreement, and the design is right. §5.2's rule is
  explicit, "narrow and absolute," and correctly distinguishes the two evictors' triggers; Task 8.2
  contradicts it outright rather than interpreting it loosely. This should be corrected in the plan,
  not the design.

## Scope discipline

Only `reviews/boomerang-batch4-storage-audit.md` was written. No other file in the repository was
read-then-modified, and nothing was staged or committed. `design/boomerang-low-level-design.md`,
`design/boomerang-high-level-design.md`, `design/boomerang-requirements.md`,
`plan/boomerang-plan.md`, and `reviews/boomerang-low-level-design-review.md` were read only.

## Recommendation

**One more fix round before implementation starts — do not begin coding Batch 4 yet.** Finding 1 is a
hard blocker: literally following the plan produces a task that cannot pass its own verification
step. Finding 2 is a hard blocker for correctness even after Batch 4 lands, since it means the
eviction design has no correct caller anywhere in the plan as written. Both are narrow, mechanical
fixes — a resequencing of one test file's rows (or a defer-and-collect split) for Finding 1, and a
one-line correction to Task 8.2 step 4 for Finding 2 — and neither implicates the design documents
(§3.4 and §5.2 are sound as written; this is a planning-layer defect in both cases). Given the
project's round-7 pattern of fixes landing cleanly outside the section that raised them, I'd expect
one more targeted pass to close both cleanly without reopening previously-settled ground — the two
Should findings can ride along in the same pass at near-zero marginal cost.
