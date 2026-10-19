terraform {
  required_providers { aws = { source = "hashicorp/aws", version = "~> 6.0" } }
}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-discovery-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}
resource "aws_sqs_queue" "discovery" {
  name                       = "${var.name}-discovery"
  visibility_timeout_seconds = var.visibility_seconds
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = var.max_receive_count })
  tags                       = var.tags
}
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url            = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.discovery.arn] })
}
resource "aws_sqs_queue_policy" "tls" {
  queue_url = aws_sqs_queue.discovery.id
  policy    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "sqs:*", Resource = aws_sqs_queue.discovery.arn, Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_s3_bucket" "evidence" {
  bucket = "${var.name}-evidence-${data.aws_caller_identity.current.account_id}"
  tags   = var.tags
}
resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_policy" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.evidence.arn, "${aws_s3_bucket.evidence.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    id     = "archive-old-evidence"
    status = "Enabled"
    filter { prefix = "documents/" }
    noncurrent_version_transition {
      noncurrent_days = 90
      storage_class   = "STANDARD_IA"
    }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
  depends_on = [aws_s3_bucket_versioning.evidence]
}
resource "aws_cloudwatch_log_group" "service" {
  for_each          = toset(["api", "worker"])
  name              = "/ecs/${var.name}/${each.key}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
resource "aws_secretsmanager_secret" "database" {
  name                    = "${var.name}/database"
  recovery_window_in_days = 30
  tags                    = var.tags
}
resource "aws_secretsmanager_secret" "integrations" {
  name                    = "${var.name}/integrations"
  recovery_window_in_days = 30
  tags                    = var.tags
}
resource "aws_scheduler_schedule_group" "followups" {
  name = "${var.name}-followups"
  tags = var.tags
}
resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole", Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }, ArnEquals = { "aws:SourceArn" = aws_scheduler_schedule_group.followups.arn } } }] })
  tags               = var.tags
}
resource "aws_iam_role_policy" "scheduler" {
  role   = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.discovery.arn }] })
}
resource "aws_iam_policy" "development" {
  name = "${var.name}-development-resources"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.discovery.arn },
    { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"], Resource = "${aws_s3_bucket.evidence.arn}/documents/*" },
    { Effect = "Allow", Action = ["scheduler:CreateSchedule", "scheduler:GetSchedule"], Resource = "arn:aws:scheduler:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:schedule/${aws_scheduler_schedule_group.followups.name}/qima-followup-*" },
    { Effect = "Allow", Action = ["iam:PassRole"], Resource = aws_iam_role.scheduler.arn, Condition = { StringEquals = { "iam:PassedToService" = "scheduler.amazonaws.com" } } }
  ] })
  tags = var.tags
}
resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${var.name}-discovery-dlq"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  alarm_actions       = var.alarm_actions
  tags                = var.tags
}
resource "aws_cloudwatch_metric_alarm" "queue_age" {
  alarm_name          = "${var.name}-discovery-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 900
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.discovery.name }
  alarm_actions       = var.alarm_actions
  tags                = var.tags
}
