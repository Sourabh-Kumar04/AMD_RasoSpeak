# RasoSpeak AI OS — Terraform Infrastructure
# Production-grade AWS/EKS infrastructure

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  backend "s3" {
    bucket = "rasospeak-terraform-state"
    key    = "infrastructure/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# ──────────────────────────────────────────────────────────────────────────────
# Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "rasospeak"
}

# ──────────────────────────────────────────────────────────────────────────────
# VPC
# ──────────────────────────────────────────────────────────────────────────────

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.cluster_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = false
  enable_dns_hostnames   = true
  enable_dns_support     = true

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# EKS Cluster
# ──────────────────────────────────────────────────────────────────────────────

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.29"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Control plane
  create_kms_key         = true
  kms_key_administrators = [data.aws_caller_identity.current.arn]
  kms_key_description    = "EKS cluster encryption key"

  # Node groups
  eks_managed_node_groups = {
    general = {
      min_size       = 3
      max_size       = 10
      desired_size   = 3
      instance_types = ["m6i.xlarge"]
      capacity_type  = "ON_DEMAND"

      labels = {
        role = "general"
      }

      update_config = {
        max_unavailable_percentage = 33
      }
    }

    memory_optimized = {
      min_size       = 2
      max_size       = 6
      desired_size   = 2
      instance_types = ["r6i.2xlarge"]
      capacity_type  = "ON_DEMAND"

      labels = {
        role = "memory-service"
      }

      taints = [
        {
          key    = "workload"
          value  = "memory"
          effect = "NO_SCHEDULE"
        }
      ]
    }
  }

  # GPU node group
  self_managed_node_groups = {
    gpu = {
      min_size       = 0
      max_size       = 4
      desired_size   = 0
      instance_type  = "p4d.24xlarge"
      key_name       = aws_key_pair.nodes.key_name
      capacity_type  = "SPOT"

      labels = {
        nvidia.com/gpu = "true"
        role            = "inference"
      }

      taints = [
        {
          key    = "nvidia.com/gpu"
          value  = "present"
          effect = "NO_SCHEDULE"
        }
      ]

      update_config = {
        max_unavailable_percentage = 33
      }
    }
  }

  # Cluster addons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# Kubernetes Providers
# ──────────────────────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# RDS PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"

  identifier = "${var.cluster_name}-postgres"

  engine               = "postgres"
  engine_version       = "16.1"
  family              = "postgres16"
  major_engine_version = "16"
  instance_class       = "db.r6g.2xlarge"

  allocated_storage     = 200
  max_allocated_storage = 1000
  storage_encrypted     = true
  storage_throughput    = 500

  db_name  = "rasospeak"
  username = "rasospeak_admin"
  port     = 5432

  multi_az               = true
  db_subnet_group_name    = module.vpc.database_subnet_group
  vpc_security_group_ids  = [module.security_group_rds.id]

  backup_retention_period = 30
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  deletion_protection    = true
  skip_final_snapshot    = false
  final_snapshot_identifier = "${var.cluster_name}-final-snapshot"

  parameters = [
    {
      name  = "max_connections"
      value = "1000"
    },
    {
      name  = "shared_buffers"
      value = "65536"  # 512MB for large instance
    },
    {
      name  = "effective_cache_size"
      value = "196608"  # 1.5GB
    },
    {
      name  = "maintenance_work_mem"
      value = "1638400"  # 1.5GB
    },
    {
      name  = "checkpoint_completion_target"
      value = "0.9"
    },
    {
      name  = "wal_buffers"
      value = "16384"
    },
    {
      name  = "default_statistics_target"
      value = "100"
    },
    {
      name  = "random_page_cost"
      value = "1.1"
    },
    {
      name  = "effective_io_concurrency"
      value = "200"
    },
    {
      name  = "work_mem"
      value = "16384"
    },
    {
      name  = "min_wal_size"
      value = "4096"
    },
    {
      name  = "max_wal_size"
      value = "102400"
    },
    {
      name  = "enable_pgvector"
      value = "on"
    }
  ]

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# ElastiCache Redis
# ──────────────────────────────────────────────────────────────────────────────

module "redis" {
  source  = "terraform-aws-modules/elasticache/aws"
  version = "~> 8.0"

  cluster_id           = "${var.cluster_name}-redis"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.r7g.xlarge"
  number_of_cache_nodes = 3

  availability_zones    = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  subnet_group_name    = module.vpc.database_subnet_group
  security_group_ids    = [module.security_group_redis.id]

  auto_minimal_version_seeding = true

  cluster_mode = {
    num_replicas_per_node_group = 2
    # Replicas are spread across AZs
  }

  at_rest_encryption_enabled = true
  transit_encryption_enabled  = true
  auth_token_enabled          = true

  auto_upgrade                = true
  maintenance_window          = "mon:04:00-mon:05:00"

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# Security Groups
# ──────────────────────────────────────────────────────────────────────────────

module "security_group_rds" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "~> 5.0"

  name        = "${var.cluster_name}-rds"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = module.vpc.vpc_id

  ingress = [
    {
      from_port   = 5432
      to_port     = 5432
      protocol    = "tcp"
      description = "PostgreSQL from EKS nodes"
      cidr_blocks = [module.vpc.vpc_cidr_block]
    }
  ]

  egress = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
  ]

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

module "security_group_redis" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "~> 5.0"

  name        = "${var.cluster_name}-redis"
  description = "Security group for ElastiCache Redis"
  vpc_id      = module.vpc.vpc_id

  ingress = [
    {
      from_port   = 6379
      to_port     = 6379
      protocol    = "tcp"
      description = "Redis from EKS nodes"
      cidr_blocks = [module.vpc.vpc_cidr_block]
    }
  ]

  egress = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
  ]

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# ECR Repositories
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "agent_runtime" {
  name         = "${var.cluster_name}/agent-runtime"
  image_scanning_configuration = {
    scan_on_push = true
  }
  image_tag_mutability = "MUTABLE"
}

resource "aws_ecr_repository" "memory_service" {
  name         = "${var.cluster_name}/memory-service"
  image_scanning_configuration = {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "llm_gateway" {
  name         = "${var.cluster_name}/llm-gateway"
  image_scanning_configuration = {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "api_gateway" {
  name         = "${var.cluster_name}/api-gateway"
  image_scanning_configuration = {
    scan_on_push = true
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# S3 Buckets
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "documents" {
  bucket = "${var.cluster_name}-documents-${data.aws_caller_identity.current.account_id}"

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

resource "aws_s3_bucket" "backups" {
  bucket = "${var.cluster_name}-backups-${data.aws_caller_identity.current.account_id}"

  tags = {
    Environment = var.environment
    Project     = "rasospeak"
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# IAM Roles
# ──────────────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "eks_worker_assume_role_policy" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# SSH Key for GPU Nodes
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_key_pair" "nodes" {
  key_name   = "${var.cluster_name}-nodes"
  public_key = var.ssh_public_key
}
