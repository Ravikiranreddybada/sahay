# ECS Fargate services: api (public ALB), one service per MCP server (internal ALB), autoscaling on in-flight turns.
resource "aws_security_group" "alb" {
  name   = "sahay-alb"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "app" {
  name   = "sahay-app"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 8000
    to_port         = 8200
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    self            = true
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "data" {
  name   = "sahay-data"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

resource "aws_lb" "public" {
  name               = "sahay-public"
  load_balancer_type = "application"
  subnets            = module.vpc.public_subnets
  security_groups    = [aws_security_group.alb.id]
  idle_timeout       = 120 # SSE streams
}

resource "aws_lb" "internal" {
  name               = "sahay-mcp"
  internal           = true
  load_balancer_type = "application"
  subnets            = module.vpc.private_subnets
  security_groups    = [aws_security_group.app.id]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "sahay-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  container_definitions = jsonencode([{
    name         = "api"
    image        = var.api_image
    portMappings = [{ containerPort = 8000 }]
    environment = concat(
      [{ name = "SAHAY_ENV", value = "prod" },
        { name = "SAHAY_DEV_LOGIN", value = "false" },
      { name = "SAHAY_REDIS_URL", value = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379" }],
      [for s in var.mcp_servers : { name = "SAHAY_MCP_${upper(s)}_URL", value = "http://${aws_lb.internal.dns_name}/${s}/mcp" }]
    )
    secrets = [
      { name = "ANTHROPIC_API_KEY", valueFrom = aws_secretsmanager_secret.anthropic.arn },
      { name = "SAHAY_AUTH_SECRET", valueFrom = aws_secretsmanager_secret.auth.arn },
      { name = "SAHAY_MCP_TOKEN", valueFrom = aws_secretsmanager_secret.mcp_token.arn },
      { name = "SAHAY_DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
    ]
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.app.name, awslogs-region = var.region, awslogs-stream-prefix = "api" } }
    healthCheck      = { command = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/readyz')\""], interval = 15, retries = 3 }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "sahay-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_min_tasks
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.app.id]
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

resource "aws_ecs_task_definition" "mcp" {
  for_each                 = toset(var.mcp_servers)
  family                   = "sahay-mcp-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  container_definitions = jsonencode([{
    name         = each.key
    image        = var.mcp_image
    command      = ["python", "-m", "sahay.mcp_servers.servers", each.key, "--http", "8101", "--host", "0.0.0.0"]
    portMappings = [{ containerPort = 8101 }]
    environment  = [{ name = "SAHAY_ENV", value = "prod" }]
    # without the token the server refuses to bind 0.0.0.0: user_id is caller-supplied
    secrets          = [{ name = "SAHAY_MCP_TOKEN", valueFrom = aws_secretsmanager_secret.mcp_token.arn }]
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.app.name, awslogs-region = var.region, awslogs-stream-prefix = "mcp-${each.key}" } }
  }])
}

resource "aws_ecs_service" "mcp" {
  for_each        = toset(var.mcp_servers)
  name            = "sahay-mcp-${each.key}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.mcp[each.key].arn
  desired_count   = 2
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.app.id]
  }
}

# Scale the API on in-flight turns per task (custom CloudWatch metric emitted by the app), not CPU:
# the tier is I/O-bound (capacity-estimation.md §4).
resource "aws_appautoscaling_target" "api" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.api_min_tasks
  max_capacity       = var.api_max_tasks
}

resource "aws_appautoscaling_policy" "api_inflight" {
  name               = "sahay-api-inflight"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value       = 80
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    customized_metric_specification {
      metric_name = "InFlightTurnsPerTask"
      namespace   = "Sahay"
      statistic   = "Average"
    }
  }
}
