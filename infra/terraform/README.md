# Terraform (AWS, ap-south-1)

Skeleton of the production topology in `docs/04-system-design/deployment-aws.md`: VPC (3 AZ), ECS Fargate
(api + 4 MCP services), public + internal ALB, Aurora PostgreSQL 16, ElastiCache Redis 7, SQS (+DLQ), S3 trace lake,
Secrets Manager, target-tracking autoscaling on in-flight turns.

Status: 🧭 designed. **Not yet validated**: the terraform CLI was not installed when this was written, so run `terraform validate` first. Listeners/target groups, WAF/CloudFront, IAM task roles and
Bedrock permissions are left as the next increment. Not applied to a real account.

```bash
terraform init && terraform validate
terraform plan -var api_image=<ecr>/sahay-api:sha -var mcp_image=<ecr>/sahay-api:sha
```
