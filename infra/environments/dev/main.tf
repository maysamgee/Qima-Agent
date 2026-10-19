terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 6.0" } }
  backend "s3" {}
}
provider "aws" {
  region = var.region
  default_tags { tags = local.tags }
}
variable "project" {
  type    = string
  default = "qima-agents"
}
variable "region" { type = string }
variable "owner" { type = string }
variable "cost_center" {
  type    = string
  default = ""
}
variable "alarm_actions" {
  type    = list(string)
  default = []
}
locals { tags = merge({ Project = var.project, Environment = "dev", Owner = var.owner, ManagedBy = "Terraform" }, var.cost_center != "" ? { CostCenter = var.cost_center } : {}) }
module "foundation" {
  source        = "../../modules/foundation"
  name          = "${var.project}-dev"
  tags          = local.tags
  alarm_actions = var.alarm_actions
}
output "application" {
  value = { AWS_REGION = var.region, DISCOVERY_QUEUE_URL = module.foundation.queue_url, DISCOVERY_DLQ_URL = module.foundation.dlq_url, EVIDENCE_BUCKET = module.foundation.evidence_bucket, SCHEDULER_ROLE_ARN = module.foundation.scheduler_role_arn, SCHEDULER_GROUP = module.foundation.scheduler_group }
}
output "development_policy_arn" { value = module.foundation.development_policy_arn }
