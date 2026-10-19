variable "name" { type = string }
variable "tags" { type = map(string) }
variable "vpc_id" { type = string }
variable "public_subnets" { type = list(string) }
variable "private_subnets" { type = list(string) }
variable "foundation" {
  type = object({ queue_url = string, queue_arn = string, dlq_url = string, evidence_bucket = string, evidence_bucket_arn = string, log_groups = map(string), database_secret_arn = string, integrations_secret_arn = string, scheduler_role_arn = string, scheduler_group = string })
}
variable "api_certificate_arn" { type = string }
variable "api_origin_hostname" { type = string }
variable "frontend_hostname" {
  type    = string
  default = ""
}
variable "frontend_certificate_arn" {
  type    = string
  default = ""
}
variable "route53_zone_id" {
  type    = string
  default = ""
}
variable "bedrock_model_id" { type = string }
variable "bedrock_resource_arns" { type = list(string) }
variable "search_api_url" { type = string }
variable "approved_fetch_domains" {
  type    = string
  default = ""
}
variable "desired_count" {
  type    = number
  default = 0
}
variable "worker_desired_count" {
  type    = number
  default = 0
}
variable "image_tag" {
  type    = string
  default = "release"
}
variable "cpu" {
  type    = number
  default = 512
}
variable "memory" {
  type    = number
  default = 1024
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "db_multi_az" {
  type    = bool
  default = true
}
variable "alarm_actions" {
  type    = list(string)
  default = []
}
