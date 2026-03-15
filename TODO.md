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

---

## What's Left

### Terraform: FIFO Queue DLQ
The `device_events` FIFO queue has a DLQ defined (`device_events_dlq`) but no `redrive_policy` attached to the main queue. The fan-out queues (presence-tracker, notifier, metadata-enricher) all have redrive policies — this one was missed.

### Terraform: S3 Bucket for UI
Need `s3.tf` with:
- S3 bucket for static HTMX UI
- Static website hosting config
- Bucket policy for public read (or CloudFront)

### Data Collector
Everything under `data-collector/` is empty. Need:
- `collector/main.py` — Poll MikroTik ARP table every 30s, output JSON events to stdout
- `collector/mikrotik.py` — librouteros wrapper for ARP, DHCP leases, wireless clients
- `collector/models.py` — Event data models
- `requirements.txt` — librouteros, etc.
- `Dockerfile` — Python 3.12 container
- `config.yaml` — MikroTik connection settings

MikroTik router: 10.204.10.1 (RB4011iGS+, RouterOS 7.22)

### Vector Config Changes (on compute-1)
**Important:** No new Vector container. Modify the existing config at `/var/srv/apps/vector/vector.toml` on compute-1. Vector runs in the `monitoring.yml` docker-compose stack (homelab repo: `~/src/melvyndekort/homelab/compute-1/monitoring.yml`).

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
- FIFO queue DLQ fix (small, important)
- Data collector (the event source)
- Vector config changes + AWS credentials (bridges on-prem to AWS)
- S3 + UI
- Retire router-events
- Everything else (docs, dashboards, scripts)
