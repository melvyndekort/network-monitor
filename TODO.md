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

### Terraform: S3 Bucket for UI
Need `s3.tf` with:
- S3 bucket for static HTMX UI
- Static website hosting config
- Bucket policy for public read (or CloudFront)

### ~~Data Collector~~ ✅ Done
Implemented as `data_collector` Python package with uv/hatchling:
- `mikrotik.py` — librouteros wrapper for ARP + DHCP queries with auto-reconnect
- `models.py` — Event schema matching event-router Lambda, VLAN detection from IP prefix
- `main.py` — Poll loop (default 30s), outputs JSON to stdout
- 24 tests, 86% coverage, pylint 9.91/10
- Multi-stage Dockerfile, connects to MikroTik at 10.204.50.1 (management VLAN)

### ~~Vector Config Changes (on compute-1)~~ ✅ Done
Deployed new `vector.toml` with:
- `docker_logs` source (for data-collector container stdout)
- `dhcp_to_event` transform (converts DHCP syslog to event schema)
- `parse_collector` transform (parses data-collector JSON)
- `dedupe` transform (30s window, keyed on mac + event_type)
- `aws_sqs` sink (sends to FIFO queue, message_group_id = mac)
- Loki sink preserved, password moved to env var
- Docker socket mount + SELinux `label=disable` in compose
- IAM user `network-monitor-vector` with `sqs:SendMessage` + `sqs:GetQueueAttributes`
- AWS credentials encrypted via SOPS into `compute-1-monitoring.enc.env`

#### Current config
- Source: `syslog` on UDP 514 (receives RouterOS logs)
- Transform: `fix_timestamp` (sets timestamp to now())
- Transform: `dhcp_filter` (filters for appname containing "dhcp")
- Sink: `router_events` — HTTP POST to `http://10.204.10.21:13959/api/events` (old app, being replaced)
- Sink: `loki` — sends all syslog to Grafana Cloud Loki

#### Changes needed
1. **Remove** the `router_events` HTTP sink (replaced by this project)
2. **Add** a `docker_logs` source to capture data collector container stdout
3. **Add** a transform to parse data collector JSON output
4. **Add** a transform to convert DHCP syslog events into our normalized event schema
5. **Add** a dedupe transform (30s window, keyed on mac + event_type)
6. **Add** an `aws_sqs` sink targeting `https://sqs.eu-west-1.amazonaws.com/844347863910/network-monitor-device-events.fifo`, using `message_group_id = "{{ mac }}"`
7. **Keep** the `loki` sink as-is
8. **Add** AWS credentials — Vector container currently has none (see Secrets section below)

#### Docker-compose changes (homelab repo)
The Vector service in `compute-1/monitoring.yml` will need:
- `env_file` referencing the secrets file (see Secrets section below)
- Docker socket volume mount if using `docker_logs` source — Vector currently has no socket mount
- The config file is already bind-mounted read-only from `/var/srv/apps/vector/vector.toml`

**⚠️ Do NOT apply Vector changes until AWS infrastructure is fully deployed and tested.**

#### Secrets for Vector AWS credentials
The homelab uses SOPS + age encrypted env files for secrets. The flow is:

1. Encrypted secrets live in Git at `homelab/secrets/{node}-{stack}.enc.env`
2. On push, GitHub Actions triggers the `secrets-sync` container on compute-1
3. secrets-sync clones the repo, decrypts all `*.enc.env` files, writes plaintext to `/var/srv/secrets/{node}-{stack}.env` (root-only, 600 perms)
4. Compose services reference secrets via `env_file: /var/srv/secrets/{node}-{stack}.env`
5. Portainer reads these files from compute-1's filesystem when deploying stacks

**What needs to happen:**

1. Create a dedicated IAM user (or use existing Terraform) with only `sqs:SendMessage` on the FIFO queue
2. Create a new plaintext env file with the AWS credentials:
   ```
   AWS_ACCESS_KEY_ID=<key>
   AWS_SECRET_ACCESS_KEY=<secret>
   AWS_REGION=eu-west-1
   SQS_QUEUE_URL=https://sqs.eu-west-1.amazonaws.com/844347863910/network-monitor-device-events.fifo
   ```
3. Encrypt it into the homelab repo:
   ```bash
   cd ~/src/melvyndekort/homelab
   make secrets-encrypt INPUT=plaintext.env FILE=compute-1-monitoring.enc.env
   ```
   Note: Vector is in the `monitoring.yml` stack, so either:
   - Add the new vars to the existing `compute-1-monitoring.enc.env`, or
   - Create a separate `compute-1-network-monitor.enc.env` and add a second `env_file` to the Vector service
4. Add `env_file` to the Vector service in `compute-1/monitoring.yml`:
   ```yaml
   vector:
     env_file:
       - /var/srv/secrets/compute-1-monitoring.env
   ```
5. Commit and push — secrets-sync auto-decrypts, Portainer webhook redeploys the monitoring stack

### Retire router-events
Once the network monitor is live:
- Remove `router-events` container from `~/src/melvyndekort/homelab/compute-1/infrastructure.yml`
- Remove its MariaDB database (`router_events`)
- Update Cloudflare tunnel config if `router-events.mdekort.nl` is exposed
- Update Traefik labels

### UI
All files under `ui/` are empty:
- `index.html` — empty
- `devices.html` — missing
- `styles.css` — missing

### Documentation
- `docs/api.md` — empty
- `docs/event-types.md` — empty
- `docs/grafana-setup.md` — missing

### Scripts
`scripts/` directory is empty. README references:
- `deploy_lambdas.sh`
- `package_lambdas.sh`

(May not be needed since CI/CD handles deployment via GitHub Actions)

### Grafana Dashboards
`examples/grafana-dashboards/` is empty. Need dashboard JSON for:
- Network overview
- Device details
- VLAN activity

### Shared Lambda Libraries
README mentions `lambdas/shared/` with `dynamodb.py`, `sns.py`, `models.py`. Currently each Lambda has inline boto3 code. Optional refactor.

### Tests
`tests/unit/` and `tests/integration/` are empty. Unit tests exist co-located in each Lambda dir. Central test dirs are unused.

---

## Suggested Order

- ~~API Gateway terraform~~ ✅ Done
- ~~IAM fix for event-router~~ ✅ Done
- ~~FIFO queue DLQ fix~~ ✅ Done
- ~~Apprise URL fix~~ ✅ Done
- ~~Data collector~~ ✅ Done
- ~~Vector config changes + AWS credentials~~ ✅ Done
- S3 + UI
- Retire router-events
- Everything else (docs, dashboards, scripts)
