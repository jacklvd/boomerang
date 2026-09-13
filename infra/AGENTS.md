# infra/AGENTS.md

Terraform for AWS. Read [`../AGENTS.md`](../AGENTS.md) first for repo-wide rules.

> **Everything in this directory is legacy and superseded. Do not build from it, and do not build
> the design it used to point to.** The Terraform here provisions a VPC, an EC2 instance and a
> security group — a topology that matches neither the architecture this file used to describe nor
> the one the product has now. The production deployment topology is an **open decision, not yet
> made**. Read "Current state" below, then stop.

## Current state

The Terraform in this directory provisions a VPC, a public subnet, a security group, an EC2
instance and its IAM instance role. It predates the architecture the rest of the repo now builds
against and is kept only so that anyone who still needs to run it can do so without guessing. It is
not a candidate for the production topology and nobody should extend it.

This file used to also instruct an implementer to replace that scaffold with a specific target: a
single Lambda function behind a public, unauthenticated Function URL, with no VPC and no database.
That instruction is gone. It described a design the product has since moved past — the current
architecture requires accounts backed by Google identity, persisted orders and return summaries,
and a database-backed dashboard, none of which a no-database Lambda can serve. The design sections
that instruction cited for its reasoning have themselves been deleted, so the old text was also
pointing at nothing.

## What to do here

**Nothing, until the topology decision is made.** Don't build the old Lambda/no-VPC/no-database
design, don't extend the current VPC/EC2 scaffold, and don't invent a third option on your own
initiative. The current, accurate statement of what's settled and what isn't lives in the
deployment-posture section of the high-level design document
([`../design/boomerang-high-level-design.md`](../design/boomerang-high-level-design.md)); the
decision itself, once made, belongs in the migration-decisions record
([`../plan/boomerang-decisions.md`](../plan/boomerang-decisions.md)) and is tracked as part of the
release-readiness milestone in the milestones plan
([`../plan/boomerang-milestones.md`](../plan/boomerang-milestones.md)). A database is a hard
requirement of whatever topology is eventually chosen — any proposal without one is out of
consideration before it starts.

If you're picking up infra work and none of those documents show a resolved decision yet, the
right move is to stop and surface that, not to guess a topology and start writing Terraform for it.

## Phase

**Not on the PoC critical path.** `docker compose up` covers local development completely, and the
PoC demo runs on a laptop. Nothing here blocks product work; it only matters once someone outside
the team needs to reach a deployed service.

## Commands

If you need to operate the existing scaffold as-is (not extend it):

```bash
terraform init
terraform plan
terraform apply
```

Terraform ≥ 1.9, AWS provider ~> 6.0.

## Rules specific to this workspace

- **Secrets never enter Terraform state.** Any credential this workspace ever needs should be
  written once by hand as a `SecureString`-style parameter, with Terraform granting read access and
  never holding the value. State is a plaintext file retained across every historical version —
  treat anything you put in it as published.
- **Never put an access key in a `tfvars` file, a compute environment variable, or an image.**
  Credentials belong on an IAM role attached to whatever compute is chosen, not hardcoded. The
  commented entries in `server/.env.example` are local-development only.
- **Region must be one where the Bedrock model used by the server is available.** Whatever
  workspace eventually manages this, changing region without checking model availability breaks
  inference at runtime, not at plan time.
- **Everything is tagged via `default_tags`** (`Project`, `ManagedBy`). Don't hand-tag resources —
  add to the provider block instead.
- **`terraform.tfvars` is gitignored; `terraform.tfvars.example` is not.** Keep the example in sync
  if you touch a variable, or the next person's `plan` fails on a missing input.

## Legacy scaffold

Everything below describes the VPC and EC2 configuration currently in `main.tf`. It is not the
target topology — no target topology is selected — and is documented only so the existing code can
be run safely until it is replaced or removed as part of the deployment-topology decision.

- **Don't "fix" the `allowed_cidr` validation.** It refuses `0.0.0.0/0` deliberately — the instance
  runs the service that holds every credential in the system. `allowed_cidr` has no default, on
  purpose: it must be a real IP, set in `terraform.tfvars`.
- **Two AZs is a floor, not a preference.** Load balancers and most managed services refuse to
  launch in one. Don't collapse the subnet count to save a few cents.
- **`terraform destroy` takes the EC2 instance and anything on it.** Nothing persists server-side
  under this scaffold, so this stays cheap.
- **Changing `instance_type` replaces the instance.** Harmless while the server is stateless.

## Gotchas

- **The healthcheck in `docker-compose.yml` and anything you'd put in AWS are different things.**
  Compose gates client startup on server health locally; nothing in Terraform reads it.
