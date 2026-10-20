variable "region" { default = "ap-south-1" }
variable "api_image" { type = string }
variable "mcp_image" { type = string }
variable "api_min_tasks" { default = 6 } # 2 per AZ (HA); Little's law sizing in capacity-estimation.md
variable "api_max_tasks" { default = 40 }
variable "mcp_servers" { default = ["orders", "care_services", "claims", "care_journeys"] }
