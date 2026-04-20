terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.33"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  backend "s3" {
    bucket  = "vocalmarket-tfstate"
    key     = "prod/terraform.tfstate"
    region  = "af-south-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = var.tags }
}

# ── VPC ───────────────────────────────────────────────────────────────────────

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr

  # af-south-1 has 3 AZs
  azs             = ["af-south-1a", "af-south-1b", "af-south-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = false  # HA: one NAT GW per AZ
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Required tags for AWS Load Balancer Controller
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

# ── EKS Cluster ───────────────────────────────────────────────────────────────

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnets
  cluster_endpoint_public_access = true

  # EKS managed add-ons
  cluster_addons = {
    coredns                = { most_recent = true }
    kube-proxy             = { most_recent = true }
    vpc-cni                = { most_recent = true }
    aws-ebs-csi-driver     = { most_recent = true }
    aws-load-balancer-controller = { most_recent = true }
  }

  eks_managed_node_groups = {
    # General-purpose nodes for all non-GPU services
    general = {
      name           = "general"
      instance_types = [var.general_node_instance_type]
      min_size       = var.general_node_min
      max_size       = var.general_node_max
      desired_size   = var.general_node_desired

      labels = { node-group = "general" }

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 50
            volume_type           = "gp3"
            encrypted             = true
            delete_on_termination = true
          }
        }
      }
    }

    # GPU nodes for Whisper STT — tainted to only accept GPU workloads
    gpu-whisper = {
      name           = "gpu-whisper"
      instance_types = [var.gpu_node_instance_type]
      min_size       = var.gpu_node_min
      max_size       = var.gpu_node_max
      desired_size   = var.gpu_node_desired
      ami_type       = "AL2_x86_64_GPU"  # Amazon Linux 2 with GPU AMI

      labels = { node-group = "gpu-whisper" }
      taints = [{
        key    = "nvidia.com/gpu"
        value  = "present"
        effect = "NO_SCHEDULE"
      }]

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 100  # Whisper model cache
            volume_type           = "gp3"
            encrypted             = true
            delete_on_termination = true
          }
        }
      }
    }
  }
}

# ── RDS PostgreSQL 16 + pgvector ──────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name       = "${var.cluster_name}-db-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name   = "${var.cluster_name}-rds-sg"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }
}

resource "aws_db_instance" "postgres" {
  identifier        = "${var.cluster_name}-postgres"
  engine            = "postgres"
  engine_version    = "16.4"
  instance_class    = var.rds_instance_class
  allocated_storage = var.rds_allocated_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "vocalmarket"
  username = "vocalmarket"
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az               = true
  deletion_protection    = true
  backup_retention_period = 14
  skip_final_snapshot    = false
  final_snapshot_identifier = "${var.cluster_name}-final-snapshot"

  # pgvector is installed via the init SQL in the K8s ConfigMap
  parameter_group_name = aws_db_parameter_group.postgres16.name
}

resource "aws_db_parameter_group" "postgres16" {
  name   = "${var.cluster_name}-pg16"
  family = "postgres16"

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }
  # pgvector is not a shared library — install it via: CREATE EXTENSION IF NOT EXISTS vector;
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.cluster_name}-cache-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.cluster_name}-redis"
  description          = "VocalMarket Redis cache + Celery broker"
  node_type            = var.elasticache_node_type
  port                 = 6379
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"

  num_cache_clusters         = 2  # Primary + 1 replica
  automatic_failover_enabled = true
  multi_az_enabled           = true
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

# ── Secrets Manager — store sensitive values for K8s ExternalSecrets ─────────

resource "aws_secretsmanager_secret" "postgres" {
  name = "/${var.cluster_name}/postgres"
}

resource "aws_secretsmanager_secret_version" "postgres" {
  secret_id = aws_secretsmanager_secret.postgres.id
  secret_string = jsonencode({
    username = aws_db_instance.postgres.username
    password = random_password.db_password.result
    database = aws_db_instance.postgres.db_name
    host     = aws_db_instance.postgres.address
  })
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "cluster_endpoint" {
  value     = module.eks.cluster_endpoint
  sensitive = true
}

output "rds_endpoint" {
  value     = aws_db_instance.postgres.address
  sensitive = true
}

output "redis_endpoint" {
  value     = aws_elasticache_replication_group.redis.primary_endpoint_address
  sensitive = true
}
