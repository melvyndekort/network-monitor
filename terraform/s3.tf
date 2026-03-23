# S3 Bucket for Static UI

resource "aws_s3_bucket" "ui" {
  bucket = "network-monitor-ui-${var.account_id}"

  tags = {
    Name = "network-monitor-ui"
  }
}

resource "aws_s3_bucket_public_access_block" "ui" {
  bucket = aws_s3_bucket.ui.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "ui" {
  bucket     = aws_s3_bucket.ui.id
  depends_on = [aws_s3_bucket_public_access_block.ui]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = aws_cloudfront_origin_access_identity.ui.iam_arn
      }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.ui.arn}/*"
    }]
  })
}
