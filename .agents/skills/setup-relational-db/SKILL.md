---
name: setup-relational-db
description: Provision compliant AWS PostgreSQL relational databases using Terraform (supports Aurora Serverless v2 and RDS PostgreSQL with KMS CMEK encryption, IAM auth, private subnets, and Multi-AZ). Use when creating, provisioning, or modifying relational databases on AWS.
---

# Setup Relational DB (AWS PostgreSQL via Terraform)

This skill guides agents and engineers through provisioning compliant relational database infrastructure on AWS using Terraform. It supports two deployment modes based on traffic pattern:
- **Aurora Serverless v2** (Recommended for variable/bursty traffic, auto-scaling between 0.5 and 16 ACUs).
- **Amazon RDS PostgreSQL** (For predictable workloads requiring standard instance-based provisioning).

---

## Rule Precedence

$$\text{CyberSec (CSS)} \succ \text{CloudGov (CGS)} \succ \text{EntArch (EAS)}$$

All configurations must strictly enforce the higher-precedence standards.

---

## Hard Guardrails (Non-Negotiable)

1. **Approved Engine**: PostgreSQL only (`aurora-postgresql` or `postgres`). All other database engines are prohibited (*EAS_1*).
2. **Platform**: AWS managed services only (Amazon Aurora or RDS). Never run unmanaged database software on EC2 (*CGS_1*).
3. **Approved Regions**: `us-east-1` and `us-east-2` only (*CGS_1*).
4. **Storage Encryption**: `storage_encrypted = true` bound to a Customer-Managed Key (CMEK) via `kms_key_id`. Default AWS-managed keys are prohibited (*CSS_1*).
5. **Authentication**: `iam_database_authentication_enabled = true`. Master passwords must be managed via AWS Secrets Manager (`manage_master_user_password = true`) (*CSS_1*).
6. **Network Isolation**: Instances must reside strictly in private subnets with `publicly_accessible = false` and ingress restricted to the application security group (*CGS_1*, *CSS_1*).
7. **High Availability**: Production environments (`env == "prod"`) must enable Multi-AZ (*CGS_1*).
8. **FinOps & Sizing Limits** (*CGS_1*):
   - Aurora Serverless v2 must cap scaling at `max_capacity = 16`.
   - RDS non-production instances must not exceed `db.m6g.xlarge`.
   - RDS storage must use `gp3` with `max_allocated_storage` configured for dynamic autoscaling.
   - Dedicated IOPS (`io1`/`io2`) in dev/stage are prohibited.
9. **Mandatory Metadata Tags** (*CGS_1*):
   - `Environment`: `dev`, `stage`, or `prod`
   - `CostCenter`: Format `CC-[0-9]{4}`
   - `Owner`: Team email alias or service identifier
   - `DataClassification`: `Confidential`, `Internal`, or `Public`
10. **Lifecycle & Deletion Protection**: `deletion_protection = true` in production; automated backup retention between 7 and 35 days (*CGS_1*).

---

## Step-by-Step Instructions

### Step 1: Input Gathering & Validation
Collect and validate the following variables:
- `app_name`: Application identifier (e.g., `orders-service`).
- `environment`: `dev`, `stage`, or `prod`.
- `deployment_mode`: `aurora_serverless` or `rds_instance`.
- `vpc_id` & `private_subnet_ids`: At least 2 private subnets in distinct AZs within `us-east-1` or `us-east-2`.
- `app_security_group_id`: Security group of the connecting application tier.
- `cost_center`: Billing code matching `^CC-[0-9]{4}$`.
- `owner`: Team email alias.
- `data_classification`: `Confidential`, `Internal`, or `Public`.

### Step 2: Provision Customer-Managed KMS Key (CMEK)
```hcl
resource "aws_kms_key" "db" {
  description             = "CMEK for ${var.app_name}-${var.environment} PostgreSQL database"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = local.mandatory_tags
}

resource "aws_kms_alias" "db" {
  name          = "alias/${var.app_name}-${var.environment}-db"
  target_key_id = aws_kms_key.db.key_id
}
```

### Step 3: Network Isolation & Security Groups
```hcl
resource "aws_db_subnet_group" "this" {
  name        = "${var.app_name}-${var.environment}-db-subnet-group"
  description = "Private database subnet group"
  subnet_ids  = var.private_subnet_ids

  tags = local.mandatory_tags
}

resource "aws_security_group" "db" {
  name        = "${var.app_name}-${var.environment}-db-sg"
  description = "Controls ingress to PostgreSQL database"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Allow PostgreSQL access from application tier"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.app_security_group_id]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.mandatory_tags
}
```

### Step 4A: Provision Aurora PostgreSQL Serverless v2 (If `aurora_serverless`)
```hcl
resource "aws_rds_cluster" "aurora" {
  count                               = var.deployment_mode == "aurora_serverless" ? 1 : 0
  cluster_identifier                  = "${var.app_name}-${var.environment}-cluster"
  engine                              = "aurora-postgresql"
  engine_version                      = "15.4"
  database_name                       = replace(var.app_name, "-", "_")
  master_username                     = "dbadmin"
  manage_master_user_password         = true
  iam_database_authentication_enabled = true
  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.db.arn
  db_subnet_group_name                = aws_db_subnet_group.this.name
  vpc_security_group_ids              = [aws_security_group.db.id]
  deletion_protection                 = var.environment == "prod"
  backup_retention_period             = var.environment == "prod" ? 35 : 7

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 16.0
  }

  tags = local.mandatory_tags
}

resource "aws_rds_cluster_instance" "aurora_instances" {
  count               = var.deployment_mode == "aurora_serverless" ? (var.environment == "prod" ? 2 : 1) : 0
  identifier          = "${var.app_name}-${var.environment}-instance-${count.index + 1}"
  cluster_identifier = aws_rds_cluster.aurora[0].id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.aurora[0].engine
  engine_version      = aws_rds_cluster.aurora[0].engine_version
  publicly_accessible = false

  tags = local.mandatory_tags
}
```

### Step 4B: Provision Standard Amazon RDS PostgreSQL (If `rds_instance`)
```hcl
resource "aws_db_instance" "rds" {
  count                               = var.deployment_mode == "rds_instance" ? 1 : 0
  identifier                          = "${var.app_name}-${var.environment}-db"
  engine                              = "postgres"
  engine_version                      = "15.4"
  instance_class                      = var.environment == "prod" ? "db.r6g.xlarge" : "db.t4g.medium"
  allocated_storage                   = 20
  max_allocated_storage               = 100
  storage_type                        = "gp3"
  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.db.arn
  username                            = "dbadmin"
  manage_master_user_password         = true
  iam_database_authentication_enabled = true
  multi_az                            = var.environment == "prod"
  publicly_accessible                 = false
  db_subnet_group_name                = aws_db_subnet_group.this.name
  vpc_security_group_ids              = [aws_security_group.db.id]
  deletion_protection                 = var.environment == "prod"
  backup_retention_period             = var.environment == "prod" ? 35 : 7

  tags = local.mandatory_tags
}
```

### Step 5: Application IAM Access Policy
Attach an IAM policy granting connect privileges to the application role:
```hcl
data "aws_iam_policy_document" "db_connect" {
  statement {
    actions   = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:${var.aws_region}:${data.aws_caller_identity.current.account_id}:dbuser:*/*"]
  }
}

resource "aws_iam_policy" "db_connect" {
  name        = "${var.app_name}-${var.environment}-db-connect-policy"
  description = "Allows IAM database connection to PostgreSQL"
  policy      = data.aws_iam_policy_document.db_connect.json

  tags = local.mandatory_tags
}
```

### Step 6: Verification & Pre-Apply Linting
Before executing `terraform apply`:
1. Run `terraform fmt -check` and `terraform validate`.
2. Inspect the `terraform plan` output to verify:
   - `storage_encrypted` is `true` and `kms_key_id` references the customer-managed key.
   - `iam_database_authentication_enabled` is `true`.
   - `publicly_accessible` is `false`.
   - In production, `multi_az = true` (or 2 cluster instances) and `deletion_protection = true`.
   - All 4 required tags are present.

---

## Traceability Matrix

| Precedence | Standard | Source File | Commit SHA | Rule Citation |
|---|---|---|---|---|
| 1 | CSS | `cyber-sec-standards/CSS_1-Relational_Database_Encryption_at_Rest.md` | `b21b844ab72ef6c67c7ff8182dc9ca384cdd17d9` | Mandatory CMEK encryption at rest, IAM auth |
| 2 | CGS | `cloud-gov-standards/CGS_1-approved_cloud_provider_for_managed_databases.md` | `3d28de52366c11b42db59441a01634debd995f47` | AWS managed DB only, approved regions, private subnets, Multi-AZ prod, FinOps caps, tagging |
| 3 | EAS | `enterprise-arch-standards/EAS_1-approved_enterprise_database_engines.md` | `7827bb20dac5ec93fe4b05e22bb25bb616f5baef` | PostgreSQL approved relational engine |
