---
id: "I.1"
batch: "deployment"
batch_dir: "deployment"
order: 64
track: null
track_heading: null
track_scope: null
title: "Replace the Terraform with the Lambda topology"
kind: "implementation"
package: "infra/"
package_raw: "`infra/`"
prerequisites: ["6.5", "1.4"]
prerequisites_raw: "Task 6.5 (a deployable handler), Task 1.4 (the pinned extension IDs)"
conflicts_with: []
conflicts_with_raw: "None"
parallel_with: []
parallel_with_raw: "All of Batches 7–10"
requirements_covered: ["NFR-6.5", "NFR-6.6", "NFR-6.7"]
requirements_covered_raw: "NFR-6.5, NFR-6.6, NFR-6.7"
sections_covered: []
status: "not_started"
---
### Task I.1: Replace the Terraform with the Lambda topology

**Prerequisites:** Task 6.5 (a deployable handler), Task 1.4 (the pinned extension IDs)
**Conflicts with:** None
**Parallel with:** All of Batches 7–10
**Package:** `infra/`

**Objective:** Zero of this plan's original 79 tasks touched `infra/`, while NFR-6.6 and NFR-6.7 had
traceability rows pointing at application tasks that cannot satisfy them — no application task can
create a CloudWatch alarm. Close that.

**Instructions:**
1. **Delete** the VPC, internet gateway, subnets, EC2 instance and security group from
   `infra/main.tf`, along with the `vpc_cidr`, `instance_type` and `allowed_cidr` variables and any
   output that referenced them. `infra/AGENTS.md` explicitly instructs this deletion; do not leave
   the old resources beside the new ones "in case".
2. Provision, per the resource table in `infra/AGENTS.md`:
   - the **Lambda function** — 1024 MB, 60 s timeout, ARM, and
     `reserved_concurrent_executions = 5`;
   - the **Function URL** with auth type `NONE` and CORS restricted to **exactly one**
     `chrome-extension://` origin — the extension ID Task 1.4 derived for this environment;
   - the **IAM execution role**: Bedrock invoke, Parameter Store read, KMS decrypt, log write, least
     privilege and path-scoped, and **without** read access to
     `/boomerang/release/<env>/extension-key`;
   - **SSM `SecureString`** parameters for the USPS client ID and secret — Terraform grants access
     and never holds the value, because state is plaintext and retained;
   - the **CloudWatch log group** with **30-day retention set explicitly** — an unset log group
     retains forever;
   - **Bedrock model invocation logging explicitly disabled**, asserted off rather than left
     unconfigured. With it on, Bedrock writes full request bodies to S3 or CloudWatch, and the
     request body on the ingest path is the user's order-page DOM — that one setting falsifies
     NFR-6.1 without any application code changing;
   - **alarms** on Lambda error rate, Lambda `Throttles`, USPS failure rate and Bedrock
     `InputTokenCount`, plus an **AWS Budget** at $20/day.
3. Two environments, `dev` and `prod`, sharing nothing: separate Function URLs, log groups, CORS
   origins and SSM paths, with the execution role scoped so `dev` cannot read `prod`.
4. **Delete the "Legacy scaffold" section of `infra/AGENTS.md`** in this same change — the section
   ends with the instruction to do so once these resources land. Leaving it turns an accurate
   document into a misleading one the moment this task completes.
5. Keep `terraform.tfvars.example` in sync with every variable added or removed.
6. Reference: high-level design §6.1, §6.2, §8.2, §8.3, §8.4; `infra/AGENTS.md`; requirements
   NFR-6.5, NFR-6.6, NFR-6.7; decisions D7, D8.

**Verification:**
- `cd infra && terraform init && terraform validate && terraform plan` — plans cleanly with no VPC,
  EC2 or security-group resource in the plan output.
- `grep -ri "aws_vpc\|aws_instance\|aws_security_group" infra/` returns nothing.
- The planned Function URL CORS block names exactly one origin, and it matches the extension ID in
  `extension/AGENTS.md`.
- `terraform plan` shows Bedrock invocation logging disabled and log-group retention set to 30 days.

**Requirements covered:** NFR-6.5, NFR-6.6, NFR-6.7
