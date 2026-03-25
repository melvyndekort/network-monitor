# TODO - Network Monitor

## What's Done ✅

- **Terraform**: DynamoDB tables, SNS/SQS (with DLQs, subscriptions, queue policies), Lambda functions, IAM roles, provider/backend config
- **Terraform: API Gateway** (deployed 2026-03-15)
  - HTTP API v2 at `https://ys7ivwcdqf.execute-api.eu-west-1.amazonaws.com`
  - IAM auth (SigV4) on all routes — unsigned requests get 403
  - Routes: `GET /devices`, `GET /devices/{mac}`, `PUT /devices/{mac}`, `DELETE /devices/{mac}`, `GET /devices/{mac}/history`, `GET /stats`, `GET /stats/vlan/{vlan_id}`
  - Lambda proxy integration with payload format 2.0
  - Tested: unsigned → 403, signed → 200 with `{"devices": []}`
- **Lambda code**: All 4 handlers implemented with unit tests (event-router, send-notifications, enrich-metadata, api-handler)
- **CI/CD**: Reusable deploy-lambda workflow, per-Lambda trigger workflows, Terraform plan/apply workflow
- **IAM fix** (deployed 2026-03-15): event-router was missing DynamoDB permissions for `devices` and `deduplication` tables (only had `device_events`). Fixed and verified with end-to-end test.
- **End-to-end pipeline test** (2026-03-15): Sent manual `device_discovered` event to SQS → all Lambdas fired successfully. Event-router stored event + created device, enrich-metadata looked up manufacturer, send-notifications attempted Apprise (see known issue below).
- **Presence model rewrite** (2026-03-23): Replaced `track-presence` Lambda and state machine with TTL-based `online_until` field. Status computed at read time by API handler. Removed track-presence Lambda, IAM role, SQS queue, SNS topic, CI/CD workflow, and `state-index` GSI.
- **Vector fix** (2026-03-23): `parse_collector` was failing on Python log lines from data-collector stderr. Added `filter_json` transform to drop non-JSON lines before parsing.
- **DHCP lease discovery** (2026-03-23): Data collector now emits events for devices with active DHCP leases not seen in ARP table, catching transient devices that connect briefly between poll cycles.
- **Apprise notifications** (2026-03-23): Fixed Apprise connectivity — exposed via Cloudflare Tunnel with Zero Trust service token auth. CF Access credentials stored in SSM Parameter Store. Uses stateful config key `/notify/apprise` with `homelab` tag.
- **Event batching** (2026-03-23): Data collector emits one batch message per poll instead of one per device. Poll interval increased from 30s to 60s. Reduces SQS messages from ~5.7M/month to ~43K/month.
- **Device auto-expiry** (2026-03-23): Devices automatically deleted after 14 days of inactivity via DynamoDB TTL. Re-discovered as new devices when they return.
- **Vector fixes** (2026-03-23): Added `filter_json` transform to drop non-JSON log lines. Removed `dedupe` transform that was permanently suppressing events.

---

## What's Left

### ~~Terraform: FIFO Queue DLQ~~
~~The `device_events` FIFO queue has a DLQ defined (`device_events_dlq`) but no `redrive_policy` attached to the main queue. The fan-out queues (notifier, metadata-enricher) all have redrive policies — this one was missed.~~ ✅ Fixed

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
- `docs/event-types.md` — Event schema, types, presence model, routing
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

**Cross-account state sharing**:

Network-monitor runs in account `844347863910`. The existing repos (`example.melvyn.dev`, `startpage`) that use CloudFront + signed cookies all run in `075673041815` and solve their dependencies via `terraform_remote_state` — reading from `tf-cloudflare.tfstate` (for Cloudflare API token + zone ID) and `get-cookies.tfstate` (for CloudFront public key ID).

✅ **Solved** (2026-03-23): Added org-wide `s3:GetObject` policy to the `account-bootstrap` module in `tf-aws`. All tfstate buckets (`mdekort-tfstate-*`) now allow read access from any principal in the organization (`o-l6ev5lx5yj`). Applied to management account. No KMS needed (buckets use SSE-S3/AES256).

Network-monitor can now use `terraform_remote_state` to read from `mdekort-tfstate-075673041815`, same pattern as the other repos.

**Values consumed via `terraform_remote_state`**:

| Value | Source state file | Output key | Used for |
|---|---|---|---|
| Cloudflare API token | `tf-cloudflare.tfstate` | `api_token_network_monitor` | Creating DNS records in `mdekort.nl` zone |
| `mdekort.nl` zone ID | `tf-cloudflare.tfstate` | `mdekort_zone_id` | Targeting the correct Cloudflare zone |
| CloudFront public key ID | `get-cookies.tfstate` | `public_key_id` | `aws_cloudfront_key_group` for signed cookie validation |

---

**Other challenges**:

1. **us-east-1 provider**: ACM certs for CloudFront must be in `us-east-1`. Need a second AWS provider with alias `useast1` (same pattern as startpage/example repos).

2. **Access logs bucket**: The other repos log CloudFront access logs to `mdekort.accesslogs` in `075673041815`. Options: skip logging for now, or create a logs bucket in `844347863910`. Recommendation: skip for now, add later if needed.

---

**Required changes in other repos**:

1. **`tf-cloudflare` repo** (`075673041815`):
   - Add `cloudflare_api_token.network_monitor` in `api_tokens.tf` — DNS Write on `mdekort.nl` zone (same pattern as `cloudflare_api_token.cognito`)
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

**Cognito client ID**: `3s2qppa564nr44e2igdkb40qq7` (shared across startpage, example.melvyn.dev — same `get-cookies` Lambda)

**Implementation order**:

**Phase 1 — Prerequisites (other repos)**:
1. ~~`tf-cloudflare`: Create `cloudflare_api_token.network_monitor` + output, `terraform apply`~~ ✅ Done (2026-03-23)
2. ~~`tf-aws`: Org-wide `s3:GetObject` on tfstate buckets via `account-bootstrap` module, `terraform apply`~~ ✅ Done (2026-03-23)
3. ~~`get-cookies`: Add origin + callback URL, `terraform apply`~~ ✅ Done (2026-03-23)

**Phase 2 — Terraform (network-monitor)**:
4. ~~Add `terraform_remote_state` data sources for `tf-cloudflare` and `get-cookies`~~ ✅ Done (2026-03-23)
5. ~~Update `providers.tf`: Add `cloudflare/cloudflare` provider + `aws.useast1` alias~~ ✅ Done (2026-03-23)
6. ~~Create `terraform/acm.tf` — cert + Cloudflare DNS validation~~ ✅ Done (2026-03-23)
7. ~~Create `terraform/dns.tf` — CNAME record~~ ✅ Done (2026-03-23)
8. ~~Create `terraform/cloudfront.tf` — distribution, OAI, key group~~ ✅ Done (2026-03-23)
9. ~~Update `terraform/s3.tf` — private bucket + OAI policy (remove public access)~~ ✅ Done (2026-03-23)
10. ~~Update `terraform/outputs.tf` — add CloudFront domain / custom domain URL~~ ✅ Done (2026-03-23)

**Phase 3 — UI auth files**:
11. ~~Create `ui/callback.html`~~ ✅ Done (2026-03-23)
12. ~~Create `ui/assets/js/callback.js`~~ ✅ Done (2026-03-23)
13. ~~Create `ui/error-pages/403.html`~~ ✅ Done (2026-03-23)
14. ~~Deploy UI files to S3~~ ✅ Done (2026-03-23)

**Cross-account key ID note**: CloudFront public keys are per-account. The `get-cookies` Lambda signs cookies with the key ID from `075673041815`, but the distribution in `844347863910` has its own key ID for the same key material. `callback.js` overrides the `Key-Pair-Id` cookie with the local account's key ID (`K3MOQECPWQIP8H`). The signature still validates because the underlying RSA key pair is identical.

**Live at**: `https://network-monitor.mdekort.nl`

### ~~Device Name Editing via UI~~ ✅ Done (2026-03-23)

**Goal**: Allow editing device names through the web UI.

**What's done**:
1. ~~Removed API Gateway, replaced with Lambda function URL~~ ✅
2. ~~Added CloudFront OAC for Lambda function URL (SigV4 signing)~~ ✅
3. ~~Added `/api/*` ordered cache behavior in CloudFront~~ ✅
4. ~~Updated `api_handler` Lambda to strip `/api` prefix from paths~~ ✅
5. ~~Changed UI API base URL to `/api` (relative path, same domain)~~ ✅
6. ~~Made name column click-to-edit inline with PUT on save~~ ✅

**Root cause of OAC 403** (resolved 2026-03-23): Two issues:
1. Missing `lambda:InvokeFunction` permission — only had `lambda:InvokeFunctionUrl`. AWS requires both permissions for OAC to work.
2. Missing `origin_request_policy_id` on the `/api/*` cache behavior — needed `AllViewerExceptHostHeader` to forward headers properly for SigV4 signing.

After fixing both, re-added `trusted_key_groups` to the `/api/*` behavior for signed cookie auth. Verified: direct Lambda URL → 403, CloudFront without cookies → 403, CloudFront with cookies → 200.

### ~~Move new-device detection from data collector to event-router Lambda~~ ✅ Done (2026-03-25)

**Problem**: The data collector was deciding whether a device is "new" by tracking `known_macs` in memory, which reset on container restart causing false notification floods.

**Fix**: Data collector is now a pure sensor — polls MikroTik, sends `device_activity` for every device, every poll. No state, no decisions. The event-router Lambda checks DynamoDB to determine if a device is new (not found → create + route to `TOPIC_DISCOVERED`) or existing (found → update `last_seen`/`online_until` + route to `TOPIC_ACTIVITY`).

### ~~OpenWrt AP polling for wireless presence~~ ✅ Done (2026-03-25)

**Problem**: Using ARP + DHCP for presence was unreliable — DHCP leases persist after a device disconnects (bound for up to 1 hour), and ARP entries go stale within 30 seconds (shorter than the 60s poll interval). This caused devices to appear online when they were physically gone.

**Fix**: Data collector now polls all 4 OpenWrt APs via ubus HTTP JSON-RPC (`hostapd.*.get_clients`) for associated wireless clients. This is the primary presence signal — AP associations drop immediately when a device disconnects. ARP is used for wired devices only. DHCP is used solely for IP/hostname enrichment, never as a presence signal.

**AP setup**: Created `netmon` rpcd user on all 4 APs with read-only ACL for `hostapd.*.get_clients`. New env vars: `AP_HOSTS`, `AP_USER`, `AP_PASSWORD`.

### Grafana Dashboards`examples/grafana-dashboards/` has `network-overview.json` but deferred — Infinity plugin deemed unnecessary. Dashboard JSON kept for reference.

### Shared Lambda Libraries
README mentions `lambdas/shared/` with `dynamodb.py`, `sns.py`, `models.py`. Currently each Lambda has inline boto3 code. Optional refactor.

### ~~Tests~~ ✅ Done (2026-03-23)
Removed empty `tests/unit/` and `tests/integration/` dirs. Tests are co-located: each Lambda has `test_handler.py`, data-collector has `tests/`. Root `Makefile` runs all tests via `make test`.
