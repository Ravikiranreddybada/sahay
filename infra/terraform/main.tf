# Sahay on AWS (ap-south-1). Topology and sizing: docs/04-system-design/deployment-aws.md
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" { region = var.region }

module "vpc" {
  source                 = "terraform-aws-modules/vpc/aws"
  version                = "~> 5.13"
  name                   = "sahay"
  cidr                   = "10.20.0.0/16"
  azs                    = ["${var.region}a", "${var.region}b", "${var.region}c"]
  public_subnets         = ["10.20.0.0/22", "10.20.4.0/22", "10.20.8.0/22"]
  private_subnets        = ["10.20.32.0/20", "10.20.48.0/20", "10.20.64.0/20"]
  enable_nat_gateway     = true
  one_nat_gateway_per_az = true
}

resource "aws_ecs_cluster" "this" {
  name = "sahay"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_secretsmanager_secret" "anthropic" { name = "sahay/anthropic-api-key" }

# Values are set out of band (`aws secretsmanager put-secret-value`), never in Terraform state.
# The API refuses to start in prod without a strong auth secret (sahay/main.py check_settings).
resource "aws_secretsmanager_secret" "auth" { name = "sahay/auth-secret" }          # signs session tokens (>= 32 chars)
resource "aws_secretsmanager_secret" "mcp_token" { name = "sahay/mcp-token" }       # hub -> MCP service auth (INC-011)
resource "aws_secretsmanager_secret" "database_url" { name = "sahay/database-url" } # postgresql://… built from the RDS managed secret

# Fargate needs an execution role to pull images, write logs and read the secrets above.
resource "aws_iam_role" "ecs_exec" {
  name = "sahay-ecs-exec"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_exec" {
  role       = aws_iam_role.ecs_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_exec_secrets" {
  name = "read-sahay-secrets"
  role = aws_iam_role.ecs_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [for s in [aws_secretsmanager_secret.anthropic, aws_secretsmanager_secret.auth, aws_secretsmanager_secret.mcp_token, aws_secretsmanager_secret.database_url] : s.arn]
    }]
  })
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/sahay/app"
  retention_in_days = 30 # traces in logs are PII-redacted (INC-014); keep retention short anyway
}
