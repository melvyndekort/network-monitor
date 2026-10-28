# Network Monitor - Main Terraform Configuration
# This file imports all modules and resources

# DynamoDB tables are defined in dynamodb.tf
# Lambda functions are defined in lambda.tf
# SNS/SQS are defined in sns_sqs.tf
# IAM roles are defined in iam.tf

# Throwaway comment-only change: proves github-actions-network-monitor's
# apply still works now that it runs under PowerUserAccess + boundary +
# guardrail instead of AdministratorAccess (tf-github PR #45, canary for
# the §4.2a rollout in tf-github-redesign-plan-2026-10.md). No resource
# change - a push-to-main apply under the new role is the test. Delete
# this comment and close the PR once the apply is confirmed green.
