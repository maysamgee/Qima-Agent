output "frontend_url" { value = local.frontend_url }
output "api_url" { value = "https://${var.api_origin_hostname}" }
output "frontend_bucket" { value = aws_s3_bucket.frontend.id }
output "cloudfront_distribution_id" { value = aws_cloudfront_distribution.frontend.id }
output "cognito_user_pool_id" { value = aws_cognito_user_pool.this.id }
output "cognito_client_id" { value = aws_cognito_user_pool_client.this.id }
output "cognito_domain" { value = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com" }
output "ecr_repositories" { value = { for k, v in aws_ecr_repository.service : k => v.repository_url } }
output "ecs_cluster" { value = aws_ecs_cluster.this.name }
output "ecs_services" { value = { api = aws_ecs_service.api.name, worker = aws_ecs_service.worker.name } }
output "task_definitions" { value = { for k, v in aws_ecs_task_definition.service : k => v.arn } }
output "database_address" { value = aws_db_instance.this.address }
output "database_admin_secret_arn" { value = aws_db_instance.this.master_user_secret[0].secret_arn }
output "task_security_group" { value = aws_security_group.tasks.id }
output "alb_dns_name" { value = aws_lb.api.dns_name }
