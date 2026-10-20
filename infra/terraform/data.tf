# Aurora PostgreSQL 16 (checkpoints, tickets, feedback, pgvector) + ElastiCache Redis 7 (rate limit, semantic cache, locks)
resource "aws_db_subnet_group" "db" {
  name       = "sahay-db"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_rds_cluster" "pg" {
  cluster_identifier          = "sahay-pg"
  engine                      = "aurora-postgresql"
  engine_version              = "16.4"
  database_name               = "sahay"
  master_username             = "sahay"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.db.name
  vpc_security_group_ids      = [aws_security_group.data.id]
  storage_encrypted           = true
  backup_retention_period     = 7
  deletion_protection         = true
}

resource "aws_rds_cluster_instance" "pg" {
  count              = 2 # writer + reader (pgvector reads, analytics)
  identifier         = "sahay-pg-${count.index}"
  cluster_identifier = aws_rds_cluster.pg.id
  instance_class     = "db.r7g.large"
  engine             = aws_rds_cluster.pg.engine
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "sahay-redis"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "sahay-redis"
  description                = "rate limits, semantic cache, thread locks"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.r7g.large"
  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.data.id]
}

resource "aws_sqs_queue" "jobs" {
  for_each                   = toset(["ingest", "evals", "reminders"])
  name                       = "sahay-${each.key}"
  visibility_timeout_seconds = 300
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = 5 })
}

resource "aws_sqs_queue" "dlq" { name = "sahay-dlq" }

resource "aws_s3_bucket" "traces" { bucket_prefix = "sahay-traces-" }

resource "aws_s3_bucket_lifecycle_configuration" "traces" {
  bucket = aws_s3_bucket.traces.id
  rule {
    id     = "expire-90d"
    status = "Enabled"
    filter {}
    expiration { days = 90 }
  }
}
