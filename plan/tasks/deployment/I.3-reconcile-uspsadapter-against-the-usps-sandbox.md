---
id: "I.3"
batch: "deployment"
batch_dir: "deployment"
order: 64
track: null
track_heading: null
track_scope: null
title: "Reconcile `UspsAdapter` against the USPS sandbox"
kind: "implementation"
package: "server/app/carriers/usps"
package_raw: "`server/app/carriers/usps`"
prerequisites: ["I.1", "0.2", "4.4"]
prerequisites_raw: "Task I.1, Task 0.2 (credentials granted), Task 4.4"
conflicts_with: []
conflicts_with_raw: "None"
parallel_with: []
parallel_with_raw: "All of Batches 7–10"
requirements_covered: ["FR-3.4.1", "FR-3.4.5", "FR-3.4.6", "FR-3.4.8"]
requirements_covered_raw: "FR-3.4.1, FR-3.4.5, FR-3.4.6, FR-3.4.8"
sections_covered: []
status: "not_started"
---
### Task I.3: Reconcile `UspsAdapter` against the USPS sandbox

**Prerequisites:** Task I.1, Task 0.2 (credentials granted), Task 4.4
**Conflicts with:** None
**Parallel with:** All of Batches 7–10
**Package:** `server/app/carriers/usps`

**Objective:** Tasks 4.3–4.5 build the USPS client against `respx` mocks written from documentation.
Nobody has seen a real USPS response. This task is where "built against the documented contract"
becomes "verified the contract is real". High-level design §11 Q11 — what USPS does on a duplicate
booking — has no answer, and this is the task that answers it. Decision D12.

**If credentials have not arrived, this task does not run.** It is on no critical path, blocks
nothing, and its absence is a known risk rather than a schedule failure. Say so in the status
tracker rather than quietly marking it done.

**Instructions:**
1. Against the USPS sandbox, exercise each method `UspsAdapter` implements: token acquisition,
   eligibility, schedule, refresh, cancel.
2. **Diff every real response against the `respx` fixture** that stands in for it. Field names,
   nesting, date formats, and error bodies are the four places documentation and reality routinely
   diverge.
3. Update the fixtures to the observed shapes and re-run the Batch 4 and Batch 7 suites. A fixture
   change that breaks a test is this task finding a real defect; fix the adapter, not the assertion.
4. **Answer HLD §11 Q11 empirically:** book a pickup, then book an identical one. Record what USPS
   does — a second confirmation, an error, a silent no-op — in `docs/spikes/usps-sandbox.md`, and
   raise it as an upstream amendment if FR-3.4.5's behaviour depends on an answer the design
   assumed differently.
5. Record token TTL and any rate limit observed; both are inputs the token provider guessed at.

**Verification:**
- `docs/spikes/usps-sandbox.md` records one observed response per method plus the duplicate-booking
  answer.
- `cd server && make check` passes with the reconciled fixtures.

**Requirements covered:** FR-3.4.1, FR-3.4.5, FR-3.4.6, FR-3.4.8
