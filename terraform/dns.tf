resource "cloudflare_dns_record" "ui" {
  zone_id = data.terraform_remote_state.tf_cloudflare.outputs.mdekort_zone_id
  name    = aws_acm_certificate.ui.domain_name
  type    = "CNAME"
  ttl     = 300
  content = aws_cloudfront_distribution.ui.domain_name
}
