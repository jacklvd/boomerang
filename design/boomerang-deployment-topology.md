# Boomerang deployment topology and schema-migration tooling

Status: **recommendation, awaiting sign-off.** Nothing here has been implemented, and no file in
`infra/` was modified to produce it. Covers `INF-1` (deployment topology) and `INF-3` (schema
migration tooling), which are resolved together because the answer to one changes the answer to the
other.

Author's note on scope: this document decides nothing on its own. `infra/AGENTS.md` is explicit that
the topology decision belongs in `plan/boomerang-decisions.md` once made. Section 8 lists the items
that are the user's call rather than mine.

---

## 0. Summary

| Question | Recommendation | Confidence |
|---|---|---|
| `INF-1` production-shaped topology | Defined in section 4, **not built yet** | Medium |
| `INF-1` what to actually stand up now | Single EC2 instance in AWS, single public origin behind a reverse proxy, Postgres on the box — section 5 | Medium-high |
| `INF-1` salvage in `infra/` | The IAM role, the provider/tagging block and the SSM shell output. Everything else is dead weight — section 6 | High |
| `INF-3` migrations | **Adopt Alembic this week**, baseline generated *after* the two in-flight table tickets land — section 7 | High |
| Rough monthly cost of the recommendation | **~$20–35/month infrastructure, plus a Bedrock bill that is the only line item that can run away** — section 3 | Medium |

The two recommendations are coupled. The PoC topology I recommend puts a PostgreSQL instance
somewhere that survives a redeploy. The moment that exists, `Base.metadata.create_all` stops being
an honest choice, because there is a database holding rows nobody wants to recreate by hand. If the
user rejects section 5 and keeps the demo entirely on a laptop with a disposable container, then
`create_all` remains defensible and `INF-3` can slip — that is the one trigger, and it is stated
plainly in section 7.

---

## 1. What is actually true today

Verified against the working tree, not inferred from documents:

- `infra/*.tf` provisions a VPC, two public subnets, an internet gateway, a security group, an IAM
  instance role and one EC2 instance. There is **no `aws_db_instance` and no `aws_rds_cluster`
  anywhere**. The "database-backed dashboard" is architecture, not deployed fact.
- There is **no migration tooling of any kind** — no `alembic`, no `alembic.ini`, no `migrations/`,
  and no entry in `server/uv.lock`. Schema exists only as Python declarations in
  `server/app/db/models.py`, instantiated by `Base.metadata.create_all()` inside the opt-in
  integration tests against a `tmpfs`-backed container.
- **Nothing is deployed.** No hostname, no certificate, no database, no secret store entry, no
  Google OAuth client.
- The server already depends on `mangum` and `fastapi[standard]`, so both a Lambda shape and a
  long-lived-process shape are one configuration change away. Nothing in the code forecloses either.

This is the cheapest moment every decision in this document will ever have. That is the whole
argument for making them now rather than after the deadline.

---

## 2. What has to exist for this to run

Six things, in dependency order. Four of them are not compute and are the ones that get forgotten.

### 2.1 A real registrable domain — this is the constraint people miss

The accepted authentication design (`MIG-15`) puts a `Secure; HttpOnly; SameSite=Lax` cookie on the
dashboard leg and allows credentials to cross on that origin. The extension-auth proposal is explicit
about what makes that work: *"If the dashboard and the API share a registrable domain, `SameSite=Lax`
permits the dashboard's own cross-origin calls while blocking genuinely cross-site ones."*

The consequence is load-bearing for topology and it is easy to get wrong:

- **A platform-provided hostname will not do.** `*.vercel.app`, `*.onrender.com`, `*.trycloudflare.com`
  and similar shared suffixes sit on the Public Suffix List, which means two subdomains of one of
  them are *cross-site to each other*, not same-site. A `SameSite=Lax` cookie issued by the API would
  simply not be attached to the dashboard's requests, and the failure is silent — an unauthenticated
  response, not an error anyone can grep for. I have not re-verified the PSL entry for every AWS
  service hostname and I would not want the design to depend on the answer.
- Therefore: **register a domain, or use one the team already owns.** Cost is negligible (~$12–15/yr)
  and it is a hard prerequisite for anything else, including the Google OAuth client's redirect URI.
- **Recommended, and needing sign-off (section 8): serve the dashboard and the API from one origin**,
  with the API mounted at `/v1/*` behind a reverse proxy or a CDN behavior. That makes the session
  cookie same-origin, removes the dashboard leg from the CORS allowlist entirely, and removes the PSL
  question from the design. The API contract's dashboard-leg CORS rules then become trivially
  satisfied rather than deleted. Two subdomains of one registrable domain
  (`app.example.com` / `api.example.com`) also work and match how the contract imagines it; they cost
  one more certificate and keep a cross-origin preflight in the hot path.

### 2.2 The exact-origin CORS allowlist

Per the API contract's cross-origin section, the allowlist is exact and per-environment, no wildcard
is ever emitted in any environment, `Vary: Origin` goes on every response including preflights, and
an absent origin is refused rather than answered permissively. For deployment that means:

- The concrete origin strings are **environment configuration**, so the topology has to supply them
  as configuration to the service — an environment variable or a Parameter Store value, one per
  environment. Nothing in `server/.env.example` carries them today.
- The dashboard origin follows from 2.1.
- **The production extension origin is not knowable yet.** `chrome-extension://<published id>`
  requires a published extension, and `extension/` is not built. The production allowlist therefore
  cannot be finalized before the extension is submitted, and the deployment has to tolerate that
  entry arriving later as a config change rather than a code change.
- The development extension ID is only stable if the unpacked build pins a `key` in its manifest.
  Someone has to own that; without it every developer machine produces a different origin and the
  development allowlist is unmaintainable.
- The extension leg is preflighted (`Authorization` is not safelisted) and must **never** receive
  `Access-Control-Allow-Credentials`. That is application behavior, not infrastructure, but a CDN or
  proxy sitting in front of the API can break it by caching or rewriting CORS headers. If a CDN is
  used, the API behavior must forward and vary on `Origin` and must not cache authenticated
  responses — which the contract already requires via `Cache-Control: private, no-store`.

### 2.3 The FastAPI service

Python 3.13, `uv`-managed, async SQLAlchemy 2.0 over `psycopg`, cold-start work in the FastAPI
`lifespan`. Two viable shapes:

- **A long-lived process** (container on EC2, ECS Fargate or App Runner). Normal connection pooling,
  no cold start, lifespan runs once per process, no adapter in the path.
- **Lambda via Mangum**, which the dependency set already anticipates. Cheaper at zero traffic, but
  it puts an async SQLAlchemy pool behind a concurrency model that creates and freezes one pool per
  execution environment. That is a known source of connection exhaustion against a small Postgres
  instance and usually ends in RDS Proxy, which is another ~$12+/month and more moving parts.

For a database-backed service on a deadline, **the long-lived process is the lower-risk shape**, and
it is what section 5 recommends. Lambda is not wrong; it is wrong *first*.

### 2.4 PostgreSQL

Durable, and a hard requirement of any topology per `infra/AGENTS.md`. Options and their real cost
are in section 3. The choice between "a container on the app box" and "a managed instance" is a
sign-off item, because it is the same choice as the `INF-3` trigger.

### 2.5 Bedrock access, with no credential on disk

Both `AGENTS.md` files are unambiguous: credentials belong on an IAM role attached to whatever
compute is chosen, never in a `tfvars` file, an environment variable, or an image. This is the single
strongest argument for keeping compute inside AWS. Running the server on a non-AWS platform
(Render, Fly, Railway) means minting a long-lived IAM user access key and putting it in that
platform's environment — which is precisely the thing the workspace rule forbids. I am not
recommending a non-AWS host, and if the user wants one, that rule needs an explicit, recorded
exception rather than a quiet violation.

Two further provisioning notes:

- **Region must be one where the configured Bedrock model is available.** `BEDROCK_MODEL` has no
  default in code and is validated at startup, so a wrong region fails at first invoke, not at
  `terraform apply`. Confirm the identifier for the chosen region before the first deploy.
- The existing Bedrock IAM policy grants `bedrock:InvokeModel` on `Resource = "*"`. When narrowing
  it, note that invoking through a regional inference profile generally requires the grant to cover
  **both** the inference-profile ARN and the underlying foundation-model ARNs in each member region.
  I have not verified this against a live account and it is the most likely cause of a
  "permissions look right but invoke is denied" first deploy. Budget an hour for it.

### 2.6 Secrets

`infra/AGENTS.md` already settles the mechanism: written once by hand as a `SecureString`-style
parameter, with Terraform granting read access and never holding the value, because state is a
plaintext file retained across every historical version. SSM Parameter Store standard tier is free
and is the right choice; Secrets Manager buys rotation nobody needs yet at $0.40/secret/month.

What has to be stored, at minimum:

| Secret | Notes |
|---|---|
| Database connection URL / password | Not needed if using an IAM-authenticated database, which is extra work not worth it now |
| Google OAuth client secret | Sign in with Google, **identity scopes only** — repo rule 1 is absolute |
| Session/credential signing key | The grant and pairing records store hashed credentials; whatever pepper or signing key that involves |
| Allowed origin strings | Not secret, but environment config that has to come from somewhere |

The current IAM role has **no** `ssm:GetParameter` / `kms:Decrypt` grant. That is a gap in the
existing Terraform, not something the new topology invents.

---

## 3. Cost

All figures are `us-east-1` on-demand list price, rounded, for a single environment with demo-level
traffic. They exclude tax and assume no free-tier credit (if the AWS account is under twelve months
old, the database line may be free, which I cannot verify from here).

### Recommended PoC (section 5)

| Line | Monthly |
|---|---|
| EC2 `t4g.small` (2 vCPU Graviton, 2 GB), on-demand | ~$12 |
| EBS gp3, 30 GB | ~$2.40 |
| Public IPv4 address (charged since Feb 2024) | ~$3.65 |
| Route 53 hosted zone + queries | ~$0.60 |
| Domain registration, amortized | ~$1.20 |
| SSM Parameter Store (standard tier) | $0 |
| CloudWatch Logs, low volume | ~$0.50–1 |
| Data transfer out (first 100 GB/mo free) | ~$0 |
| **Infrastructure subtotal** | **~$20/month** |

Use `t4g.medium` (~$24/month instead of $12) if images are built on the box rather than in CI; 2 GB
is tight for a Next.js build alongside Postgres. Building in GitHub Actions and pulling from ECR
keeps the small instance and is the better habit anyway.

### Bedrock — the line that can run away

Bedrock is partner-operated with its own published pricing, which I have not fetched and which should
be confirmed on the AWS Bedrock pricing page before anyone relies on a number. As an order of
magnitude, Anthropic first-party rates for the currently configured model class are $5 per million
input tokens and $25 per million output tokens; Sonnet-class is $2/$10 and Haiku-class $1/$5.

With `BEDROCK_MAX_TOKENS = 4096` and a bounded order-list ingest subtree, a single parse plausibly
costs on the order of **$0.05–0.15**. A demo week of a few hundred parses is **$10–30**. That is
fine.

**The finding is not the steady-state number, it is the exposure.** `server/AGENTS.md` describes the
ingest payload ceiling as *"a cost control on an endpoint anyone can call"* — the ingestion endpoint
is unauthenticated. On a laptop behind no public DNS that is theoretical. On a public hostname it is
a stranger's ability to spend your Bedrock budget in a loop. Mitigations, in order of how much they
cost to add:

1. **Do not expose the ingest route publicly until the extension auth grant gates it.** Cheapest and
   most effective. Until then, the deployed surface is the dashboard and the authenticated routes.
2. An AWS Budgets alert and a CloudWatch alarm on Bedrock invocation count, with a real email on it.
   Half an hour of work; the difference between a surprise and an incident.
3. Rate limiting at the proxy on the ingest path.

A PoC that quietly costs real money is exactly this shape, and it is why the item is called out
rather than buried in the table.

### Production-shaped, for comparison (section 4, not recommended now)

| Line | Monthly |
|---|---|
| App Runner (0.25 vCPU / 0.5 GB, request-billed vCPU) | ~$5 |
| RDS PostgreSQL `db.t4g.micro`, single-AZ, 20 GB gp3 | ~$15 |
| Bedrock reachability from a VPC: interface endpoint (~$7.30/AZ) or NAT gateway (~$33 + data) | ~$8–33 |
| CloudFront in front of one origin | ~$1 |
| Next.js dashboard hosting (Amplify, or same container) | ~$0–5 |
| Route 53, ACM, Parameter Store | ~$0.60 |
| **Subtotal** | **~$30–60/month** |

Swapping App Runner for ECS Fargate adds an ALB at ~$17/month, which is why App Runner wins at this
size. Multi-AZ RDS doubles the database line. The VPC-egress row is the one that surprises people: a
service inside a VPC cannot reach Bedrock without either a NAT gateway or an interface endpoint, and
the NAT gateway alone costs more than the entire recommended PoC.

---

## 4. `INF-1` — the smallest credible production-shaped deployment

Recorded so that the PoC has a target to grow into, and so the shortcuts in section 5 are visible as
shortcuts. **I am not recommending building this now.**

```
                        one registrable domain
                                 │
                        CloudFront (ACM cert)
                    ┌────────────┴────────────┐
              default behavior            /v1/* behavior
                    │                          │
          Next.js dashboard            FastAPI on App Runner
          (Amplify or container)      (VPC connector, IAM role)
                                               │
                              ┌────────────────┴──────────────┐
                      RDS PostgreSQL                  Bedrock, via
                      (private subnets,               interface endpoint
                      two AZs, automated              or NAT
                      backups)
                                               │
                                    SSM Parameter Store
                                    (SecureString, read-only grant)
```

Properties that make it "production-shaped" rather than merely deployed: the database is managed,
backed up and not on the same disk as the application; the compute is replaceable without data loss;
secrets are never in Terraform state; there is one public origin so the session cookie is
same-origin; the two-AZ subnet layout that `infra/AGENTS.md` insists on is load-bearing again,
because an RDS subnet group requires it.

What it does **not** include, deliberately: multi-AZ failover, a staging environment, autoscaling,
WAF, or a deployment pipeline beyond "build image, update service". Each of those is a real cost and
none is credible to add before a first user exists.

---

## 5. `INF-1` — what I recommend standing up now

**One EC2 instance in AWS, running the whole stack under Docker Compose behind a TLS-terminating
reverse proxy on a single public origin, with an IAM instance role for Bedrock and SSM.**

```
  https://app.<yourdomain>            ← one origin, one ACM/Let's Encrypt cert
            │
     Caddy or nginx on the instance
     ┌──────┴───────┐
   /  → Next.js   /v1/* → FastAPI ──→ Bedrock (IAM instance role, no keys)
                              │
                     Postgres container
                     on a dedicated EBS volume
                              │
                   SSM Parameter Store (SecureString)
```

Why this and not the section 4 topology, given the deadline:

1. **It is the fastest path from "nothing deployed" to "someone outside the team can reach it."**
   `docker compose up` already describes the whole stack. The delta is a reverse proxy, a domain, a
   Postgres service, and a systemd unit.
2. **It satisfies every hard constraint**, which is what makes it credible rather than merely quick:
   IAM role for Bedrock with no credential on disk; secrets from Parameter Store; a single origin, so
   the `SameSite=Lax` cookie works and the CORS allowlist only ever has to carry extension origins;
   a durable database.
3. **It costs about a third of the production-shaped option** and has no NAT gateway, no ALB and no
   RDS instance to forget about.
4. **It reuses the most valuable thing in `infra/`** — the IAM role, instance profile, Bedrock policy
   and the SSM-session shell output — rather than throwing them away.
5. **Its failure mode is acceptable.** One box, no redundancy, a manual restore if the volume dies.
   For a PoC with no external users, that is the correct trade. For a real user base it is not, which
   is what section 4 is for.

Honest weaknesses, stated rather than hidden: it is a pet, not cattle; the database shares a disk and
a blast radius with the application; there is no automated backup unless someone adds an EBS snapshot
schedule (do — it is a one-line `dlm` policy and it is what makes the `INF-3` answer survivable); and
`terraform destroy` takes the data with it, so the volume should be a separate resource with
`prevent_destroy` rather than the instance's root volume.

### How to build it without touching the legacy files

**Do not edit `infra/main.tf`.** Create a new Terraform root — `infra/poc/` — and build there. Leave
the legacy scaffold untouched until the new root applies cleanly end to end, then delete the legacy
files in a single, separate, reviewable commit. That sequence respects "don't delete historical
artifacts", keeps `git log` legible, and means a failed experiment costs nothing. It also means
`infra/AGENTS.md`'s "Legacy scaffold" section stays accurate right up until the moment the scaffold
goes away.

### The alternative I am explicitly not recommending, and when it wins

**Deploy nothing. Keep the demo on a laptop.** `infra/AGENTS.md` says the PoC demo runs on a laptop
and that infra "only matters once someone outside the team needs to reach a deployed service." If
nobody outside the team needs to reach it before the deadline, then the cheapest correct answer to
`INF-1` is a recorded decision and no resources. Cost: the domain, if you want one reserved. With a
tunnel bound to a domain you control, a laptop can even serve a real HTTPS origin that satisfies the
cookie and CORS requirements — so "laptop" does not mean "cannot demo to an outsider."

I do not know whether an external demo is scheduled. That is sign-off item 1, and it is the single
question that changes the most.

---

## 6. What in `infra/` is salvageable and what is dead weight

Assessment only. **Nothing in `infra/` was modified.**

### Worth keeping — move it into the new root

| Thing | Why |
|---|---|
| `aws_iam_role.app`, `aws_iam_instance_profile.app`, the `AmazonSSMManagedInstanceCore` attachment, `aws_iam_role_policy.bedrock` | The most valuable code in the directory. It is exactly the zero-credentials-on-disk Bedrock path both `AGENTS.md` files demand, and it works. Needs two changes: narrow `Resource = "*"` on the Bedrock policy (see 2.5), and add the missing `ssm:GetParameter`/`GetParameters` and `kms:Decrypt` grants. If the compute shape ever changes, the assume-role principal changes with it. |
| `provider "aws"` block with `default_tags` | Correct, and the "don't hand-tag resources" rule depends on it. |
| `terraform` block — version floor, provider pin, the S3 backend `dev-note` | The backend note is right and should be acted on the moment a second person applies. |
| `variables.tf`: `name`, `region`, `vpc_cidr` | Fine as-is. |
| `metadata_options { http_tokens = "required" }`, `root_block_device { encrypted = true }` | Good hygiene, keep by default. |
| `outputs.tf` `shell` (SSM `start-session`) | Genuinely useful and costs nothing. |
| `terraform.tfvars.example` + the gitignore pattern | Keep the convention. |
| The two-AZ subnet layout | Dead for the single-instance PoC, load-bearing again for section 4's RDS subnet group. Keep the code, don't collapse it. |

### Dead weight — do not carry it forward

| Thing | Why |
|---|---|
| `aws_security_group.app` ingress on **3000 and 8000** from `allowed_cidr` | A deployed service needs 443 from the internet, not two dev ports from one office IP. Entirely wrong shape. |
| The `allowed_cidr != "0.0.0.0/0"` validation, and `infra/AGENTS.md`'s instruction not to "fix" it | **The most actively misleading artifact in the directory.** Its stated rationale — the instance runs the service holding every credential, and must not be exposed — was correct for a bare dev box on port 8000. It is wrong for a TLS-terminated, authenticated public product, where 443 from `0.0.0.0/0` *is* the requirement. A future agent that reads the guide and obeys it will be blocked from doing the correct thing and will not know why. This needs an explicit retraction in `infra/AGENTS.md` when the topology is recorded. `infra/AGENTS.md` already has uncommitted modifications, so the user may want to fold it into that edit. |
| The `user_data` block | Installs Docker, then downloads `docker-compose` from `releases/latest` — unpinned — and stops. It checks out nothing, starts nothing, terminates no TLS and sets no restart policy. It produces a box with Docker on it and no application. Rewrite; there is nothing to salvage. |
| `data.aws_ssm_parameter.al2023` (x86_64) and `instance_type = "t3.small"` | Only if moving to Graviton, which is ~20% cheaper for this workload. A judgment call, not a defect. |
| Local Terraform state | Fine for one person, a real blocker for two. The S3-backend note in `main.tf` is the fix. |
| `instance_public_ip` output | Harmless, but the thing you actually want is a DNS name. |

### Missing entirely

No database. No secret store resources or grants. No DNS, no certificate, no hosted zone. No service
manager, so nothing restarts after a reboot. No backup or snapshot policy. No budget alarm. Every one
of these is a requirement of the running system, and none of them exists in any form.

### Adjacent finding, outside `INF-1` but worth someone's attention

`client/AGENTS.md` is stale in a way that would mislead a frontend hosting decision. It states that
the dashboard's *"data comes from the extension, not from the server,"* that *"the server is
stateless and has no `GET /orders` to call,"* and that there is *"no signup, no OAuth, no account
creation."* All three contradict `MIG-01` and `MIG-02`. It is not my ticket and I did not touch it,
but anyone sizing the frontend from that file will size the wrong thing.

---

## 7. `INF-3` — migrations

**Recommendation: adopt Alembic this week. Generate the baseline revision after the two in-flight
table tickets land, not before.** High confidence.

### Why now, and not after the PoC

This is not my finding; it is already the accepted position of documents this repo treats as
authoritative, and `INF-3` is the ticket that executes it.

- The account-scoping design — accepted as `MIG-16` on 2026-09-13 — recommends adopting migration
  tooling in the same change, *"not because this change needs it, but because the next one will and
  this is the last moment adding it is free,"* and notes that *"a project with no migration history
  gets exactly one chance at a clean baseline."*
- `PROV-03` in the decisions record states that migration tooling *"does not yet exist in this
  repository at all, which `MIG-16` makes urgent rather than optional."*
- The low-level design review's `DAL-5` already recommended decoupling migrations from the retention
  blocker and adopting a tool at the first persisted table.

### The honest tradeoff, stated as the ticket frames it

`create_all` costs nothing until the first deployed database holds data anyone cares about. After
that, every schema change becomes a manual operation — and the account-scoping document's own online
migration table shows what that looks like for a change that is currently *one file edit*: add
nullable column, backfill in batches, `NOT VALID` check plus `VALIDATE`, `CREATE UNIQUE INDEX
CONCURRENTLY`, foreign keys as `NOT VALID` then validated, and one primary-key swap that takes a real
`ACCESS EXCLUSIVE` lock and therefore a maintenance window. Application code has to tolerate both
shapes across the whole window.

Two tickets are adding tables this week — account-scoped composite primary keys on `order_items`,
`return_policies`, `policy_rules` and `return_summaries`; and the pairing and grant records from
`MIG-15`. Those are the exact changes that are free today and expensive after a deployment. The
argument for Alembic is not that this week's changes need it. It is that Alembic costs roughly half a
day *this week* and an unbounded amount of careful work in any week after the first real database
exists — and section 5 recommends creating exactly that database.

### The trigger that would force the other choice

**If the user rejects section 5 and decides nothing gets deployed before the deadline — demo on a
laptop, container recreated from scratch every run — then `create_all` remains honest and `INF-3` can
slip past the deadline.** In that world there is no database whose contents anyone would mourn, and
migration tooling is unearned ceremony.

The trigger that ends that reprieve is precise and worth writing into the decision record: **the
first PostgreSQL data directory that is not recreated from empty on every start.** A named Docker
volume counts. An EBS volume counts. An RDS instance counts. The moment one exists, `create_all` is
no longer a choice, it is a deferred manual-DDL debt with interest.

### Sequencing — this matters more than the decision itself

Two other agents are editing `server/` concurrently. Getting this wrong wastes the one clean baseline:

1. **Let the composite-primary-key change and the pairing/grant tables land first.** A baseline
   generated today captures a schema that is stale by Friday, and the whole value of the baseline is
   that the composite keys and composite foreign keys *are* the origin rather than a later
   alteration.
2. `uv add alembic` — never `pip`, never `requirements.txt`, per `server/AGENTS.md`.
3. `alembic init -t async`; point `env.py` at the existing async engine and `Base.metadata`.
4. Generate exactly one baseline revision, review the generated DDL by hand, and confirm it matches
   what `create_all` produces.
5. Add a `make migrate` target alongside the existing gates.
6. **Keep `create_all` in the integration tests.** `server/AGENTS.md` is explicit that schema
   lifecycle is observable there on purpose, and the account-scoping document makes the sharper point:
   if `create_all` and the migration history ever diverge, one of them is wrong, and a test comparing
   the two catches it. Delete it and you lose a free cross-check.

### Two gotchas that decide whether this takes half a day or two

- **The quality gates will reject generated code.** `server/` runs `ruff` with `select = ["ALL"]`,
  `mypy --strict`, and a 95% line *and* branch coverage floor currently sitting at 100%. Alembic's
  generated `env.py` and every revision file will fail docstring rules, annotation rules, `INP001`,
  strict typing, and will drag coverage below the floor. `migrations/` must be excluded from ruff,
  mypy and coverage in `pyproject.toml` in the same change. This is the step that surprises people,
  and it is a `pyproject.toml` edit inside `server/` — so it belongs to whoever owns that file this
  week, not to `INF-3` acting unilaterally.
- **Autogenerate and native PostgreSQL enums do not get along.** The ORM layer uses six native enum
  types. Alembic's autogenerate does not reliably emit `CREATE TYPE` / `ALTER TYPE ... ADD VALUE`, so
  the baseline revision needs those reviewed and, likely, hand-written. Assume the first revision is
  read line by line rather than trusted. The separate enum-versus-text question `DAL-5` raises is
  untouched by this and stays open on its own terms.

---

## 8. Needs the user's decision, not mine

Listed in the order that unblocks the most work.

1. **Is an externally reachable deployment actually needed before the deadline?** If not, the correct
   answer to `INF-1` is a recorded decision and zero resources, and `INF-3` gets a stay of execution
   under the trigger in section 7. This question changes more than any other and I cannot answer it
   from the repository. *(Recommendation: if there is any chance the answer is yes, section 5 is
   cheap enough to just do.)*
2. **Which domain.** A real registrable domain the team controls is a hard prerequisite (section 2.1)
   and gates the Google OAuth client's redirect URIs, the certificate, and the CORS allowlist. Nobody
   but the user can pick it.
3. **Single origin, or `app.` + `api.` subdomains?** *Recommendation: single origin* — it removes the
   dashboard leg from CORS entirely and takes the Public Suffix List out of the security argument.
   Flagged because the accepted auth design describes the dashboard leg as cross-origin, so choosing
   single-origin is a (simplifying) deviation from how the contract imagines it and should be
   recorded as such rather than discovered later.
4. **Postgres on the box, or a managed instance?** On the box: ~$0 extra, one blast radius,
   restore-from-snapshot is manual. Managed: ~+$15/month, backups included, survives the instance.
   *Recommendation: on the box for the PoC, with a scheduled EBS snapshot policy on a dedicated
   volume that has `prevent_destroy` set.* Either way the `INF-3` trigger fires.
5. **Who owns the extension ID problem?** The production CORS allowlist cannot be completed until the
   extension is published, and the development allowlist is unmaintainable until an unpacked build
   pins its manifest key. `extension/` is not built and has no owner in this ticket.
6. **Who creates the Google OAuth client** (identity scopes only — repo rule 1 is absolute) and writes
   its secret into Parameter Store by hand? Terraform must never hold that value.
7. **Model choice for the parse path.** Moving the parse call from the Opus-class model to a
   Sonnet-class one would cut the Bedrock line by roughly 60%. That is a quality-versus-cost trade
   about the product's core function, and it is the user's call, not an infrastructure decision. I am
   not recommending it — only noting that it is the largest single lever on the one cost line that
   can run away.
8. **Retracting the `allowed_cidr` guidance in `infra/AGENTS.md`** (section 6). That file is binding
   and currently instructs future agents not to fix something that will need fixing. It also has
   uncommitted modifications right now, so the user may want to fold the retraction in rather than
   leave it for a later, conflicting edit.

---

## 9. Uncertainties

Stated rather than smoothed over.

- **AWS pricing** is from memory of list prices and was not fetched; no `aws` CLI call was made and
  no cloud account was touched. Treat every figure as order-of-magnitude. The Bedrock rates in
  particular are partner-operated and published separately from Anthropic's first-party rates —
  confirm them before quoting the number to anyone.
- **Public Suffix List membership** for specific AWS and platform hostnames was not verified. The
  recommendation in 2.1 is deliberately built so that the answer does not matter: own the domain, and
  the question never arises.
- **The Bedrock inference-profile IAM grant** (2.5) is the item I am least sure about and most sure
  will cost someone an afternoon.
- **Free-tier eligibility** is unknown from here. If the AWS account is new, the database and some
  compute may be free for twelve months, which changes the comparison in section 3 materially.
- **`t4g.small` sizing** for a Next.js build plus FastAPI plus Postgres on one box is an estimate. If
  builds happen on the instance, assume `t4g.medium`.
- **Alembic effort** is estimated at half a day *excluding* the quality-gate exclusions and the enum
  review, which could each take as long again.
