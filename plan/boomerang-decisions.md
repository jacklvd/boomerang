# Boomerang — Plan Review Decisions

**Date:** 2026-08-27
**Reviewed document:** [`plan/boomerang-plan.md`](boomerang-plan.md) at 79 tasks / 10 batches
**Method:** adversarial interview across six rounds, each finding checked against the repository
rather than against the documents describing it.

This record exists because several of the decisions below are not derivable from the plan, the
designs, or the code — they are choices about scope, sequencing and risk that a reader six weeks
from now would otherwise have to reverse-engineer. Each entry states the defect found, the decision
taken, and the edit it implies. Where a decision contradicts an upstream design document, that is
named explicitly and the amendment is listed.

The plan grows from **79 tasks to 91**, and its honest makespan is restated from a claimed 19 slots
to roughly **35** — the 79-task plan never cost 19 either; 19 was its dependency floor, and the hard
commit barrier at each batch boundary was already being paid without being counted.

**`Dn` in this document is local to this document.** [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
carries an older `D1`–`D7` series of product decisions, and both series are cited in the same
sections of the requirements and the high-level design. Every reference this review introduced
upstream is written as "plan decision `Dn`" for that reason.

---

## Summary of changes

| # | Decision | Touches |
|---|----------|---------|
| D1 | Add a blocking **Batch 0** feasibility spike | plan, HLD Q5/Q6 |
| D2 | Batch 0 exits with scrubbed, committed fixtures | plan |
| D3 | Batch 0 applies for USPS API access on day one | plan |
| D4 | Batch 0 measures Bedrock parse and action latency | plan, HLD Q9 |
| D5 | Batch 0 blocks only retailer-shaped work | plan |
| D6 | **Cut FR-3.6.3** (dashboard → extension messaging) from PoC scope | plan, requirements, HLD Q1/Q8 |
| D7 | Rewrite `infra/` for the Lambda architecture | plan, HLD Q3 |
| D8 | Retire `infra/AGENTS.md`'s "Legacy scaffold" section when I.1 lands | plan, HLD Q3 |
| D9 | Infra runs as a **track opening after Task 6.5**, not a trailing batch | plan |
| D10 | `.github/workflows/ci.yml` lands in **Batch 1** | plan |
| D11 | Keep the batch barriers; restate the schedule honestly | plan |
| D12 | Keep the doc-derived USPS mocks; add a sandbox reconciliation task | plan, HLD Q11 |
| D13 | Extension coverage gate: 95% line + branch over `src/` | plan |
| D14 | Extend `.husky/pre-commit` to the extension workspace | plan |
| D15 | Add a repo-level `contracts/` directory of golden wire payloads | plan |
| D16 | Name the client-version header upstream | plan, requirements §4.1 |
| D17 | Fix three wrong configuration-parameter names; add a missing one | plan |
| D18 | Extend the Task 10.2 sweep to configuration-parameter names | plan |
| D19 | Split the storage barrel; one file per repository | plan |
| D20 | Generate the pinned extension keypairs in Batch 1 | plan, HLD Q4 |
| D21 | Split `MockUspsAdapter` into a scripted double and a runtime stub | plan |
| D22 | Label mock-backed bookings as simulated in the popup | plan, requirements FR-3.4.5b/§5.1 |
| D23 | Add a manual acceptance task after Batch 8 | plan |
| D24 | Two agents; per-task approval on the driver and storage spines | plan |
| D25 | Amend upstream documents rather than working around them | requirements, HLD |
| D26 | Generalize carrier pickup to configured third-party carriers | requirements, HLD, LLD, plan |
| D27 | Add retailer-agnostic onboarding preferences | requirements, HLD, LLD, plan |
| D28 | Reinstate the dashboard with a concrete origin requirement | requirements, HLD, LLD, plan |

---

## A. Feasibility — the risks the plan started without

### D1. Add a blocking Batch 0 feasibility spike

**Defect.** High-level design §11 Q6 names the Amazon printable-label path as the largest open
feasibility risk and says, in the document's own words, *"prototype this before writing anything
else in `extension/`."* The plan has no spike. Task 3.14 builds the PoC retailer adapter against
selectors nobody has looked at, and Task 2.8's fixture harness has no fixtures to harness.

**Decision.** A new **Batch 0** runs before Batch 1 with three go/no-go criteria, checked by hand
against a real logged-in retailer account:

1. A **printable USPS label** is reachable through the return flow without leaving the browser.
2. Each offered return method's **price is readable from the DOM** at the point of choice.
3. The printable label option is **free**.

If any criterion fails, the PoC retargets to a different retailer or a different return method
*before* thirteen tasks are written against an assumption that does not hold. The exit is a written
finding committed to the repository, not a verbal "it works".

**Why it is worth a batch.** The three criteria are exactly the assumptions FR-3.3.4, FR-3.3.5 and
FR-3.4.1 encode. Discovering criterion 3 is false after Batch 7 invalidates the entire pickup
branch — Tasks 4.3–4.5, 5.3, 6.4, 7.4, 7.5, 7.9, 7.10, 8.5 and 9.5.

### D2. Batch 0 exits with scrubbed, committed fixtures

**Decision.** The spike does not just answer yes/no; it captures the DOM subtrees it navigated,
scrubs them per low-level design §9 Q1, and commits them. Those fixtures are the real input to
Task 2.8 and Task 3.14.

**Why.** Task 2.8 currently builds a harness and a scrubbing README for fixtures that do not exist.
A spike that answers the question and throws away the evidence forces the same pages to be
navigated twice.

### D3. Batch 0 applies for USPS API access on day one

**Defect.** Tasks 4.3–4.5 build a USPS OAuth token provider and adapter. Nothing in the plan
obtains USPS API credentials, and that is a third-party approval with no stated turnaround.

**Decision.** Filing the access request is a Batch 0 task. It is the one item in the plan whose
latency is not ours to control, so it starts before anything that depends on it.

### D4. Batch 0 measures Bedrock parse and action latency

**Defect.** High-level design §11 Q9 records model latency as unmeasured, yet `BEDROCK_TIMEOUT_PARSE_MS`
= 9000 and `BEDROCK_TIMEOUT_ACTION_MS` = 4500 are already written into the configuration table, and
NFR-6.4 promises an action round trip under five seconds. Those are guesses with a requirement
resting on them.

**Decision.** Batch 0 times a cold and a warm parse invoke against a subtree captured by D2, and a
warm action invoke, and records the numbers. `server/app/bedrock.py` already implements the client,
per-call-site model resolution and `verify_config()`, so this costs a script, not a subsystem.

**Consequence.** If the measured action latency does not fit NFR-6.4's budget, that is an upstream
amendment (see D25), decided before Batch 5 builds a service against the number.

### D5. Batch 0 blocks only retailer-shaped work

**Decision.** Batch 0 gates Tasks 2.8, 3.13, 3.14, the driver flows that depend on them, and the
Batch 9 driving rows. It does **not** gate the server track, nor Tasks 1.2, 2.4, 2.5, 2.6 or 2.7.

**Why.** A blocking spike that idles both workspaces converts a risk reduction into a schedule loss.
The server's wire contract does not depend on which retailer wins.

---

## B. Scope — what the PoC is not

### D6. Cut FR-3.6.3 entirely

**Defect.** FR-3.6.3 (the dashboard messaging the extension via `externally_connectable`) requires a
dashboard hostname. High-level design §11 Q1 records that hostname as undecided and blocking
packaging — and Task 1.2, the *second task in the plan*, writes the manifest.

**Decision.** Cut the requirement from PoC scope rather than block Batch 1 on a hostname nobody
needs yet. Concretely: no `externally_connectable` key in the manifest, drop the external half of
Task 5.6, drop the Task 9.7 external-messaging row, and declare a **second acknowledged gap**
alongside FR-3.6.2 in the traceability table, allowlisted in the Task 10.2 sweep.

**Consequences.** HLD Q1 is resolved by removal — no hostname is needed for the PoC. `DASHBOARD_ORIGIN`
leaves the configuration surface. `client/` was already out of scope (low-level design §1); this
makes the extension side of that boundary consistent with it.

**Why cut rather than defer.** A requirement that is "deferred" still shows up as unimplemented in
every sweep. A requirement that is *declared out of scope with its gap recorded* is honest and
passes CI. The plan already has this pattern for FR-3.6.2.

### D7. Rewrite `infra/` for the Lambda architecture

**Defect.** Zero of the 79 tasks touch `infra/`. The directory still provisions a VPC, an internet
gateway, an EC2 instance and security groups with local state — the architecture the high-level
design superseded. NFR-6.6 and NFR-6.7 have traceability rows pointing at application tasks that
cannot satisfy them: no application task can create the alarm NFR-6.6 requires.

**Decision.** Delete the VPC/EC2/security-group scaffold. Provision instead: the Lambda function and
its execution role, a Function URL with single-origin CORS, SSM SecureString parameters for
secrets, an `InputTokenCount` CloudWatch alarm, an AWS Budget, and `reserved_concurrent_executions = 5`.

**Why the concurrency cap.** An `AuthType: NONE` Function URL whose only browser-side control is a
forgeable CORS header is one loop away from an unbounded Bedrock bill. The reservation is the
backstop the budget alarm cannot be, because an alarm notifies after the spend.

**Resolves** HLD §11 Q3.

### D8. Retire the "Legacy scaffold" section of `infra/AGENTS.md`

**Correction to an earlier finding.** `infra/AGENTS.md` was rewritten on 2026-08-26 and is *already*
accurate: it documents the Lambda target state in full, and quarantines the stale VPC/EC2 rules
(`allowed_cidr`, the two-availability-zone floor, `instance_type` replacement) inside a clearly
labelled **"Legacy scaffold"** section that ends with its own instruction — *"When the Lambda
resources land, delete this section along with the VPC, EC2, security group and the `vpc_cidr`,
`instance_type` and `allowed_cidr` variables."* The document is not misleading; it is waiting.

**Decision.** Task I.1 executes that instruction as part of its own definition of done. There is no
rewrite to do — the target state, the sizing table, the "no VPC" rationale, the `reserved_concurrent_executions`
reasoning and the Bedrock-invocation-logging ban are already written and are the specification I.1
implements against.

**Worth noting:** the document also independently confirms two decisions reached in this review —
that infra is *"not on the PoC critical path"* (D9), and that dev and prod are separate extension IDs
with *"one pinned key each"* (D20).

### D9. Infra runs as a track opening after Task 6.5

**Decision.** Not a trailing Batch 11. The infra track opens the moment Task 6.5 exports the Mangum
handler, and runs in parallel with Batches 7–10.

**Why.** Task 6.5 is the last thing infra actually needs — after it, there is a deployable artifact.
Running infra as a trailing batch would idle it through four batches for no dependency reason, and
would push the first real deployment to the end of the project, which is exactly where deployment
surprises are most expensive.

### D10. CI lands in Batch 1

**Defect.** Batch 10's commit checkpoint reads *"CI enforces what review would otherwise have to."*
There is no `.github/` directory and no task creates one. Three tasks write checks that never run.

**Decision.** `.github/workflows/ci.yml` is a **Batch 1** task, written generically to discover both
workspaces: server `make check`, extension build/test/lint, and `scripts/citation-sweep.sh` once it
exists.

**Why Batch 1 rather than Batch 10.** A gate added at the end tells you the last commit was clean.
A gate added at the start tells you which commit broke it. Batch 10's tasks then *add checks to an
existing pipeline* rather than inventing one.

---

## C. Schedule and verification honesty

### D11. Keep the batch barriers; restate the schedule

**Defect.** The plan claims a 19-task critical path and simultaneously mandates that *all* tasks in
a batch complete before the next batch starts. Under a hard barrier the makespan is the sum of the
per-batch poles, not the longest chain — roughly **1 + 2 + 5 + 7 + 2 + 5 + 4 + 5 + 2 + 1 = 34 slots**.
The published chain also omits Tasks 4.8 and 4.10–4.12, which sit on it.

**Decision.** Keep the barriers — they are what makes each commit checkpoint meaningful — and restate
the Critical Path and Parallelization sections in terms of both numbers, naming the barrier as the
reason for the gap, with a per-batch pole table so the arithmetic is checkable rather than asserted.

**The figures as applied.** The 34 above is the *pre-review* plan's cost. After the edits in this
record the numbers move in both directions and land at **~35 slots against a 20-task floor**: Batch 0
adds 2 and the manual acceptance gate (D23) adds 1 to Batch 8 and 1 to the floor; the storage split
(D19) takes Batch 4's pole from 7 down to 4; the deployment track (D9) adds 0, because it runs
concurrently with Batches 7–9 and gates nothing in them. The corrected speedup claim is **~2.6x**
under the barrier, against a 4.5x ceiling the barrier makes unreachable — not the ~4x the plan
advertised.

**Why keep the barriers.** They are the mechanism that keeps a multi-agent run from producing a
repository that is green nowhere. The fix is to stop advertising a number the barriers forbid.

### D12. Keep the doc-derived USPS mocks; add a sandbox reconciliation task

**Defect.** Tasks 4.3–4.5 build the USPS client against `respx` mocks written from documentation.
Nobody has seen a real USPS response. High-level design §11 Q11 asks what USPS does on a duplicate
booking and has no answer.

**Decision.** Keep 4.3–4.5 as they are — waiting on credentials would serialize the whole server
track behind a third party. Add a **"reconcile `UspsAdapter` against the sandbox"** task in the infra
track, which also answers Q11 empirically.

**Why this shape.** It separates "build against the documented contract" from "verify the contract is
real", and puts the second where credentials actually exist.

**Resolves** HLD §11 Q11.

### D13. Extension coverage gate: 95% line and branch over `src/`

**Defect.** The server has `fail_under = 95` with `branch = true`. The extension has no stated
coverage gate at all, and the plan's most intricate logic — the driver state machine — lives there.

**Decision.** 95% line and branch across `extension/src/`. `entrypoints/` is excluded by an
**explicit named list**, not a glob, and is covered by the Batch 9 integration rows instead.

**Why a named list.** A glob exclusion silently swallows anything later dropped into the directory.
A named list makes each exclusion a reviewable line.

### D14. Extend `.husky/pre-commit` to the extension

**Defect.** The hook is server-only. Every extension task in the plan can be committed without
running a test.

**Decision.** Extend the hook to the extension workspace in the same task as D13.

### D15. Add a repo-level `contracts/` directory

**Defect.** The plan's preamble states the wire types are *"a duplicated type by design"*. Nothing in
79 tasks verifies the two copies agree. Both suites can be green on mutually incompatible shapes —
the server's Pydantic model and the extension's TypeScript interface never meet in a test.

**Decision.** A new Batch 3 task creates `contracts/`: canonical request and response JSON for each
of the seven endpoints, plus one error body per reason code. Both suites assert their own
serialization against those files.

**Why golden files rather than codegen.** Codegen would couple the two workspaces' builds and destroy
the Batch 1–7 parallelism that is the plan's main asset. Golden JSON is a shared *artifact*, not a
shared *build step*: each side reads it independently, and a divergence fails a test on whichever
side drifted.

---

## D. Correctness of the plan's own text

### D16. Name the client-version header upstream

**Defect.** Task 3.8 builds a client version gate and Task 4.13 builds the client that must satisfy
it. Neither names the header. Requirements §4.2 specifies that an *absent* header raises
`client-too-old` — so two independently-written tasks that pick different spellings produce a
system where every request from the real client is rejected, and both suites pass.

**Decision.** Name it upstream in requirements §4.1 as **`X-Boomerang-Client-Version`**; cite it from
Tasks 3.8 and 4.13; include it in the D15 golden payloads.

### D17. Fix three configuration names; add a missing one

**Defect.** Tasks 2.5, 3.9 and 4.13 use `PAYLOAD_CEILING_BYTES` and `API_TIMEOUT_MS`. Neither string
appears anywhere in the requirements or the low-level design. The real names are `MAX_INGEST_BYTES`
and `API_REQUEST_TIMEOUT_MS`. `API_RETRY_BUDGET_MS` is specified upstream and absent from the plan
entirely, so the retry budget it governs would not have been built.

**Decision.** Correct both names and add the missing parameter to Task 2.5's constant set and
Task 4.13's client.

### D18. Extend the Task 10.2 sweep to configuration-parameter names

**Decision.** The citation sweep checks `FR-`/`NFR-` identifiers. Extend it to configuration-parameter
names drawn from requirements §5.1/§5.2.

**Why.** D17 is a class of defect, not an instance. An identifier sweep catches a missing requirement
citation but not an invented constant, and the invented constant is the one that compiles.

### D19. Split the storage barrel

**Defect.** Batch 4's seven-task storage chain (4.6 → 4.12) is fully serialized. The plan justifies
this as protecting *"one state machine, one serialising queue"* — but the actual serializing
constraint is that all seven tasks edit `src/storage/index.ts`, a barrel file. That is a scheduling
artifact wearing an invariant's clothes.

**Decision.** One file per repository — `OrderRepository`, `ReturnRepository`, `PickupRepository`,
`AddressRepository`/`SessionStore`. `src/storage/index.ts` is written **once**, in Task 4.6, listing
the exports up front. `StorageCoordinator.transact` stays whole in 4.7 — *that* is a real invariant.

**Effect.** Batch 4's pole drops from 7 slots to ~4, which is the single largest schedule improvement
available in the plan.

---

## E. Gaps found in the tail

### D20. Generate the pinned extension keypairs in Batch 1

**Defect.** No task in 3,223 lines generates the extension keypair or writes the manifest `key`.
FR-3.7.1 requires it. Requirements line 761 explains why: without a pinned key, Chrome derives the
extension ID from the load path, so the ID differs between every machine. NFR-6.5 allowlists exactly
one `chrome-extension://` origin on the Function URL — a literal string that must be known at
`terraform apply` time. Task 10.1 scans the production bundle for a *dev* key, implying two keypairs
that nothing creates.

**Decision.** A Batch 1 task alongside 1.2 generates the dev and prod keypairs. The dev public key
goes in `wxt.config.ts`; private keys go to SSM at `/boomerang/release/<env>/extension-key` per HLD
§8.4, with the prod key additionally held offline. Neither private key enters the repository.

**Why Batch 1 and not the infra track.** The derived origin is an *input* to the CORS policy — it has
to exist before the thing that allowlists it. Batch 1 also makes the ID stable for every unpacked
load from that point on.

**Both keys are required, not speculative.** `infra/AGENTS.md` specifies two environments sharing
nothing, with *"separate CORS origins (they are separate extension IDs — one pinned key each)"*. The
prod key is therefore mandated by the deployment topology independently of whether Boomerang ever
self-packages a CRX, and Task 10.1's dev-key scan is what keeps the two from being confused.

### D21. Split `MockUspsAdapter` into a scripted double and a runtime stub

**Defect.** Task 4.5 designs `MockUspsAdapter` as a strict test double: `push(method, outcome)` queues
per-method outcomes, an **unqueued call is an error** rather than a happy path, and `assert_drained()`
fails on leftovers. But requirements §5.1 makes `CARRIER_ADAPTER=mock` the *runtime* default until
USPS access lands, and D23's acceptance test books against it. A push/pop double cannot serve a
running deployment — the first real request pops an empty queue and raises.

**Decision.** Rename Task 4.5's class to **`ScriptedUspsAdapter`** — same behaviour, honest name,
tests only. Add a task building **`MockCarrierAdapter`** for `CARRIER_ADAPTER=mock`: deterministic
confirmation numbers, a next-available scheduled date, eligible everywhere **except one designated
unserviceable postcode**.

**Why the unserviceable postcode.** FR-3.4.2's graceful second answer is the hardest copy in the
product to get right and the easiest to never see. A designated failing postcode makes it
demonstrable by hand.

**Rejected alternative.** Giving one class a permissive default mode reintroduces exactly the silent
happy-path behaviour Task 4.5 step 3 exists to forbid, one constructor argument away from a test.

### D22. Label mock-backed bookings as simulated

**Defect.** Under `CARRIER_ADAPTER=mock` the extension stores a fabricated confirmation number, writes
an NFR-6.2 `ConsentStamp` for a pickup that was never booked, and the popup renders it as a
confirmed USPS collection. Requirements §5.1 names this failure — *"a production deployment that
silently degrades to a mock returns fabricated confirmation numbers to real users"* — but only
guards production, and the demo runs on the mock by design.

**Decision.** `MockCarrierAdapter` returns confirmation numbers carrying a fixed recognisable prefix.
The popup renders any booking carrying that prefix with a **"simulated — no carrier was contacted"**
label, asserted in a test.

**Why.** The product's own governing rule is that a derived thing is never presented as authoritative.
The one screen showing a confirmation number is the screen most likely to be demonstrated to other
people, and it would be the only screen making a false claim.

---

## F. Execution

### D23. Manual acceptance task after Batch 8

**Defect.** Nothing in the plan runs the built extension in a real browser. Batch 9 drives an
assembled extension under `vitest` against a fake `chrome`; Task 10.1 inspects a bundle statically.
The fake browser is a model of Chrome written by the same people writing the code it validates.

**Decision.** A manual acceptance task after Batch 8, with a written step list and an expected
observation at each step: load `.output/chrome-mv3` unpacked, scan a real order page, drive to the
label choice, confirm, affirm print, book against the mock carrier, open the calendar template,
cancel.

**Why written steps rather than "try it".** An unwritten manual test is not repeatable and its
failure is not reportable. The step list is also the demo script.

### D24. Two agents; per-task approval on the driver and storage spines

**Decision.** One agent on the extension spine, one on the server, both executing through
`implement-task-code`. **Per-task human approval** on driver and storage tasks; **batch-level
approval** on leaf modules.

**Why the split.** The driver state machine and the storage coordinator are where a plausible-looking
wrong implementation is most expensive to discover late — they are the plan's serial spine, so a
defect there invalidates everything downstream. Leaf modules are individually cheap to re-do.

### D25. Amend upstream documents rather than working around them

**Decision.** Where this review found the requirements or the high-level design wrong or incomplete
(D6, D16, D22, and D4 if measurement contradicts NFR-6.4), amend those documents and have the plan
cite the amended text.

**Precedent.** Low-level design §10 already records five upstream amendments it made during review.
The repository's established position is that upstream wins — *and that upstream can be wrong*, in
which case it is corrected rather than routed around. A plan that silently contradicts its
requirements produces a system nobody can audit against either document.

### D26. Generalize carrier pickup to configured third-party carriers

**Defect.** The Amazon return-flow spike found that USPS is not offered consistently: the available
return methods depend on the retailer, item, account, and return context. Naming USPS as the only
pickup carrier would make the implementation specific to one retailer and would reject otherwise
valid carrier-backed return paths.

**Decision.** Use the generic concept **third-party pickup** in the requirements and user-facing
flow. The server supports a configured set of pickup carriers, and `label_carrier` must belong to
that set before eligibility or scheduling can occur. The implementation may support USPS, UPS,
and additional carriers independently; it must not assume one carrier is always available. Amazon's
own door-pickup option is a retailer-provided option and is handled by the retailer adapter unless
an explicit supported integration is added later.

### D27. Add retailer-agnostic onboarding preferences

**Defect.** Return-method choices and form requirements differ between retailers and even between
items or accounts. Without preferences captured before the driver starts, the extension cannot
make a useful first recommendation or know whether a printed label is practical for the user.

**Decision.** On first interaction, offer a skippable onboarding form that stores a return address,
the user's preferred return mode (self-service drop-off or home pickup), and whether the user has
access to a printer. Store these values in a client-only `PREFERENCES` singleton in
`chrome.storage.local`; do not create a server-side user database or account. Preferences guide
which available option is highlighted, but never silently select an option or override the retailer's
actual choices. When the user has no printer, prefer a no-printer-required option such as a QR-code
drop-off when one is available.

### D28. Reinstate the dashboard with a concrete origin requirement

**Defect.** The dashboard was previously cut because its production origin was undecided, but the
product now requires a main dashboard showing returnable value, savings, and ranked return windows.

**Decision.** Reinstate the dashboard requirement and its `externally_connectable` integration.
`DASHBOARD_ORIGIN` defaults to `http://localhost:3000` for development and must be set to a concrete
production origin before a release build; an unset production value fails the build. The dashboard
reads an enumerated summary from the extension: currently returnable value, saved value from
successful returns, and each open item's days remaining in urgency order. These figures are derived
at render time from stored order and return entities, not persisted as running totals. The dashboard
does not receive onboarding preferences.

---

## Upstream amendments required

| Document | Section | Amendment | Decision |
|----------|---------|-----------|----------|
| `boomerang-plan.md` | Header, preamble, Batch 0–10, deployment track, all tail sections | Applied 2026-08-27 | D1–D25 |
| `boomerang-requirements.md` | Overview | Revision banner; `Dn` disambiguated from the `docs/ARCHITECTURE.md` series | D25 |
| `boomerang-requirements.md` | §4.1 | Name the client-version header `X-Boomerang-Client-Version`, normatively, including the rule that a differently-worded header is treated as absent | D16 |
| `boomerang-requirements.md` | FR-3.4.5b | **New requirement:** a booking made without contacting a carrier SHALL disclose itself, detected by confirmation-number prefix rather than by build environment | D22 |
| `boomerang-requirements.md` | FR-3.6.3 | Mark out of PoC scope with rationale | D6 |
| `boomerang-requirements.md` | §5.1/§5.2 | `MOCK_CONFIRMATION_PREFIX` added to the server table; `DASHBOARD_ORIGIN` struck from the extension table with a restore note | D6, D22 |
| `boomerang-high-level-design.md` | §11 Q1 | Resolved by removal — no dashboard hostname needed | D6 |
| `boomerang-high-level-design.md` | §11 preamble | Struck-through vs. **assigned** distinction stated; `Dn` disambiguated | D25 |
| `boomerang-high-level-design.md` | §11 Q3 | Resolved — `infra/` becomes the Lambda topology; the claim that `infra/AGENTS.md` is contradictory is retracted | D7, D8 |
| `boomerang-high-level-design.md` | §11 Q4 | Answered question now also assigned to Task 1.4 | D20 |
| `boomerang-high-level-design.md` | §11 Q5 | Assigned — Task 0.1's second go/no-go criterion | D1 |
| `boomerang-high-level-design.md` | §11 Q8 | Moot for the PoC — no `externally_connectable` to review | D6 |
| `boomerang-high-level-design.md` | §11 Q6 | Resolved — Batch 0 spike, with go/no-go criteria | D1 |
| `boomerang-high-level-design.md` | §11 Q9 | Resolved — Batch 0 measures it | D4 |
| `boomerang-high-level-design.md` | §11 Q11 | Assigned — Task I.3 answers it against the sandbox | D12 |
| `boomerang-requirements.md` | FR-3.3.5, FR-3.4 | Generalize USPS-specific pickup rules to configured third-party pickup carriers | D26 |
| `boomerang-requirements.md` | §3.0 | Add retailer-agnostic onboarding preferences and client-only storage | D27 |
| `boomerang-requirements.md` | FR-3.6.3 | Reinstate the dashboard with render-time return and savings summaries | D28 |
| `boomerang-high-level-design.md` | §4.2, §5.1, §6.7 | Add `PREFERENCES`, onboarding, and dashboard flows | D27, D28 |
| `boomerang-low-level-design.md` | Storage, dashboard messaging, configuration | Add preferences storage and dashboard contract | D27, D28 |

**D1–D25 were applied on 2026-08-27; D26–D28 were applied on 2026-09-01.** Questions 2, 7 and 10 in §11 remain open and
unassigned, and are marked as such rather than quietly dropped: the unauthenticated-endpoint
availability gap, the terms-of-service assessment, and the region choice. None of them blocks Batch
0.

---

## Defects found and not separately decided

Recorded so the traceability edits below are not mistaken for cosmetic:

- NFR-6.6 and NFR-6.7 traceability rows point at application tasks that cannot satisfy them. Fixed by
  D7's infra tasks.
- The published critical path omits Tasks 4.8 and 4.10–4.12, which lie on it. Fixed by D11.
- Task 10.1 scans for a dev extension key that, before D20, nothing created.
