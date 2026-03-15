# IAM User for Vector on compute-1 to send events to SQS

resource "aws_iam_user" "vector" {
  name = "network-monitor-vector"
  path = "/network-monitor/"

  tags = {
    Name = "network-monitor-vector"
  }
}

resource "aws_iam_user_policy" "vector" {
  name = "sqs-send-message"
  user = aws_iam_user.vector.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
      Resource = aws_sqs_queue.device_events.arn
    }]
  })
}

resource "aws_iam_access_key" "vector" {
  user = aws_iam_user.vector.name
}
