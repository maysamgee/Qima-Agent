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
variable "bedrock_resource_arns" {
  type = list(string)
  validation {
    condition     = length(var.bedrock_resource_arns) > 0 && !contains(var.bedrock_resource_arns, "*")
    error_message = "Supply the specific model/profile resource ARNs required by the chosen Bedrock model."
  }
}
variable "search_api_url" {
  type = string
  validation {
    condition     = startswith(var.search_api_url, "https://")
    error_message = "Use an approved HTTPS search API endpoint."
  }
}
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
variable "db_multi_az" {
  type    = bool
  default = true
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "nat_strategy" {
  type    = string
  default = "per_az"
}
variable "cpu" {
  type    = number
  default = 512
}
variable "memory" {
  type    = number
  default = 1024
}
variable "image_tag" {
  type    = string
  default = "release"
}
variable "alarm_actions" {
  type    = list(string)
  default = []
}
