# TODO

## Lambda Deployment Pipeline

**Issue**: Lambda deployment workflows fail because GitHub Actions AWS credentials are in the organization account (075673041815) but Lambda functions exist in the network-monitor account (844347863910).

**Current State**:
- Terraform successfully deploys infrastructure to account 844347863910 using role assumption
- Lambda functions exist: `arn:aws:lambda:eu-west-1:844347863910:function:network-monitor-*`
- GitHub Actions workflows build successfully but deployment fails with "Function not found"

**Solution Needed**:
- Update `AWS_ROLE_ARN` GitHub secret to use the same role that Terraform uses: `arn:aws:iam::844347863910:role/OrganizationAccountAccessRole`
- OR configure the Lambda deployment workflow to assume the correct role before deploying

**Workflows Affected**:
- `.github/workflows/event-router.yml`
- `.github/workflows/track-presence.yml`
- `.github/workflows/send-notifications.yml`
- `.github/workflows/enrich-metadata.yml`
- `.github/workflows/api-handler.yml`
