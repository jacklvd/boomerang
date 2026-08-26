# infra/AGENTS.md

Terraform for AWS. Read [`../AGENTS.md`](../AGENTS.md) first for repo-wide rules.

## Scope

A VPC across two AZs and an EC2 instance to run the FastAPI service, plus the IAM role that gives
it Bedrock access. That's the whole remit — this workspace does not manage DNS, certificates, a
load balancer, or CI.

## Phase

**Scaffolded, never applied. Not on the PoC critical path.**

`docker compose up` covers local development completely, and the PoC demo runs on a laptop. Infra
becomes real when someone outside the team needs to reach the service — which, notably, is *not*
required for Chrome Web Store review of the extension.

Two things must be fixed before anyone applies this for real:

1. **State is local.** Move to an S3 backend before a second person applies, or you will corrupt
   each other's state. The commented block in `main.tf` has the shape:
   `backend "s3" { bucket = … key = "boomerang/terraform.tfstate" region = … use_lockfile = true }`
2. **`allowed_cidr` has no default, on purpose.** It must be a real IP.

## Commands

```bash
cp terraform.tfvars.example terraform.tfvars   # then set allowed_cidr
terraform init
terraform plan
terraform apply
```

Terraform ≥ 1.9, AWS provider ~> 6.0.

## Rules specific to this workspace

- **Don't "fix" the `allowed_cidr` validation.** It refuses `0.0.0.0/0` deliberately — the
  instance runs the service that holds every credential in the system. If you need public access,
  put an ALB in front; don't widen the security group.
- **Two AZs is a floor, not a preference.** Load balancers and most managed services refuse to
  launch in one. Don't collapse the subnet count to save a few cents.
- **Bedrock credentials come from the instance role in production.** Never put
  `AWS_ACCESS_KEY_ID` in user data, an AMI, or a `tfvars` file. The commented entries in
  `server/.env.example` are local-development only.
- **Region must be one where the Bedrock model is available.** `var.region` feeds both the
  provider and the server's `AWS_REGION`; changing it without checking model availability breaks
  inference at runtime, not at plan time.
- **Everything is tagged via `default_tags`** (`Project`, `ManagedBy`). Don't hand-tag resources
  — add to the provider block instead.
- **`terraform.tfvars` is gitignored; `terraform.tfvars.example` is not.** Keep the example in
  sync when you add a variable, or the next person's `plan` fails on a missing input.

## Gotchas

- **`terraform destroy` takes the EC2 instance and anything on it.** There's no datastore yet, so
  today that's cheap — revisit this note the moment one exists.
- **Changing `instance_type` replaces the instance.** Fine now, not fine once it holds pickup
  confirmations and ETags.
- **The healthcheck in `docker-compose.yml` and the one you'd put in a target group are
  different things.** Compose gates client startup on server health locally; nothing in Terraform
  reads it.
