resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = var.tags
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = [for r in aws_ecr_repository.service : r.arn] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = [for log in var.foundation.log_groups : "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:${log}:*"] },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = var.foundation.integrations_secret_arn }
  ] })
}
resource "aws_iam_role" "task" {
  for_each           = toset(["api", "worker"])
  name               = "${var.name}-${each.key}-task"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = var.tags
}
resource "aws_iam_role_policy" "task" {
  for_each = aws_iam_role.task
  role     = each.value.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = var.foundation.database_secret_arn },
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = var.bedrock_resource_arns }
    ], [for statement in [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"], Resource = "${var.foundation.evidence_bucket_arn}/documents/*" }
      ] : statement if each.key == "api"], [for statement in [
      { Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"], Resource = var.foundation.queue_arn },
      { Effect = "Allow", Action = ["scheduler:CreateSchedule", "scheduler:GetSchedule"], Resource = "arn:aws:scheduler:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:schedule/${var.foundation.scheduler_group}/qima-followup-*" },
      { Effect = "Allow", Action = ["iam:PassRole"], Resource = var.foundation.scheduler_role_arn, Condition = { StringEquals = { "iam:PassedToService" = "scheduler.amazonaws.com" } } }
  ] : statement if each.key == "worker"]) })
}
resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = var.tags
}
locals {
  frontend_url = "https://${var.frontend_hostname != "" ? var.frontend_hostname : aws_cloudfront_distribution.frontend.domain_name}"
  environment = {
    APP_ENV                     = "prod"
    AUTH_MODE                   = "cognito"
    DATABASE_SECRET_ARN         = var.foundation.database_secret_arn
    DATABASE_HOST               = aws_db_instance.this.address
    DATABASE_NAME               = "qima_agents"
    DATABASE_SSLMODE            = "verify-full"
    DATABASE_SSLROOTCERT        = "/app/backend/certs/rds-global-bundle.pem"
    CORS_ORIGINS                = local.frontend_url
    AWS_REGION                  = data.aws_region.current.region
    AI_PROVIDER                 = "bedrock"
    BEDROCK_MODEL_ID            = var.bedrock_model_id
    QUEUE_PROVIDER              = "sqs"
    DISCOVERY_QUEUE_URL         = var.foundation.queue_url
    DISCOVERY_DLQ_URL           = var.foundation.dlq_url
    STORAGE_PROVIDER            = "s3"
    EVIDENCE_BUCKET             = var.foundation.evidence_bucket
    SEARCH_PROVIDER             = "approved_api"
    SEARCH_API_URL              = var.search_api_url
    APPROVED_FETCH_DOMAINS      = var.approved_fetch_domains
    EMAIL_PROVIDER              = "mock"
    REAL_EMAIL_ENABLED          = "false"
    REAL_INSTAGRAM_SEND_ENABLED = "false"
    INSTAGRAM_PROVIDER          = "manual"
    COGNITO_USER_POOL_ID        = aws_cognito_user_pool.this.id
    COGNITO_APP_CLIENT_ID       = aws_cognito_user_pool_client.this.id
    SCHEDULER_ROLE_ARN          = var.foundation.scheduler_role_arn
    SCHEDULER_GROUP             = var.foundation.scheduler_group
  }
}
resource "aws_ecs_task_definition" "service" {
  for_each                 = toset(["api", "worker"])
  family                   = "${var.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  container_definitions = jsonencode([{
    name                   = each.key
    image                  = "${aws_ecr_repository.service[each.key].repository_url}:${var.image_tag}"
    essential              = true
    user                   = "10001"
    readonlyRootFilesystem = true
    portMappings           = each.key == "api" ? [{ containerPort = 8000, protocol = "tcp" }] : []
    environment            = [for key, value in local.environment : { name = key, value = value }]
    secrets                = [{ name = "SEARCH_API_KEY", valueFrom = "${var.foundation.integrations_secret_arn}:search_api_key::" }]
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }]
    logConfiguration       = { logDriver = "awslogs", options = { awslogs-group = var.foundation.log_groups[each.key], awslogs-region = data.aws_region.current.region, awslogs-stream-prefix = each.key } }
    stopTimeout            = 120
  }])
  volume { name = "tmp" }
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
  tags = var.tags
}
resource "aws_lb" "api" {
  name                       = "${var.name}-api"
  internal                   = false
  load_balancer_type         = "application"
  subnets                    = var.public_subnets
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = true
  tags                       = var.tags
}
resource "aws_lb_target_group" "api" {
  name        = "${var.name}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check {
    path                = "/health/ready"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
  tags = var.tags
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.api_certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
resource "aws_ecs_service" "api" {
  name            = "${var.name}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.service["api"].arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnets
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  health_check_grace_period_seconds = 60
  depends_on                        = [aws_lb_listener.https]
  tags                              = var.tags
}
resource "aws_ecs_service" "worker" {
  name            = "${var.name}-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.service["worker"].arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnets
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  tags = var.tags
}
resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${var.name}-api-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  dimensions          = { LoadBalancer = aws_lb.api.arn_suffix }
  alarm_actions       = var.alarm_actions
  tags                = var.tags
}
