variable "name" { type = string }
variable "tags" { type = map(string) }
variable "visibility_seconds" {
  type    = number
  default = 120
}
variable "max_receive_count" {
  type    = number
  default = 5
}
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "alarm_actions" {
  type    = list(string)
  default = []
}
