resource "aws_cloudfront_origin_access_identity" "ui" {
  comment = "Identity for network-monitor UI"
}

resource "aws_cloudfront_origin_access_control" "api" {
  name                              = "network-monitor-api"
  description                       = "OAC for API Lambda function URL (SigV4)"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_public_key" "ui" {
  name        = "network-monitor"
  comment     = "Public key for signed cookie auth (from get-cookies)"
  encoded_key = data.terraform_remote_state.get_cookies.outputs.public_key_pem
}

resource "aws_cloudfront_key_group" "ui" {
  name    = "network-monitor"
  comment = "Key group for network-monitor.mdekort.nl"
  items   = [aws_cloudfront_public_key.ui.id]
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "ui" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "Network Monitor UI"
  price_class     = "PriceClass_100"

  default_root_object = "index.html"

  aliases = [aws_acm_certificate.ui.domain_name]

  viewer_certificate {
    cloudfront_default_certificate = false
    acm_certificate_arn            = aws_acm_certificate_validation.ui.certificate_arn
    minimum_protocol_version       = "TLSv1.2_2021"
    ssl_support_method             = "sni-only"
  }

  origin {
    origin_id   = "s3-ui"
    domain_name = aws_s3_bucket.ui.bucket_regional_domain_name

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.ui.cloudfront_access_identity_path
    }
  }

  origin {
    origin_id   = "api"
    domain_name = replace(replace(aws_lambda_function_url.api_handler.function_url, "https://", ""), "/", "")

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    origin_access_control_id = aws_cloudfront_origin_access_control.api.id
  }

  default_cache_behavior {
    target_origin_id = "s3-ui"

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id = data.aws_cloudfront_cache_policy.caching_disabled.id

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]

    trusted_key_groups = [aws_cloudfront_key_group.ui.id]
  }

  ordered_cache_behavior {
    path_pattern     = "/api/*"
    target_origin_id = "api"

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    trusted_key_groups = [aws_cloudfront_key_group.ui.id]
  }

  ordered_cache_behavior {
    path_pattern     = "/error-pages/*"
    target_origin_id = "s3-ui"

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id = data.aws_cloudfront_cache_policy.caching_disabled.id

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]
  }

  ordered_cache_behavior {
    path_pattern     = "/assets/*"
    target_origin_id = "s3-ui"

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id = data.aws_cloudfront_cache_policy.caching_disabled.id

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]
  }

  ordered_cache_behavior {
    path_pattern     = "/callback.html"
    target_origin_id = "s3-ui"

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id = data.aws_cloudfront_cache_policy.caching_disabled.id

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]
  }

  custom_error_response {
    error_caching_min_ttl = 0
    error_code            = 403
    response_code         = 403
    response_page_path    = "/error-pages/403.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
}
