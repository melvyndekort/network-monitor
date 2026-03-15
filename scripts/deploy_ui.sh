#!/usr/bin/env bash
set -euo pipefail

# Deploy UI to S3
aws s3 sync ui/ s3://network-monitor-ui-844347863910/ \
  --delete \
  --region eu-west-1

echo "UI deployed to http://network-monitor-ui-844347863910.s3-website-eu-west-1.amazonaws.com"
