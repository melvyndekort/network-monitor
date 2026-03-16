# TODO - Network Monitor

## What's Done ✅

- **Terraform**: DynamoDB tables, SNS/SQS (with DLQs, subscriptions, queue policies), Lambda functions, IAM roles, provider/backend config
- **Terraform: API Gateway** (deployed 2026-03-15)
  - HTTP API v2 at `https://ys7ivwcdqf.execute-api.eu-west-1.amazonaws.com`
  - IAM auth (SigV4) on all routes — unsigned requests get 403
  - Routes: `GET /devices`, `GET /devices/{mac}`, `PUT /devices/{mac}`, `DELETE /devices/{mac}`, `GET /devices/{mac}/history`, `GET /stats`, `GET /stats/vlan/{vlan_id}`
  - Lambda proxy integration with payload format 2.0
  - Tested: unsigned → 403, signed → 200 with `{"devices": []}`
- **Lambda code**: All 5 handlers implemented with unit tests (event-router, track-presence, send-notifications, enrich-metadata, api-handler)
- **CI/CD**: Reusable deploy-lambda workflow, per-Lambda trigger workflows, Terraform plan/apply workflow
- **IAM fix** (deployed 2026-03-15): event-router was missing DynamoDB permissions for `devices` and `deduplication` tables (only had `device_events`). Fixed and verified with end-to-end test.
- **End-to-end pipeline test** (2026-03-15): Sent manual `device_discovered` event to SQS → all 5 Lambdas fired successfully. Event-router stored event + created device, track-presence set state to online, enrich-metadata looked up manufacturer, send-notifications attempted Apprise (see known issue below).

---

## What's Left

### ~~Terraform: FIFO Queue DLQ~~
~~The `device_events` FIFO queue has a DLQ defined (`device_events_dlq`) but no `redrive_policy` attached to the main queue. The fan-out queues (presence-tracker, notifier, metadata-enricher) all have redrive policies — this one was missed.~~ ✅ Fixed

### ~~Apprise URL~~
~~The `send-notifications` Lambda has `APPRISE_URL` set to `apprise.internal.mdekort.nl`, which is not resolvable from AWS Lambda. Needs to be changed to the public Cloudflare Tunnel URL (`apprise.mdekort.nl` or similar).~~ ✅ Fixed — changed to `https://apprise.mdekort.nl`

### ~~Terraform: S3 Bucket for UI~~ ✅ Done
S3 bucket with static website hosting and public read policy.

### ~~Data Collector~~ ✅ Done
Implemented as `data_collector` Python package with uv/hatchling. 24 tests, 86% coverage.

### ~~Vector Config Changes (on compute-1)~~ ✅ Done
Deployed new `vector.toml` with docker_logs source, DHCP transform, SQS sink, dedupe. IAM user + SOPS-encrypted credentials.

### ~~Retire router-events~~ ✅ Done
Removed container, dropped MariaDB database and user.

### ~~UI~~ ✅ Done
Bootstrap 5 dark theme dashboard at `http://network-monitor-ui-844347863910.s3-website-eu-west-1.amazonaws.com`. GET routes made public, PUT/DELETE remain IAM-protected. CORS enabled.

### ~~Documentation~~ ✅ Done
- `docs/api.md` — API reference with all endpoints
- `docs/event-types.md` — Event schema, types, state machine, routing
- `docs/grafana-setup.md` — Grafana Cloud setup with Infinity plugin

### ~~Scripts~~ ✅ Done
`scripts/deploy_ui.sh` for S3 sync. Lambda deployment handled by CI/CD.

### ~~UI Deployment Workflow~~ ✅ Done
`.github/workflows/deploy-ui.yml` — triggers on `ui/**` changes, runs `aws s3 sync --delete`. Also updated `scripts/deploy_ui.sh` to match (added `--delete`, removed hardcoded `--content-type`).

### CloudFront + Authentication for UI

**Goal**: Put the UI behind CloudFront with signed cookie authentication (same pattern as `startpage` and `example.melvyn.dev` repos), served at `https://network-monitor.mdekort.nl`.

**Auth flow** (already working for other sites):
1. Unauthenticated user hits CloudFront → gets 403 → custom error page redirects to Cognito login (`auth.mdekort.nl`)
2. Cognito authenticates → redirects to `/callback.html` with `#id_token=...` in URL fragment
3. `callback.js` calls `https://api.mdekort.nl/cookies?id_token=<token>` (the `get-cookies` Lambda in account `075673041815`)
4. `get-cookies` validates JWT, returns CloudFront signed cookies (Policy, Signature, Key-Pair-Id)
5. `callback.js` sets cookies in browser, redirects to `/`
6. CloudFront validates signed cookies via `trusted_key_groups` → serves content

**Terraform resources needed** (all in `844347863910` account):
- `aws_cloudfront_distribution` — with OAI, `trusted_key_groups` on default behavior
- `aws_cloudfront_origin_access_identity` — for S3 access
- `aws_cloudfront_key_group` — referencing the `get-cookies` public key
- `aws_acm_certificate` + `aws_acm_certificate_validation` — in `us-east-1` for `network-monitor.mdekort.nl`
- `cloudflare_dns_record` — CNAME for `network-monitor.mdekort.nl` → CloudFront domain
- `cloudflare_dns_record` — ACM DNS validation record
- Update `aws_s3_bucket_policy` — replace public access with OAI-only access
- Update `aws_s3_bucket_public_access_block` — block all public access

**Ordered cache behaviors** (public, no `trusted_key_groups` — so auth pages are accessible):
- `/error-pages/*` — 403 error page (triggers Cognito login redirect)
- `/callback.html` — receives Cognito redirect, exchanges token for cookies
- `/assets/*` — JS/CSS needed by callback and error pages

**UI files to create**:
- `ui/callback.html` — copy pattern from `example.melvyn.dev/src/callback.html`
- `ui/assets/js/callback.js` — copy from `example.melvyn.dev/src/assets/js/callback.js` (calls `api.mdekort.nl/cookies`)
- `ui/error-pages/403.html` — redirect to `https://auth.mdekort.nl/login?response_type=token&client_id=<CLIENT_ID>&redirect_uri=https%3A%2F%2Fnetwork-monitor.mdekort.nl%2Fcallback.html`

**Cognito client ID**: `3s2qppa564nr44e2igdkb40qq7` (shared across startpage, example.melvyn.dev — same `get-cookies` Lambda)

**Cross-account challenge**:

Network-monitor runs in account `844347863910`. The existing repos (`example.melvyn.dev`, `startpage`) that use CloudFront + signed cookies all run in `075673041815` and solve their dependencies via `terraform_remote_state` — reading from `tf-cloudflare.tfstate` (for Cloudflare API token + zone ID) and `get-cookies.tfstate` (for CloudFront public key ID). Network-monitor cannot access the `mdekort-tfstate-075673041815` S3 bucket.

The three values we need from `075673041815`:

| Value | Source | Used for |
|---|---|---|
| Cloudflare API token | `tf-cloudflare` output `api_token_*` (scoped per project) | Creating DNS records in `mdekort.nl` zone |
| `mdekort.nl` zone ID | `tf-cloudflare` output `mdekort_zone_id` | Targeting the correct Cloudflare zone |
| CloudFront public key ID | `get-cookies` output `public_key_id` | `aws_cloudfront_key_group` for signed cookie validation |

Below are two options for solving this. Both require the same prerequisite changes in the `get-cookies` repo (see "Required changes in other repos" below).

---

#### Option A: Pass everything as terraform variables (recommended)

Treat the three cross-account values as terraform input variables. No cross-account S3 access needed.

**How it works**:
- `cloudflare_api_token` — sensitive variable, passed via `TF_VAR_cloudflare_api_token` environment variable in CI/CD (GitHub Actions secret)
- `cloudflare_zone_id` — non-sensitive, goes in `terraform.tfvars` (zone IDs are not secret)
- `cloudfront_public_key_id` — non-sensitive, goes in `terraform.tfvars` (rarely changes)

**Cloudflare API token sourcing**: A new scoped token needs to be created in `tf-cloudflare` (in `075673041815`):
- Add `cloudflare_api_token.network_monitor` resource in `tf-cloudflare/terraform/api_tokens.tf` with DNS Write permission on `mdekort.nl` zone (same pattern as `cloudflare_api_token.startpage`)
- Add corresponding output `api_token_network_monitor` in `tf-cloudflare/terraform/output.tf`
- After `terraform apply` in `tf-cloudflare`, retrieve the token value with `terraform output -raw api_token_network_monitor`
- Store it as a GitHub Actions secret `CLOUDFLARE_API_TOKEN` in the `network-monitor` repo
- For local use: `export TF_VAR_cloudflare_api_token=<token>` or pass via `-var`

**Getting the other two values** (one-time manual lookup):
- Zone ID: `cd ~/src/melvyndekort/tf-cloudflare/terraform && terraform output mdekort_zone_id` → put in `terraform.tfvars`
- Public key ID: `cd ~/src/melvyndekort/get-cookies/terraform && terraform output public_key_id` → put in `terraform.tfvars`

**CI/CD workflow change** (`.github/workflows/terraform.yml`):
```yaml
- name: Terraform Apply
  env:
    TF_VAR_cloudflare_api_token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  run: terraform apply -auto-approve -input=false
```

**Terraform variables to add** (`variables.tf`):
```hcl
variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS Write on mdekort.nl zone"
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for mdekort.nl"
  type        = string
}

variable "cloudfront_public_key_id" {
  description = "CloudFront public key ID from get-cookies (account 075673041815)"
  type        = string
}
```

**Pros**:
- Simple — no cross-account IAM, no bucket policies, no coupling between accounts
- Works identically locally and in CI/CD
- Each value is explicit and auditable in tfvars/secrets
- No risk of accidentally exposing other state files across accounts
- Follows the principle of least privilege — network-monitor only gets what it needs

**Cons**:
- Manual step to retrieve zone ID and public key ID (but they rarely change)
- If the CloudFront public key is ever rotated in `get-cookies`, you must manually update `terraform.tfvars` here too
- The Cloudflare API token is managed outside of terraform in this repo (stored as a GitHub secret, not derived from state)
- Requires a change in `tf-cloudflare` repo to create the scoped token

---

#### Option B: Cross-account S3 bucket policy for remote state access

Grant the `844347863910` CI/CD role read access to specific state files in the `075673041815` tfstate bucket. Then use `terraform_remote_state` like the other repos do.

**How it works**:
- Add a bucket policy statement on `mdekort-tfstate-075673041815` allowing the network-monitor CI/CD role to `s3:GetObject` on specific keys
- Use `terraform_remote_state` data sources in network-monitor terraform to read `tf-cloudflare.tfstate` and `get-cookies.tfstate`
- Reference outputs directly: `data.terraform_remote_state.tf_cloudflare.outputs.api_token_network_monitor`, etc.

**Bucket policy addition** (in `075673041815`, on `mdekort-tfstate-075673041815`):
```json
{
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::844347863910:role/<network-monitor-ci-role>"
  },
  "Action": "s3:GetObject",
  "Resource": [
    "arn:aws:s3:::mdekort-tfstate-075673041815/tf-cloudflare.tfstate",
    "arn:aws:s3:::mdekort-tfstate-075673041815/get-cookies.tfstate"
  ]
}
```

**Terraform data sources** (in network-monitor):
```hcl
data "terraform_remote_state" "tf_cloudflare" {
  backend = "s3"
  config = {
    bucket = "mdekort-tfstate-075673041815"
    key    = "tf-cloudflare.tfstate"
    region = "eu-west-1"
  }
}

data "terraform_remote_state" "get_cookies" {
  backend = "s3"
  config = {
    bucket = "mdekort-tfstate-075673041815"
    key    = "get-cookies.tfstate"
    region = "eu-west-1"
  }
}
```

**Still needs a new Cloudflare API token**: Even with remote state access, `tf-cloudflare` doesn't have a `network_monitor` scoped token yet. You'd still need to create `cloudflare_api_token.network_monitor` in `tf-cloudflare` and add the output. The difference is that network-monitor terraform would read it from state instead of a variable.

**Pros**:
- Consistent with how `example.melvyn.dev` and `startpage` work — same pattern across all repos
- Automatic propagation — if the CloudFront public key is rotated in `get-cookies`, network-monitor picks it up on next `terraform apply` without manual intervention
- No GitHub secrets needed for Cloudflare token (it flows through state)

**Cons**:
- Requires modifying the tfstate bucket policy in `075673041815` — this is a sensitive change (state files contain all resource attributes, including secrets)
- The `tf-cloudflare.tfstate` contains sensitive outputs (API keys, tunnel secrets, etc.) — granting `s3:GetObject` on it means the `844347863910` role can read ALL of that state, not just the network-monitor token
- The `get-cookies.tfstate` contains the CloudFront private key (via `tls_private_key`) in its state — exposing this cross-account is a security concern
- Couples the two accounts — changes to the bucket policy or state file keys could break network-monitor
- The bucket policy is likely managed by a separate terraform config (or manually) — need to figure out where and how to add the statement
- More complex to reason about for debugging ("why can't terraform read state?" vs "what's the variable value?")

**Security note**: Terraform state files are not scoped — `s3:GetObject` on `get-cookies.tfstate` exposes the entire state including the `tls_private_key.private_key` resource which contains the CloudFront signing private key in plaintext. This is the key used to sign cookies for ALL sites (`startpage`, `example.melvyn.dev`, and network-monitor). This alone makes Option B risky unless the bucket policy is very carefully scoped and the CI/CD role in `844347863910` is tightly locked down.

---

#### Decision

**Option A is recommended.** The security implications of Option B (exposing full state files cross-account, including the CloudFront signing private key) outweigh the convenience of automatic value propagation. Option A requires one GitHub secret and two tfvars values — minimal overhead for a much cleaner security boundary.

---

**Other challenges** (apply regardless of which option is chosen):

1. **us-east-1 provider**: ACM certs for CloudFront must be in `us-east-1`. Need a second AWS provider with alias `useast1` (same pattern as startpage/example repos).

2. **Access logs bucket**: The other repos log CloudFront access logs to `mdekort.accesslogs` in `075673041815`. Options: skip logging for now, or create a logs bucket in `844347863910`. Recommendation: skip for now, add later if needed.

---

**Required changes in other repos** (regardless of option chosen):

1. **`tf-cloudflare` repo** (`075673041815`):
   - Add `cloudflare_api_token.network_monitor` in `api_tokens.tf` — scoped to DNS Write on `mdekort.nl` zone (same pattern as `cloudflare_api_token.startpage`)
   - Add `output "api_token_network_monitor"` in `output.tf`
   - `terraform apply`

2. **`get-cookies` repo** (`075673041815`):
   - Add `https://network-monitor.mdekort.nl` to `allowed_origins` in `terraform.tfvars`
   - Add `https://network-monitor.mdekort.nl/callback.html` and `https://network-monitor.mdekort.nl` to `callback_urls` in `cognito.tf`
   - `terraform apply`

**Reference files** (patterns to follow):
- `~/src/melvyndekort/example.melvyn.dev/terraform/cloudfront.tf` — simplest CloudFront example with auth
- `~/src/melvyndekort/example.melvyn.dev/terraform/s3.tf` — private bucket with OAI policy
- `~/src/melvyndekort/example.melvyn.dev/terraform/acm.tf` — ACM + Cloudflare DNS validation
- `~/src/melvyndekort/example.melvyn.dev/terraform/dns.tf` — CNAME to CloudFront
- `~/src/melvyndekort/example.melvyn.dev/src/callback.html` — callback page
- `~/src/melvyndekort/example.melvyn.dev/src/assets/js/callback.js` — token→cookie exchange
- `~/src/melvyndekort/example.melvyn.dev/src/error-pages/403.html` — login redirect

**AWS account layout**:
- `075673041815` — "root" personal account (`mdekort/Admin` profile). Hosts: Cognito, get-cookies Lambda, Cloudflare terraform state, startpage, example.melvyn.dev
- `844347863910` — network-monitor sub-account (`mdekort/network-monitor` profile). Hosts: all network-monitor infrastructure
- Cross-account access from `844347863910` → `075673041815` S3 tfstate bucket is **not** available

**Implementation order** (assuming Option A):

**Phase 1 — Prerequisites (other repos)**:
1. `tf-cloudflare`: Create `cloudflare_api_token.network_monitor` + output, `terraform apply`, retrieve token value
2. `tf-cloudflare`: Retrieve `mdekort_zone_id` via `terraform output`
3. `get-cookies`: Retrieve `public_key_id` via `terraform output`
4. `get-cookies`: Add origin + callback URL to `terraform.tfvars` and `cognito.tf`, `terraform apply`
5. `network-monitor` GitHub repo: Add `CLOUDFLARE_API_TOKEN` secret

**Phase 2 — Terraform (network-monitor)**:
6. Add variables: `cloudflare_api_token`, `cloudflare_zone_id`, `cloudfront_public_key_id` to `variables.tf`
7. Add values to `terraform.tfvars`: zone ID, public key ID
8. Update `providers.tf`: Add `cloudflare/cloudflare` provider + `aws.useast1` alias
9. Create `terraform/acm.tf` — cert + Cloudflare DNS validation
10. Create `terraform/dns.tf` — CNAME record
11. Create `terraform/cloudfront.tf` — distribution, OAI, key group
12. Update `terraform/s3.tf` — private bucket + OAI policy (remove public access)
13. Update `terraform/outputs.tf` — add CloudFront domain / custom domain URL
14. Update `.github/workflows/terraform.yml` — pass `TF_VAR_cloudflare_api_token` from secret

**Phase 3 — UI auth files**:
15. Create `ui/callback.html`
16. Create `ui/assets/js/callback.js`
17. Create `ui/error-pages/403.html`
18. Update `deploy-ui.yml` workflow if needed
19. Deploy UI files to S3

### Grafana Dashboards
`examples/grafana-dashboards/` has `network-overview.json` but deferred — Infinity plugin deemed unnecessary. Dashboard JSON kept for reference.

### Shared Lambda Libraries
README mentions `lambdas/shared/` with `dynamodb.py`, `sns.py`, `models.py`. Currently each Lambda has inline boto3 code. Optional refactor.

### Tests
`tests/unit/` and `tests/integration/` are empty. Unit tests exist co-located in each Lambda dir. Central test dirs are unused.
