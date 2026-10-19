terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 6.0" } }
  backend "s3" {}
}
provider "aws" {
  region = var.region
  default_tags { tags = local.tags }
}
locals { tags = merge({ Project = var.project, Environment = "prod", Owner = var.owner, ManagedBy = "Terraform" }, var.cost_center != "" ? { CostCenter = var.cost_center } : {}) }
module "foundation" {
  source        = "../../modules/foundation"
  name          = "${var.project}-prod"
  tags          = local.tags
  alarm_actions = var.alarm_actions
}
module "network" {
  source       = "../../modules/network"
  name         = "${var.project}-prod"
  tags         = local.tags
  nat_strategy = var.nat_strategy
}
module "platform" {
  source                   = "../../modules/platform"
  name                     = "${var.project}-prod"
  tags                     = local.tags
  foundation               = module.foundation
  vpc_id                   = module.network.vpc_id
  public_subnets           = module.network.public_subnets
  private_subnets          = module.network.private_subnets
  api_certificate_arn      = var.api_certificate_arn
  api_origin_hostname      = var.api_origin_hostname
  frontend_hostname        = var.frontend_hostname
  frontend_certificate_arn = var.frontend_certificate_arn
  route53_zone_id          = var.route53_zone_id
  bedrock_model_id         = var.bedrock_model_id
  bedrock_resource_arns    = var.bedrock_resource_arns
  search_api_url           = var.search_api_url
  approved_fetch_domains   = var.approved_fetch_domains
  desired_count            = var.desired_count
  worker_desired_count     = var.worker_desired_count
  db_multi_az              = var.db_multi_az
  db_instance_class        = var.db_instance_class
  cpu                      = var.cpu
  memory                   = var.memory
  image_tag                = var.image_tag
  alarm_actions            = var.alarm_actions
}
output "platform" { value = module.platform }
output "application_resources" { value = module.foundation }
output "private_subnets" { value = module.network.private_subnets }
