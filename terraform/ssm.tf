resource "aws_ssm_parameter" "cf_access_client_id" {
  name  = "/network-monitor/cf-access-client-id"
  type  = "SecureString"
  value = data.terraform_remote_state.tf_cloudflare.outputs.github_actions_client_id
}

resource "aws_ssm_parameter" "cf_access_client_secret" {
  name  = "/network-monitor/cf-access-client-secret"
  type  = "SecureString"
  value = data.terraform_remote_state.tf_cloudflare.outputs.github_actions_client_secret
}
