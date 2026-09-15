# Boomerang — Extension Authentication: the Open Decisions, Closed

> **STATUS: RULING — 2026-09-13. Every question is closed.** The one that was outstanding — the
> revocation scope — was answered by the user the same day: **account-wide, registered as `MIG-19`.**
>
> The pairing-lifecycle implementation ticket cannot be written honestly against the accepted
> authentication design as it stands. Four defects surfaced during implementation, and six of the
> seven product questions in
> [`boomerang-extension-auth-proposal.md`](boomerang-extension-auth-proposal.md) section 13 are still
> open. An implementing agent facing those gaps will invent answers silently. This document exists so
> that it does not have to.
>
> **What it is downstream of, and treats as normative:**
> [`boomerang-extension-auth-proposal.md`](boomerang-extension-auth-proposal.md) (ACCEPTED — the
> mechanism), [`boomerang-api-contract.md`](boomerang-api-contract.md) (the frozen wire surface),
> [`boomerang-pairing-persistence.md`](boomerang-pairing-persistence.md) (PROPOSAL — the tables), and
> [`boomerang-account-scoping.md`](boomerang-account-scoping.md) (ACCEPTED).
>
> **What it does not do.** It does not reopen the accepted architecture. Server-brokered browser
> linking with proof-of-key redemption, the bearer-on-extension/cookie-on-dashboard split, the
> account-scoping pattern and the frozen route list all stand exactly as accepted. Where a ruling
> below finds that an accepted document promises something no implementation can deliver, it says so
> and names the smallest edit, rather than proposing a different design.
>
> **The bias, stated openly.** The project is under deadline and the user has twice chosen to proceed
> with the design as it stands rather than revise it. Every ruling here is therefore the smallest
> reversible decision that unblocks implementation, and where the honest answer is "this is not
> ideal, we ship it and record the debt," that is what is written.
>
> The decisions are registered in [`../plan/boomerang-decisions.md`](../plan/boomerang-decisions.md)
> as `MIG-17`, `MIG-18`, `MIG-19` and `PROV-05` through `PROV-08`.

---

## 1. What this document decides, and on what authority

Two kinds of question arrive together in the open authentication surface and they must be separated
before either can be answered.

The first kind is an engineering question wearing a product question's clothes. "Should there be a
decline route?" looks like a product call about user agency; it is settled once you notice that the
only actor who can approve a pairing is the signed-in user themselves, which makes an undeclined
pairing harmless. Questions of this kind are closed here, on engineering grounds, and recorded as
provisional where a later product decision could reasonably move them.

The second kind is genuinely irreversible, genuinely user-visible, or a product-strategy call an
engineer must not make silently. Exactly one question in the whole open surface is of that kind, and
it is in section 4. Everything else is closed below.

The test applied throughout is reversibility. A decision is safe to take here when reversing it later
costs a configuration change, an additive migration, or a copy edit — and unsafe when reversing it
costs a data migration, a user-visible behavioural break, or the un-shipping of something already
placed in users' browsers and their privacy policy.

---

## 2. The four defects, ruled

### 2.1 The rulings

| # | Defect | Ruling | Blocks implementation? | Consequence |
|---|---|---|---|---|
| 1 | There is no decline route; the approval copy promises one and the `rejected` pairing status is unreachable | **The copy and the status are wrong, not the route list.** No decline route in v1. `rejected` is not added to the pairing status enum. The approval page says *close this page*, not *decline* | **No**, once applied. It blocks the pairing schema only until answered, and the answer is cheap | Pairing status is a three-value enum: `pending`, `approved`, `redeemed`. The approval-copy bullet in the accepted proposal's section 6 needs one word changed |
| 2 | The `account_deleted` 401 discriminator cannot be returned once the account row is gone | **The server returns `not_linked`, and no credential tombstone is built.** The extension selects its cleanup branch on whether *it presented a credential*, which it knows locally and the server cannot tell it | **Yes** — the implementer must know whether to build `revoked_credentials`. This ruling unblocks it: do not build it | Nothing survives account deletion. `account_deleted` stays in the published enum as reserved and unreachable in v1. The contract's section 12 sentence promising it is wrong as written and must be amended |
| 3 | The same-browser correlator fails open silently in every ordinary case | **No correlator ships in v1** — no correlator cookie, no column on either record. The extension-grant revocation scope on dashboard sign-out is a single predicate behind one named seam, defaulting to account-wide | **No.** The seam made the pairing lifecycle safe to build before the question was answered | This changed the *letter* of the DECIDED section 13 item 1 while satisfying its stated intent strictly, which is why it was put to the user in section 4 rather than ruled here. The user answered account-wide, registered as `MIG-19`, and the correlator this ruling declines is now declined permanently |
| 4 | The abandonment reset cannot reach an item stranded by sign-out, disconnect or deletion | **V1 accepts the stranding.** The residual stays where it already lives, in `ARCH-B1`. One mitigation ships, and it is pure dashboard UI over a field the frozen contract already returns | **No** | The dashboard's sign-out confirmation warns when `in_progress_count` is non-zero. No new route, no contract change, no server behaviour. Under the account-wide default the residual is wider, and that widening is part of the user's trade in section 4 |

### 2.2 Defect 1 — the decline route

The approval page is required by the accepted proposal's section 6 to tell the user to decline if they
did not just install the extension in this browser, and the accepted route list in the same document's
section 12 contains no route to decline with. One of the two is wrong.

It is the copy, and the reason is that a decline buys almost nothing. A pairing can only be approved by
an authenticated dashboard principal — that is, by the user themselves, on the approval page the
extension opened. An attacker who has started a pairing on their own machine cannot approve it. So a
pairing the user looks at and walks away from is not a hanging risk: it stays `pending`, it is
approvable by nobody but that same user, and it dies within a few minutes. The entire behavioural
difference between a decline route and closing the tab is that a user who changes their mind inside
that window can still approve. That is not a security property worth a route, a status value, a
contract change and a sign-off cycle under deadline.

What the copy should say instead is what is actually true: *if you didn't just install Boomerang in
this browser, close this page — this request expires on its own in a few minutes and nothing is
linked.* That is a stronger instruction than "decline," because it is the one that works whether or not
the page is genuine.

The status value goes with it. An unreachable value in a native PostgreSQL enum, referenced by a check
constraint, is dead schema that the first migration has to carry. Adding it later, if a decline route is
ever wanted, is purely additive and touches nothing on the wire — pairing status never appears in a
response, because the pairing routes collapse every failure into one indistinguishable answer.

### 2.3 Defect 2 — the `account_deleted` discriminator

The contract requires that a call from an extension after its account is deleted return `401` with
`details.auth_reason` of `account_deleted`, and it distinguishes that behaviour from `not_linked`:
`account_deleted` tells the extension to clear its credential, its local workflow records **and its
checkpoints**, because those now reference identifiers that no longer exist. The same contract requires
that account deletion remove the account's records synchronously before the `204`. Once that has
happened there is nothing left to resolve the presented credential against, and the only honest answer
is `not_linked` — under which the extension clears nothing and offers to link into an account that is
gone.

The persistence proposal's answer is a credential tombstone: a table with no account column, holding an
unsalted credential digest, a reason and two timestamps, that outlives the account so the discriminator
can still be returned.

**The tombstone is not the smallest fix, and it is the wrong direction under this project's own
rules.** It creates a durable artifact that survives a deletion the product tells the user is a
deletion; it must be disclosed in the privacy copy; it needs a lifetime from the open retention gate; it
joins the unscoped-rows registry; and it exists solely to carry a four-value enum across a boundary.

The smaller fix is available because **the extension already knows the thing the server has lost.** The
contract's `not_linked` row conflates two situations that are not alike: *no credential was presented*
(a fresh install, offer linking) and *a credential was presented and resolves to nothing* (whatever this
browser was linked to is gone). Only the server cannot tell them apart after deletion. The client can
always tell them apart, trivially, by looking at its own storage.

**Ruling.** The server returns `not_linked` in both cases and stores nothing to do better. The
extension's required behaviour on `not_linked` splits on a fact it holds locally:

- it presented no credential — offer the linking flow, clear nothing, do not retry;
- it presented a credential — this is terminal. Clear the credential, the local workflow records
  **and the checkpoints**, render as not linked, do not retry.

This preserves the accepted design's actual promise, which was always about *what the extension does*
— section 10 of the accepted proposal says it "clears its credential *and* its local workflow records
and checkpoints." That behaviour is unchanged. What changes is only the signal that triggers it, and
the signal the contract chose is one the server cannot send.

What is genuinely lost is message precision. The extension can no longer distinguish "your account was
deleted" from "this browser's link expired and was reaped" when composing its empty state. *This browser
is no longer linked to Boomerang* is truthful in both cases, and it is the message a user needs either
way.

Reversibility: adding the tombstone later is additive. It writes rows only for deletions after it
ships, changes no existing data, and changes only which discriminator a small set of calls receives.
Nothing has to migrate.

### 2.4 Defect 3 — the correlator and the revocation scope

The persistence proposal's section 8.2 is honest and its conclusion is unavoidable: every ordinary
failure of a correlator is a **silent fail-open**. Cookie absent, cookie cleared, signing out from
another browser, incognito — in each case nothing is revoked, the user believes they are signed out, and
the extension in that browser keeps working. The user's stated mental model was "sign out means signed
out." The mechanism cannot deliver it, in exactly the direction the user cares about.

Account-wide revocation — sign-out revokes every extension grant on the account — needs no correlator,
no new client-side identifier, no new columns, no new cookie, and has no silent case.

**Three things follow, and only the first two are mine to decide.**

**First, no correlator ships in v1, whatever the scope turns out to be.** This is an engineering call
and it is safe, because the correlator is the *irreversible* direction. It requires minting a durable,
server-recorded, cross-session browser identifier and putting it in the privacy copy. Shipping that
provisionally and removing it later means having created and disclosed a per-browser identifier that was
never needed. Shipping account-wide first and adding the correlator afterwards is a clean additive
change: two nullable columns, one cookie, one predicate. Under a deadline and a smallest-reversible-step
bias, the direction of travel is not in question even though the destination is.

**Second, the difference between the two answers is one `WHERE` clause, and it gets a named seam.** The
pairing lifecycle does not need the answer to be built. Revocation on sign-out is one service-layer
function over `auth_grants`; account-wide is that function without a correlator predicate and
same-browser is that function with one. The implementer builds the function, the seam, and the tests,
and the user's answer later changes the predicate and adds two columns.

**Third — and this was not mine to decide — shipping account-wide as anything other than a placeholder
changed the letter of a DECIDED item.** Section 13 item 1 was decided by the user on 2026-09-13 and
read "signing out of the dashboard revokes the extension's grant in the same browser." Account-wide
revocation satisfies that decision's *stated intent* strictly and over-satisfies its *scope clause*.
That over-satisfaction is user-visible: signing out on a work laptop unlinks the home browser, and the
user re-does the one-time approval there. A user did not ask for that, an engineer could not decide it
silently, and it was put to the user in section 4.

**Ruling: build with no correlator, and default the seam to account-wide.** The scope question in
section 4 is closed: the user answered account-wide, later the same day, registered as `MIG-19`. The
seam's default is therefore the decision itself rather than an interim placeholder, and the correlator
this ruling declines to ship is declined permanently, not merely deferred.

### 2.5 Defect 4 — sign-out stranding

The `ARCH-B1` sub-decision closed the stranded-summary hole with a validated extension-published reset
to `not_started`. The reset requires a live extension grant. Sign-out, disconnect and account deletion
are precisely the events that remove one, and a re-linked extension has already discarded the local
workflow records that would tell it which items were stranded. An item stranded that way stays stranded:
the dashboard derives a continue-return action on it forever and `in_progress_count` is permanently
wrong by one.

**V1 accepts this.** The alternatives all cost more than the defect. A dashboard-initiated reset needs a
new wire route and breaks the caller-enforcement rule that only an extension may write a summary — a rule
that exists because only the extension can observe that a run is over. A server-side reset at revocation
time is a server-initiated write to user return data on an inference, which is the pattern the
architecture forbids outright. Neither is a thing to invent under deadline against an item count that is
off by one.

What ships instead costs nothing and is not a contract change: **the dashboard's sign-out confirmation
warns when the account has in-progress returns.** The dashboard already receives `in_progress_count` from
the frozen dashboard aggregate. "You have 2 returns in progress. Signing out will end them — you'll need
to start those returns again." That converts a silent data defect into a stated consequence the user
chooses, which is the most that can be done without new architecture.

Under the account-wide default from defect 3 this residual is wider — any sign-out strands in-progress
runs in *every* linked browser, not one. That is a genuine cost of the account-wide answer and it belongs
to the user's trade in section 4, where it is stated.

---

## 3. Section 13 items 2 through 7

### 3.1 The rulings and their classification

| Item | Recommendation | Class | Consequence if adopted |
|---|---|---|---|
| **2.** How many browsers may one account link at once? | **Unlimited in v1.** No cap, no uniqueness constraint | **(a)** provisional engineering default | `auth_grants` gets no uniqueness constraint beyond the one it has; approval writes unconditionally; the linked-browsers list renders an unbounded set. A cap later is a counting predicate in the approval transaction plus a configuration value |
| **3.** Must a user visit the dashboard before the extension can do anything? | **Yes.** Linking is a precondition for every extension capability | **(a)** — and effectively already decided by accepting Option B | The popup's pre-link state is the explainer and the link offer, and nothing else. No page read, no scan, no queueing or buffering of page content against a future credential. This is the accepted proposal's section 10 restated as an enforceable rule |
| **4.** How long may a linked browser sit idle before re-linking? | **Defer the number to `ARCH-B4`; implement the shape now.** Every grant carries both an idle limit and an absolute limit, evaluated at read time | **(a)** | `idle_expires_at` and `absolute_expires_at` are in every resolution predicate. Both values come from configuration with no default in code or schema. The implementer invents no number |
| **5.** Should the approval screen identify the browser being linked? | **Show the closed-vocabulary browser label and the request time. Show no location, and derive nothing from an IP address** | **(a)** | The approval page renders two facts that are already being stored for the linked-browsers list, so nothing new is collected about the user and the privacy copy needs no new claim. Location would be a new collection, a new dependency, and the one item on that list that is genuinely a product call |
| **6.** Is the browser-identity permission acceptable in the manifest in principle? | **No, not in v1, and not without reopening `ARCH-B9`.** Recorded as a forward constraint, not as a firm never | **(a)** | The manifest stays `activeTab`, `scripting`, `storage`. A guardrail line says the extension has no Google relationship and gains no identity permission. Any future need reopens the closed gate rather than arriving inside an implementation ticket |
| **7.** Should automatic linking be layered on once the bridge gate closes? | **Yes, as an intentional follow-on against `ARCH-B6`.** Not v1 scope | **(a)** | No v1 consequence at all, except that the pairing records must not be built as though manual approval is the only path forever — and they are not, because automatic linking would reuse the same records |

Every item is **(a)**. That is the finding, and it is worth stating rather than leaving as an absence:
the open product surface in section 13 contained one question that genuinely needed the user, and it
was item 1's scope, which item 1 appeared to have closed. That question is now closed too; see
section 4.

### 3.2 Where the reasoning is not obvious

**Item 2 — why unlimited, when a cap is "the safer default."** A cap is safer only once you answer what
happens at the cap, and both answers are bad under deadline. Refusing the approval strands a user who
legitimately uses three machines with an error they cannot clear without finding the linked-browsers
list. Evicting the oldest grant silently unlinks a browser the user did not touch, which is a
destructive, user-visible act taken by a counter. The control that actually matters against a mistaken
or phished approval is already in the design and is not a cap: every grant appears in the
linked-browsers list with its creation and last-use time and can be revoked from there. The honest cost
of unlimited is that one extra row is less conspicuous in a long list than in a list of three. That is
real and it is smaller than the failure modes of a cap chosen without product input. Note that the cap
and the expiry semantics have to be decided together if a cap is ever chosen, because counting *live*
grants means evaluating both expiries.

**Item 5 — the label does not detect phishing, and should not be sold as though it does.** The browser
label originates with the extension, which means in the exact phishing scenario the design is defending
against, the attacker declares it. An attacker will declare something plausible. The label's value is
not at approval time; it is afterwards, in the linked-browsers list, where a user auditing their account
can see that a browser they do not recognise is linked. The mechanism that defends the approval moment
is the short-code comparison and the absence of any manual code-entry path. Showing the label and the
time on the approval page is worth doing because it is free and it is orienting, not because it is a
control.

**Item 6 — why "no in v1" is not a product call.** Recording a firm never would be a product call,
because it forecloses options. Recording "not in v1, and reopening the closed gate is the way to change
it" forecloses nothing and merely writes down what accepting Option B already implied. The reason it
must be written down is the failure mode: the first implementer who finds the linking step annoying will
reach for the browser-identity permission, and the manifest posture is the extension's entire store-review
strategy. An unrecorded "we didn't need it" becomes a "nothing said we couldn't."

---

## 4. The revocation scope — put to the user, and answered

> **CLOSED 2026-09-13. The answer is account-wide, registered as `MIG-19`.** The question and the
> argument that produced it are kept below exactly as they were put to the user, because the reasoning
> is what makes the answer reviewable; the resolution is recorded at the end of this section.

One question was put to the user. It was the revocation scope, and it was a question because answering
it either way changes behaviour the user can see, and because one of the two answers changes the letter
of a decision the user already made.

> **When you sign out of the Boomerang dashboard, we can unlink the Boomerang extension in *that
> browser only*, or in *every browser you've linked*. We need you to pick, because we can't build both.**
>
> **That browser only** is what you asked for, and it is the more precise-sounding answer. The problem
> is that we can't actually guarantee it. Recognising "the same browser" later means we set a long-lived
> marker in your browser and look for it when you sign out. In several completely ordinary situations
> that marker isn't there — you cleared your cookies, you're in a private window, you're signing out from
> a different computer, it's a fresh profile. In every one of those cases nothing happens: you sign out,
> you believe you're signed out, and the extension in that browser keeps working exactly as before. It
> fails quietly, and it fails in the direction you told us you didn't want.
>
> It also means we start keeping a long-lived identifier for each browser you use, which is a new thing
> we'd be storing about you and would have to go into the privacy policy.
>
> **Every browser** has no quiet failure. Signing out means every browser is unlinked, every time. The
> cost is that it's blunter than you asked for: if you sign out on your work laptop, the extension on
> your home computer is unlinked too, and the next time you use it there you re-do the one-time approval
> — open the dashboard, check the code matches, approve. Perhaps ten seconds, but you didn't ask for it.
>
> **One more cost, which applies either way but is wider under "every browser."** Unlinking a browser
> ends any return that was half-finished in it. Those returns can't be resumed; they go back to "not
> started" and you begin again. Under "that browser only" that's limited to the browser you signed out
> of. Under "every browser" it's all of them.
>
> **So: every browser — blunt, reliable, nothing new stored about you? Or that browser only — precise
> when it works, silently does nothing when it doesn't, and we start keeping a per-browser identifier?**
>
> **The user answered: every browser.** Signing out of the Boomerang dashboard revokes every live
> extension grant on the account, in every linked browser — decided 2026-09-13 and registered as
> `MIG-19`. It's the only one of the two that never lies to you about being signed out, and switching
> to "that browser only" later remains a clean change that would not disturb anything already shipped.

The correlator that "that browser only" would have needed — a durable per-browser cookie and marker,
on both the pairing and the grant — is therefore not merely unbuilt; it is declined permanently.
Nothing on the account or the wire reserves a place for it, and adding it later is the same clean,
additive change it always would have been, not the completion of something left open.

---

## 5. What the pairing-lifecycle implementer may now assume

This section is written so it can be worked from alone. It is instructions, not narrative. Where it
contradicts [`boomerang-pairing-persistence.md`](boomerang-pairing-persistence.md), this section wins;
that document is a proposal and these are the rulings against it.

### 5.1 Build these three tables, and do not build the fourth

Build `pairing_requests`, `auth_grants` and `auth_credentials` as specified in the persistence
proposal's sections 3.1, 3.2 and 3.3, with these four changes:

1. **`pairing_requests.status` has three values: `pending`, `approved`, `redeemed`.** Do not add
   `rejected`. Rewrite the `pairing_requests_account_binding` check constraint to drop its
   `status = 'rejected'` branch; the remaining two branches are exhaustive.
2. **Drop `pairing_requests.approval_correlator_hash`.** Do not add it.
3. **Drop `auth_grants.browser_correlator_hash` and the `ix_auth_grants_account_id_correlator` index.**
   Do not add either.
4. **`auth_grants.revoked_reason` carries only reasons a row can actually hold:**
   `user_disconnected`, `dashboard_sign_out`, `refresh_reuse`. Drop `account_deleted`, which is
   unwritable once deletion removes the row, and drop `idle_expired` and `absolute_expired`, which are
   derived at read time and never stored.

**Do not build `revoked_credentials`.** There is no credential tombstone. Nothing survives account
deletion.

Everything else in those three tables stands as proposed and is load-bearing: `uq_auth_grants_id` is
required for account isolation and gets its own asserted test; the composite foreign key from
`auth_credentials` to `auth_grants` is `NOT DEFERRABLE` and `MATCH FULL` with no `ON UPDATE CASCADE`;
credentials are stored as an unsalted SHA-256 digest and never in plaintext; the verifier is never
stored in any form; and the grant has no `status` column.

`pairing_requests` is deliberately not account-scoped. Add it to the pinned `UNSCOPED_ROWS` registry
with `auth_grants` and `auth_credentials` scoped normally. `revoked_credentials` does not exist and
therefore does not join that registry.

### 5.2 The pairing state machine

Three transitions, each a single conditional statement, and no transition anywhere reads a row and then
writes it.

- **Approval** is the conditional `UPDATE` in the persistence proposal's section 4.1, minus the
  `approval_correlator_hash` assignment. `account_id` comes from the dashboard's authenticated
  principal and never from the request. Zero rows affected means re-read once and answer success
  idempotently if the row is `approved` with the caller's own `account_id`; otherwise answer the single
  indistinguishable failure.
- **Redemption** is the conditional `UPDATE` in section 4.2, returning `account_id` and `browser_label`
  and no correlator. Check the verifier **before** status, on every poll, so polling is not an approval
  oracle. Insert the grant and its two credential rows in the same transaction as the consuming
  `UPDATE`.
- **Handle both isolation outcomes.** Under `READ COMMITTED` the loser sees zero rows affected; under
  `REPEATABLE READ` or `SERIALIZABLE` it raises `40001`. Both mean "lost the race" and both return the
  standard failure. **Never blindly retry a serialization failure here** — a blind retry of a consumed
  pairing is the double-issue this predicate exists to prevent.
- **Redemption is at-most-once, not exactly-once, and that is accepted.** A lost response consumes the
  pairing; the extension starts a new one and the orphaned grant sits in the linked-browsers list until
  its idle limit passes or the user revokes it.
- **Expiry is never a status.** A pairing is expired when `expires_at <= now()`, evaluated in the
  predicate of every statement that touches it.
- **The short code is displayed and never submitted.** No lookup index on it, no code-entry route, ever.
  Store exactly what is displayed; keep the partial unique index over `pending` rows and the
  regenerate-on-conflict retry at creation.
- **The browser label is a closed server-side vocabulary** mapped from a small declared platform token.
  Never free text, never a raw user-agent string. Adding a value is a schema change.

### 5.3 Resolving a presented credential

Evaluate in order; first match wins. This replaces the persistence proposal's section 10 table.

| Condition | Status | `details.auth_reason` |
|---|---|---|
| Hash matches a live access credential and the grant is live | — | Authenticated |
| Hash matches an access credential past `expires_at`, grant still live | `401` | `credential_expired` |
| Hash matches a credential whose grant has `revoked_at` set | `401` | `grant_revoked` |
| Hash matches a credential whose grant is past its idle or absolute limit | `401` | `grant_revoked` |
| No credential presented, or the hash matches nothing anywhere | `401` | `not_linked` |
| Authenticated, but the route is restricted to the other client kind | `401` | `wrong_client_kind` |

`account_deleted` is never returned in v1. It remains in the published enum as a reserved value because
removing it would be a breaking change to a closed set.

Two rules underneath the table:

- **Grant status is checked on every request.** A live access credential on a revoked grant is refused.
  Credential expiry alone is never sufficient.
- **The pairing routes collapse every failure into one answer.** Unknown pairing, expired pairing,
  already-redeemed pairing and wrong verifier are indistinguishable — same status, same reason, same
  message, and no timing-observable branch before the verifier comparison.

**The extension's `not_linked` branch splits client-side**, and the extension implementer must be told
this explicitly because the server cannot tell them apart:

- presented no credential — offer the linking flow, clear nothing;
- presented a credential — terminal. Clear the credential, the local workflow records **and the
  checkpoints**. Render as not linked. Do not retry.

`client_kind` lives on the grant, not on the credential. The authentication dependency needs two
resolution modes — from `Authorization`, and from a presented refresh credential — producing the same
principal, because the refresh route is authenticated by the refresh credential and still has a caller
kind to enforce.

### 5.4 Revocation, and the one seam that moves

Rotation, reuse detection and the grace window are exactly as the persistence proposal's sections 5.2
and 5.3 specify. Reuse revocation stops at the grant: set `revoked_at` and
`revoked_reason = 'refresh_reuse'` on the grant and `revoked_at` on every credential row of that grant.
Other grants on the account, including the dashboard session, are untouched.

**Sign-out revocation goes behind one named function and nowhere else.** Write a single service-layer
operation — `revoke_grants_for_sign_out(account_id)` or equivalent — whose v1 body revokes the calling
dashboard's own grant and **every live extension-kind grant on that account**, with
`revoked_reason = 'dashboard_sign_out'`, in one statement per kind, always account-scoped.

That function is the seam. If the user chooses same-browser scope, the change is: add
`approval_correlator_hash` to the pairing, add `browser_correlator_hash` to the grant, copy it at
redemption, add the correlator cookie, and add one predicate to that function's extension-grant
statement. Nothing else in the lifecycle moves. Do not spread sign-out logic across handlers, and do not
inline the revocation predicate at a call site.

**Do not build the sign-out HTTP route in this ticket.** No document enumerates it; the contract records
it as deferred. Build the function and its tests; the route arrives with the user's answer.

`POST /v1/auth/grants/revoke` is separate and is in scope: the dashboard may revoke any grant on the
account, an extension principal may revoke only its own, and any other grant identifier returns
`404 not_found`. Revocation takes effect immediately, not at the next expiry.

**A revoked grant and its credential rows are retained until the grant's absolute expiry, then
deleted.** Reaping them early turns an accurate `grant_revoked` into an inaccurate `not_linked`.

`GET /v1/auth/grants` returns **extension-kind grants only**. A dashboard session is a grant and must not
appear in the linked-browsers list.

`last_used_at` is coarsened, not written on every request: update only when the stored value is older
than a configured refresh threshold.

### 5.5 Account deletion

In the deletion transaction, before the `204`, delete the account's `auth_credentials` rows, its
`auth_grants` rows, and any `pairing_requests` rows bound to it. The last is not optional — an
approved-but-unredeemed pairing holds a foreign key to the account and would otherwise block the delete.

Write no tombstone. A later call from a linked extension resolves to nothing and answers `not_linked`,
and the extension takes its presented-a-credential branch and clears everything.

The residual the contract already names stands: the extension learns of the deletion only on its next
call, and if that browser is never opened again it never learns.

### 5.6 Numbers

**Invent none.** Every one of these is a configuration value with no default in code and no default in
the schema, and all of them belong to `ARCH-B4`: access-credential lifetime, refresh-credential
lifetime, grant idle limit, grant absolute limit, pairing lifetime, the rotation grace window, the
`last_used_at` coarsening interval, and every rate-limit ceiling.

Two constraints hold whatever the numbers are, and both must be enforced by a configuration check
rather than by a reviewer's memory. The coarsening interval must be far smaller than the idle limit, or
the idle limit is evaluated against a stale value and grants outlive it. And, added 2026-09-13 by
`MIG-20`, **a dashboard access credential's lifetime must equal its grant's lifetime**: the dashboard
leg has no refresh path, so a shorter-lived dashboard credential would end a live session with no way
to continue it. A configuration violating either constraint fails validation rather than starting.

Rate limits on pairing creation and redemption are a named phishing mitigation. Implement the limiter
behind an interface with an in-process implementation, and record plainly that an in-process counter is
close to useless in a multi-instance topology. Do not put rate-limit counters in these tables; a
per-request write on an unauthenticated route is its own denial-of-service surface.

### 5.7 Reaping

**Pairings are reaped on the request path.** `POST /v1/auth/pairings` deletes a bounded, `LIMIT`-ed,
indexed set of rows whose `expires_at` is comfortably past, before it inserts. The server still never
initiates anything — a user's own request does the work.

**Build no scheduler in this ticket.** Credentials, grants and expired revoked grants need a real
maintenance task, and that task is the first scheduled server-side job in the system and requires the
repo-wide guardrail document to be amended rather than quietly excepted. Until it exists these rows
accumulate, and that is correctness-neutral: every predicate in this design evaluates expiry at read
time, and nothing becomes valid again because a reaper did not run. Its omission degrades storage and
nothing else.

### 5.8 What is out of scope for this ticket

No decline route. No correlator, in any form. No credential tombstone. No sign-out HTTP route. No
scheduled maintenance job. No dashboard-initiated or server-initiated summary reset. No cap on linked
browsers. No browser-identity permission and no manifest change of any kind. No lifetime, grace-window
or rate-limit number.

### 5.9 Tests that must exist

Beyond the contract's existing list, this ticket's rulings require:

1. two concurrent redemptions of one pairing yield exactly one grant, asserted under both isolation
   outcomes;
2. a pairing identifier without the verifier discloses nothing — a pre-approval poll and a post-approval
   poll from a non-holder are indistinguishable;
3. unknown, expired, consumed and wrong-verifier redemptions return the identical status, reason and
   message;
4. a rotated-away refresh credential inside the grace window rotates normally; outside it, and for any
   older generation, the whole grant is revoked and no other grant on the account is;
5. a bearer credential minted for one account cannot read another account's item, and no second grant
   row can share an id under another account;
6. account deletion removes credentials, grants and account-bound pairings before the `204`, and a
   subsequent call from a previously linked extension returns `401` with `not_linked`;
7. sign-out revocation, called on an account with grants in two browsers and a second account holding a
   grant on the same machine, revokes both of the first account's extension grants and neither of the
   second's;
8. an approval binds the pairing to the dashboard principal's account and never to anything in the
   request body, and a pairing approved by one account cannot be re-approved by another;
9. `GET /v1/auth/grants` returns no dashboard-kind grant.

---

## 6. What this document could not resolve

| Unresolved | What it blocks |
|---|---|
| **The dashboard sign-out route's wire shape** | Nothing in the pairing lifecycle, because of the seam in section 5.4. The revocation *scope* itself is closed — account-wide, decided 2026-09-13 and registered as `MIG-19`, with the correlator declined permanently — and only the route's contract entry remains to be written; see section 4 |
| **The `SameSite=Lax` registrable-domain precondition** | Deployment, not implementation. The dashboard origin and the API origin must share a registrable domain or the dashboard session cookie does not survive a cross-site POST at all. The accepted design states this conditionally and relies on it absolutely, and the production hostname is unchosen. The implementer must assume a shared registrable domain and fail configuration validation loudly if the configured origins do not share one |
| **The rate-limit store** | Not implementation — the limiter ships behind an interface. It blocks the honesty of the phishing mitigation the accepted design claims, and it cannot be settled before the deployment topology is |
| **Migration tooling** | Everything, eventually. These three tables land in `Base.metadata` with no migration path, in the same window as the account-scoping change that already made this urgent. Not created here; made worse here |
| **Every lifetime and ceiling** (`ARCH-B4`) | Nothing structural. The shapes hold whatever the numbers are, and section 5.6 forbids inventing them. It blocks a deployable configuration |
| **The isolation level and the session lifecycle** | Nothing, because section 5.2 requires both branches to be handled. It blocks removing one of them |
| **The append-only transition record** | Nothing here. It stays under `ARCH-B4`, where the `ARCH-B1` sub-decision left it |
| **Native enums versus constrained text** | Nothing. This ticket follows the existing convention and converts with it if that open low-level-design finding reverses |

---

## 7. Amendments the accepted documents need

These are edits to documents this one may not modify. Each is named precisely so it can be dispatched
as its own change. **The first three are corrections of statements that are wrong, not merely
under-specified**; the rest are consequences of the rulings above.

| Document | Location | Edit |
|---|---|---|
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §12, the sentence "Any subsequent call from any of them returns `401 unauthenticated` with `details.auth_reason` of `account_deleted`" | **Wrong as written** — no implementation that deletes the account's rows, which the same section requires, can return it. Replace with `not_linked`, and add that the extension's terminal cleanup is selected by whether it presented a credential |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §4.1, the discriminator table | The `not_linked` row's required client behaviour must split on whether a credential was presented; the `account_deleted` row must be marked reserved and unreachable in v1 |
| [`boomerang-extension-auth-proposal.md`](boomerang-extension-auth-proposal.md) | §6, the "Explicit approval copy" bullet | **Wrong as written** — it requires the page to tell the user to decline, and the same document's §12 route list contains no decline route. Change "says to decline if the user did not just install the extension in this browser" to "says to close the page if the user did not just install the extension in this browser, and that the request expires on its own" |
| [`boomerang-extension-auth-proposal.md`](boomerang-extension-auth-proposal.md) | §10, the revocation-events table, account-deletion row | "a reason meaning the account is gone" is unachievable; state the `not_linked` posture and that the extension's cleanup is unchanged |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §13, the `401 unauthenticated` bullet | Same split as §4.1 |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §5.1, `GET /v1/auth/grants` | "One entry per live grant on the account" becomes extension-kind grants only, so the route and the linked-browsers list describe the same set |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §14, contract tests | Add the not-linked-after-deletion test; the existing tests 18 and 19 are unaffected |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §15, deferred contracts, the sign-out/correlator row | Amend to record that no correlator ships in v1, permanently, and that the revocation scope is closed account-wide (`MIG-19`); only the sign-out route's wire shape remains deferred |
| [`boomerang-extension-auth-proposal.md`](boomerang-extension-auth-proposal.md) | §13 item 1 | **Already amended.** The user answered account-wide on 2026-09-13; the scope clause is amended in place there and registered as `MIG-19`. No further edit is pending |
| `AGENTS.md` (repo root) | The rules list | Add: the extension has no Google relationship and gains no identity permission; the credential never enters synced storage; no content script touches the credential or the network |

---

## 8. Where these decisions are registered

[`../plan/boomerang-decisions.md`](../plan/boomerang-decisions.md) carries them as `MIG-17` (the v1
authentication posture: no decline route, no correlator, no tombstone), `MIG-18` (the two standing
constraints from section 13 items 3 and 6), `MIG-19` (the revocation scope, closed account-wide),
`PROV-05` (account-wide sign-out revocation, resolved by `MIG-19`), `PROV-06` (no cap on linked
browsers), `PROV-07` (what the approval screen shows), and `PROV-08` (no invented numbers, including the
`MIG-20` dashboard-credential-lifetime constraint in section 5.6). Automatic linking after the bridge
gate joins the deferred-capabilities table. The revocation-scope question is recorded as closed against
`MIG-15` and `ARCH-B9`; the sign-out route's wire shape is the one item from that gate that remains
open.

The sign-out stranding residual is **not** re-registered here. It is already recorded inside the
`ARCH-B1` sub-decision, which names it precisely, and duplicating it would create a second place for it
to be marked closed.
