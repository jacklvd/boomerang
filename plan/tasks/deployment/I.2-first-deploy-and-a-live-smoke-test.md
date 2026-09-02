---
id: "I.2"
batch: "deployment"
batch_dir: "deployment"
order: 65
track: null
track_heading: null
track_scope: null
title: "First deploy and a live smoke test"
kind: "integration"
package: "infra/"
package_raw: "`infra/`"
prerequisites: ["I.1"]
prerequisites_raw: "Task I.1"
conflicts_with: []
conflicts_with_raw: "None"
parallel_with: []
parallel_with_raw: "All of Batches 7–10"
requirements_covered: ["NFR-6.4", "NFR-6.5", "NFR-6.6"]
requirements_covered_raw: "NFR-6.4, NFR-6.5, NFR-6.6"
sections_covered: []
status: "not_started"
---
### Task I.2: First deploy and a live smoke test

**Prerequisites:** Task I.1
**Conflicts with:** None
**Parallel with:** All of Batches 7–10
**Package:** `infra/`

**Objective:** Prove the deployed thing serves the same seven endpoints the test suite serves, from
a real browser origin, before Batch 10 starts asserting things about a bundle nobody has run against
a real server.

**Instructions:**
1. Apply to `dev`. State is local today — `infra/AGENTS.md` warns that a second person applying will
   corrupt it, so either move to the S3 backend it sketches or make it explicit that exactly one
   person applies during the PoC. This apply is where NFR-6.6's topology stops being a
   `terraform plan` and becomes a running deployment — low-level design §8.4 names Task I.1
   and this task as that requirement's two owners.
2. Write the USPS credentials into SSM by hand. If Task 0.2's access has not arrived, deploy with
   `CARRIER_ADAPTER=mock` and confirm the startup log emits the Task 6.5 warning.
3. Smoke test from a real loaded extension, not `curl`: `/health` responds **to a request carrying
   `X-Boomerang-Client-Version`** — the gate covers `/health` too (requirements §4.1), so a bare
   probe returns 426 and that is the correct behaviour, not a deployment failure; one ingest round
   trip succeeds; and a request from **any other origin is rejected by CORS**. The last one is the
   assertion that matters — it is the only browser-side control on an unauthenticated endpoint.
4. Record the deployed Function URL and the measured cold-start time in `docs/spikes/deploy.md`.
   Compare the cold start against NFR-6.4's budget and against Task 0.3's measurement; a cold start
   that breaks the budget is an upstream amendment (decision D25), not a footnote.

**Verification:**
- `/health` returns 200 over the Function URL **when the request carries a supported
  `X-Boomerang-Client-Version`**, and 426 `client-too-old` when it carries none (corrected
  2026-08-28, seventh review, CONF-2 — the bare-probe form of this check could not pass against a
  correctly gated deployment).
- A request with a spoofed `Origin` header is refused.
- `docs/spikes/deploy.md` records the URL and the cold-start figure.

**Requirements covered:** NFR-6.4, NFR-6.5, NFR-6.6
