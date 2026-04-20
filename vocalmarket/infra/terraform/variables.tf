variable "region" {
  description = "AWS region — Cape Town"
  type        = string
  default     = "af-south-1"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "vocalmarket-prod"
}

variable "cluster_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.31"
}

variable "general_node_instance_type" {
  description = "EC2 instance type for general workloads"
  type        = string
  default     = "m6i.xlarge"  # 4 vCPU / 16 GB — good balance for af-south-1 availability
}

variable "gpu_node_instance_type" {
  description = "EC2 instance type for Whisper GPU nodes"
  type        = string
  default     = "g4dn.xlarge"  # 1x T4 GPU / 4 vCPU / 16 GB
}

variable "general_node_min" {
  type    = number
  default = 3
}

variable "general_node_max" {
  type    = number
  default = 12
}

variable "general_node_desired" {
  type    = number
  default = 3
}

variable "gpu_node_min" {
  type    = number
  default = 1
}

variable "gpu_node_max" {
  type    = number
  default = 4
}

variable "gpu_node_desired" {
  type    = number
  default = 1
}

variable "rds_instance_class" {
  description = "RDS instance — PostgreSQL 16 with pgvector"
  type        = string
  default     = "db.r6g.large"  # 2 vCPU / 16 GB — ARM Graviton for cost savings
}

variable "rds_allocated_storage_gb" {
  type    = number
  default = 200
}

variable "elasticache_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "VocalMarket"
    Environment = "production"
    Region      = "af-south-1"
    ManagedBy   = "Terraform"
  }
}
