# S3 Bucket for Static UI

resource "aws_s3_bucket" "ui" {
  bucket = "network-monitor-ui-${var.account_id}"

  tags = {
    Name = "network-monitor-ui"
  }
}

resource "aws_s3_bucket_website_configuration" "ui" {
  bucket = aws_s3_bucket.ui.id

  index_document {
    suffix = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "ui" {
  bucket = aws_s3_bucket.ui.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "ui" {
  bucket     = aws_s3_bucket.ui.id
  depends_on = [aws_s3_bucket_public_access_block.ui]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.ui.arn}/*"
    }]
  })
}
