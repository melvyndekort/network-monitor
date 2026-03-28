# network-monitor

> For global standards, way-of-workings, and pre-commit checklist, see `~/.kiro/steering/behavior.md`

## Role

Python developer and AWS engineer.

## What This Does

Serverless network device monitoring system. Tracks all devices across VLANs, detects presence changes, enriches metadata (manufacturer lookup), and sends notifications. Built with AWS Lambda, DynamoDB, SQS/SNS, and a static S3-hosted UI.

## Important: Subaccount Pattern Reference Implementation

This is the first repo using a dedicated AWS subaccount (`844347863910`). State bucket is `mdekort-tfstate-844347863910`. Other repos will follow this pattern.

## Important: Multi-Component Repo

- `lambdas/` — 5 Lambda functions, each with its own `handler.py`, `pyproject.toml`, tests
  - `api_handler/` — API Gateway backend
  - `event_router/` — Routes incoming events to processors
  - `enrich_metadata/` — Manufacturer lookup for MAC addresses
  - `send_notifications/` — Sends ntfy notifications
  - `track_presence/` — Tracks device online/offline state
- `data-collector/` — Python container (separate pyproject.toml, Dockerfile, Makefile) that collects data from router-events and pushes to SQS
- `ui/` — Static HTML/JS frontend hosted on S3 behind CloudFront
- `terraform/` — All AWS infrastructure
- `scripts/` — Utility scripts
- `.github/workflows/deploy-lambda.yml` — Reusable workflow for Lambda deployment

## Lambda Deployment Pattern

Terraform creates Lambdas with dummy code and `ignore_changes` on `source_code_hash`. Each Lambda has its own workflow that calls the reusable `deploy-lambda.yml`.

## Terraform Details

- Backend: S3 key `network-monitor.tfstate` in `mdekort-tfstate-844347863910`
- Providers: AWS `~> 5.0`, Cloudflare `~> 5.0`
- Uses `default_tags` on the AWS provider

## Related Repositories

- `~/src/melvyndekort/tf-aws` — Created the subaccount and bootstrapped OIDC
- `~/src/melvyndekort/tf-github` — OIDC role provisioning for this repo
- `~/src/melvyndekort/tf-cloudflare` — DNS and API tokens
- `~/src/melvyndekort/router-events` — Source of device data (DHCP events)
