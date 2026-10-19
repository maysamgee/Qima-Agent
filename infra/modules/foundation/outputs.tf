output "queue_url" { value = aws_sqs_queue.discovery.url }
output "queue_arn" { value = aws_sqs_queue.discovery.arn }
output "dlq_url" { value = aws_sqs_queue.dlq.url }
output "evidence_bucket" { value = aws_s3_bucket.evidence.id }
output "evidence_bucket_arn" { value = aws_s3_bucket.evidence.arn }
output "log_groups" { value = { for k, v in aws_cloudwatch_log_group.service : k => v.name } }
output "database_secret_arn" { value = aws_secretsmanager_secret.database.arn }
output "integrations_secret_arn" { value = aws_secretsmanager_secret.integrations.arn }
output "scheduler_role_arn" { value = aws_iam_role.scheduler.arn }
output "scheduler_group" { value = aws_scheduler_schedule_group.followups.name }
output "development_policy_arn" { value = aws_iam_policy.development.arn }
