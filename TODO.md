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

**Challenges and solutions**:

1. **Cloudflare provider**: Network-monitor terraform currently only has the AWS provider. Need to add `cloudflare/cloudflare` provider. The other repos get the API token and zone ID from `terraform_remote_state` referencing `tf-cloudflare.tfstate` in bucket `mdekort-tfstate-075673041815`. We can't access that bucket from `844347863910`.
   - **Solution**: Add `cloudflare_api_token` as a sensitive terraform variable. Pass it via `TF_VAR_cloudflare_api_token` GitHub Actions secret. For the zone ID, hardcode it or pass as a variable (it's not sensitive).
   - Need to check: does the existing Cloudflare API token have permissions for the `mdekort.nl` zone, or do we need a new scoped token?

2. **us-east-1 provider**: ACM certs for CloudFront must be in `us-east-1`. Need a second AWS provider with alias `useast1` (same pattern as startpage/example repos).

3. **CloudFront public key**: The `get-cookies` terraform in `075673041815` exports `public_key_id`. We can't read that remote state. Options:
   - **Option A**: Use `aws_cloudfront_public_key` data source to look it up by name (if CloudFront public keys are global/accessible cross-account — need to verify)
   - **Option B**: Hardcode the public key ID as a variable (get it from `get-cookies` terraform output)
   - **Option C**: The public key itself is in `get-cookies` terraform — we could create a duplicate public key in `844347863910` and a separate key group. But then `get-cookies` would need to sign for both key IDs... probably not worth it.
   - **Best bet**: Option B — just hardcode/variable it. It rarely changes.

4. **get-cookies `ALLOWED_ORIGINS`**: Need to add `https://network-monitor.mdekort.nl` to the comma-separated list in `get-cookies/terraform/terraform.tfvars`. This is a change in the `get-cookies` repo (separate repo, `075673041815` account).

5. **get-cookies Cognito `callback_urls`**: Need to add `https://network-monitor.mdekort.nl/callback.html` and `https://network-monitor.mdekort.nl` to the Cognito user pool client in `get-cookies/terraform/cognito.tf`.

6. **Access logs bucket**: The other repos log to `mdekort.accesslogs` in `075673041815`. We can either skip logging, create a logs bucket in `844347863910`, or skip it for now and add later.

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

**Implementation order**:
1. Get Cloudflare API token + zone ID sorted (variable/secret)
2. Get `get-cookies` public key ID (hardcode or variable)
3. Add Cloudflare + us-east-1 providers to network-monitor terraform
4. Create `terraform/cloudfront.tf` — distribution, OAI, key group
5. Create `terraform/acm.tf` — cert + DNS validation
6. Create `terraform/dns.tf` — CNAME record
7. Update `terraform/s3.tf` — private bucket + OAI policy (remove public access)
8. Create UI auth files: `callback.html`, `assets/js/callback.js`, `error-pages/403.html`
9. Update `get-cookies` repo: add origin + callback URL (separate commit/repo)
10. `terraform apply` + deploy UI files
11. Update `deploy-ui.yml` workflow if needed (bucket name won't change, but verify)
12. Update output for UI URL (CloudFront domain → custom domain)

### Grafana Dashboards
`examples/grafana-dashboards/` has `network-overview.json` but deferred — Infinity plugin deemed unnecessary. Dashboard JSON kept for reference.

### Shared Lambda Libraries
README mentions `lambdas/shared/` with `dynamodb.py`, `sns.py`, `models.py`. Currently each Lambda has inline boto3 code. Optional refactor.

### Tests
`tests/unit/` and `tests/integration/` are empty. Unit tests exist co-located in each Lambda dir. Central test dirs are unused.
