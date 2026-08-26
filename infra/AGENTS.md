# infra/AGENTS.md

Terraform for AWS. Read [`../AGENTS.md`](../AGENTS.md) first for repo-wide rules.

> **The Terraform in this directory is superseded and has not been replaced yet.** It provisions a
> VPC, an EC2 instance and a security group. The high-level design
> ([`../design/boomerang-high-level-design.md`](../design/boomerang-high-level-design.md) §6.1)
> puts the service on Lambda outside any VPC, which uses none of that. Read "Target state" below
> before writing anything here; read "Legacy scaffold" only if you need to run what exists today.

## Scope

The IAM role, the Lambda function and its Function URL, the Parameter Store entries holding USPS
credentials, and the CloudWatch log group and alarms. That's the whole remit — this workspace does
not manage DNS, certificates, a load balancer, or CI.

## Target state

Per §8.3 of the high-level design:

| Resource | Purpose | Sizing |
|---|---|---|
| Lambda function | The API | 1024 MB, 60 s timeout, ARM, `reserved_concurrent_executions = 5` |
| Lambda Function URL | Public HTTPS with a managed certificate | Auth type `NONE`, CORS restricted to **exactly one** `chrome-extension://` origin — the dashboard is not on the allowlist and has no call to make |
| IAM execution role | Bedrock invoke, Parameter Store read, KMS decrypt, log write | Least privilege, path-scoped |
| SSM parameters | USPS client ID and secret | Two `SecureString` values, AWS-managed key |
| CloudWatch log group | Structured logs | **30-day retention, set explicitly.** An unset log group retains forever |
| Bedrock model invocation logging | **Explicitly disabled** | Assert it off; do not leave it unconfigured |
| CloudWatch alarms | Lambda error rate, Lambda `Throttles`, USPS failure rate, Bedrock `InputTokenCount` | Four alarms, plus an AWS Budget at $20/day |

**Two environments, `dev` and `prod`, sharing nothing.** Separate Function URLs, separate log
groups, separate CORS origins (they are separate extension IDs — one pinned key each), and SSM
paths `/boomerang/dev/*` and `/boomerang/prod/*` with the execution role scoped so `dev` cannot
read `prod`. See §8.2 of the high-level design.

**Do not enable Bedrock model invocation logging.** It is off by default and must stay off. With it
on, Bedrock writes full request bodies to S3 or CloudWatch — and the request body on the ingest path
is the user's order-page DOM. That single setting falsifies the design's "no user data at rest"
claim and NFR-6.1's logging ban without any application code changing. Terraform asserts it off so
the state shows up in a diff.

**The release key is not the runtime's business.** Each environment's pinned extension private key
lives at `/boomerang/release/<env>/extension-key` as a `SecureString`, readable by the release role
and **not** by the Lambda execution role. Same rule as the USPS credentials: written by hand,
Terraform grants access and never holds the value, because state is plaintext and retained.

**No VPC.** This is deliberate and is the decision most likely to be "helpfully" reversed. There is
no database and nothing private to reach — Bedrock, USPS and Parameter Store are all public or
AWS-service endpoints. Putting the function in a VPC would require a NAT Gateway (~$32/month plus
data) purely to reach USPS, protecting nothing. If you think the function needs a VPC, re-read
§6.1 before opening the editor.

**Auth type `NONE` on the Function URL is also deliberate.** A browser extension cannot sign
SigV4, so `AWS_IAM` is unavailable, and any secret shipped inside the extension bundle is readable
by anyone who unzips it. Abuse is contained by a CORS origin allowlist, a payload ceiling, a
bounded `max_tokens` and a short timeout — and, as the only actual ceiling, **reserved
concurrency**. See §6.2.

Two containments that sound right are not available here, and both were removed from the design
after being written down:

- **AWS WAF does not attach to Lambda Function URLs.** Its supported targets are CloudFront, ALB,
  API Gateway, AppSync and Cognito. Fronting the function with CloudFront just to get WAF is a
  different architecture, not a config change.
- **Per-source rate limiting needs shared state**, and this design deliberately has no datastore.
  A per-instance counter on a function that scales horizontally counts nothing.

**`reserved_concurrent_executions` is the spend ceiling, and it is not optional.** This is an
unauthenticated endpoint that invokes a paid model; concurrency × timeout × `max_tokens` is the
arithmetic that bounds the worst case. Note also that **there is no real-time "Bedrock spend"
metric** to alarm on — alarm on Bedrock `InputTokenCount` to catch the shape of a spike, and use an
AWS Budget for the daily dollar figure. An earlier draft specified a "Bedrock spend alarm"; it
wasn't buildable.

## Phase

**Not on the PoC critical path.** `docker compose up` covers local development completely, and the
PoC demo runs on a laptop. Infra becomes real when someone outside the team needs to reach the
service — which, notably, is *not* required for Chrome Web Store review of the extension.

Before anyone applies for real: **state is local.** Move to an S3 backend before a second person
applies, or you will corrupt each other's state. The commented block in `main.tf` has the shape:
`backend "s3" { bucket = … key = "boomerang/terraform.tfstate" region = … use_lockfile = true }`

## Commands

```bash
terraform init
terraform plan
terraform apply
```

Terraform ≥ 1.9, AWS provider ~> 6.0.

## Rules specific to this workspace

- **Secrets never enter Terraform state.** USPS credentials are written once by hand as
  `SecureString` parameters; Terraform grants read access and stores no value. State is a plaintext
  file retained across every historical version — treat anything you put in it as published.
- **Bedrock and Parameter Store access come from the execution role.** Never put
  `AWS_ACCESS_KEY_ID` in a `tfvars` file, a function environment variable, or an image. The
  commented entries in `server/.env.example` are local-development only.
- **Don't raise `reserved_concurrent_executions` to clear a throttle, and don't set it to zero.**
  Zero disables the function entirely; raising it raises the worst-case bill on an endpoint that
  anyone on the internet can call. A throttle at PoC scale is the control working.
- **Region must be one where the Bedrock model is available.** `var.region` feeds both the provider
  and the server's `AWS_REGION`; changing it without checking model availability breaks inference
  at runtime, not at plan time.
- **Everything is tagged via `default_tags`** (`Project`, `ManagedBy`). Don't hand-tag resources —
  add to the provider block instead.
- **`terraform.tfvars` is gitignored; `terraform.tfvars.example` is not.** Keep the example in sync
  when you add a variable, or the next person's `plan` fails on a missing input.

## Legacy scaffold

Everything below describes the VPC and EC2 configuration currently in `main.tf`, which the design
replaces. It is recorded so that anyone running the existing code today does so safely, and so the
reasoning isn't lost if the compute decision is ever revisited.

- **Don't "fix" the `allowed_cidr` validation.** It refuses `0.0.0.0/0` deliberately — the instance
  runs the service that holds every credential in the system. If you need public access, put an ALB
  in front; don't widen the security group. `allowed_cidr` has no default, on purpose: it must be a
  real IP, set in `terraform.tfvars`.
- **Two AZs is a floor, not a preference.** Load balancers and most managed services refuse to
  launch in one. Don't collapse the subnet count to save a few cents.
- **`terraform destroy` takes the EC2 instance and anything on it.** Nothing persists server-side
  under the current design, so this stays cheap.
- **Changing `instance_type` replaces the instance.** Harmless while the server is stateless.

When the Lambda resources land, delete this section along with the VPC, EC2, security group and the
`vpc_cidr`, `instance_type` and `allowed_cidr` variables.

## Gotchas

- **The healthcheck in `docker-compose.yml` and anything you'd put in AWS are different things.**
  Compose gates client startup on server health locally; nothing in Terraform reads it.
- **Cold starts are accepted, not solved.** Provisioned concurrency is explicitly deferred (§10);
  don't add it before measurement says it's needed.
