# Terraform configuration for FACEIT Telegram Bot infrastructure on DigitalOcean

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
  
  backend "s3" {
    endpoint                    = "nyc3.digitaloceanspaces.com"
    region                      = "us-east-1"
    key                        = "terraform/faceit-bot.tfstate"
    bucket                     = "faceit-bot-terraform"
    skip_credentials_validation = true
    skip_metadata_api_check   = true
  }
}

provider "digitalocean" {
  token = var.do_token
}

# Variables
variable "do_token" {
  description = "DigitalOcean API Token"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment name (staging or production)"
  type        = string
}

variable "region" {
  description = "DigitalOcean region"
  type        = string
  default     = "nyc3"
}

variable "ssh_keys" {
  description = "SSH key fingerprints for droplet access"
  type        = list(string)
}

# Local variables
locals {
  common_tags = [
    "faceit-bot",
    var.environment,
    "terraform-managed"
  ]
  
  droplet_size = {
    staging    = "s-1vcpu-1gb"
    production = "s-1vcpu-2gb"
  }
  
  db_size = {
    staging    = "db-s-1vcpu-1gb"
    production = "db-s-1vcpu-2gb"
  }
}

# VPC for network isolation
resource "digitalocean_vpc" "main" {
  name     = "faceit-bot-${var.environment}-vpc"
  region   = var.region
  ip_range = var.environment == "production" ? "10.10.0.0/16" : "10.20.0.0/16"
}

# Droplet for bot application
resource "digitalocean_droplet" "bot" {
  name     = "faceit-bot-${var.environment}"
  region   = var.region
  size     = local.droplet_size[var.environment]
  image    = "ubuntu-22-04-x64"
  vpc_uuid = digitalocean_vpc.main.id
  
  ssh_keys = var.ssh_keys
  tags     = local.common_tags
  
  backups           = var.environment == "production" ? true : false
  monitoring        = true
  droplet_agent     = true
  graceful_shutdown = true
  
  user_data = templatefile("${path.module}/cloud-init-${var.environment}.yaml", {
    environment = var.environment
  })
}

# Floating IP for production
resource "digitalocean_floating_ip" "bot" {
  count  = var.environment == "production" ? 1 : 0
  region = var.region
}

resource "digitalocean_floating_ip_assignment" "bot" {
  count      = var.environment == "production" ? 1 : 0
  ip_address = digitalocean_floating_ip.bot[0].ip_address
  droplet_id = digitalocean_droplet.bot.id
}

# PostgreSQL Database Cluster
resource "digitalocean_database_cluster" "postgres" {
  name       = "faceit-bot-${var.environment}-db"
  engine     = "pg"
  version    = "15"
  size       = local.db_size[var.environment]
  region     = var.region
  node_count = 1
  tags       = local.common_tags
  
  private_network_uuid = digitalocean_vpc.main.id
  
  maintenance_window {
    day  = "sunday"
    hour = "03:00:00"
  }
}

# Database firewall rules
resource "digitalocean_database_firewall" "postgres" {
  cluster_id = digitalocean_database_cluster.postgres.id
  
  rule {
    type  = "droplet"
    value = digitalocean_droplet.bot.id
  }
  
  # Allow connections from GitHub Actions for migrations
  rule {
    type  = "ip_addr"
    value = "0.0.0.0"  # Replace with actual GitHub Actions IP ranges
  }
}

# Database user for application
resource "digitalocean_database_user" "app_user" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "faceit_app"
}

# Database for application
resource "digitalocean_database_db" "app_db" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "faceit_bot"
}

# Read replica for production
resource "digitalocean_database_replica" "read_replica" {
  count      = var.environment == "production" ? 1 : 0
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "faceit-bot-${var.environment}-replica"
  size       = "db-s-1vcpu-1gb"
  region     = var.region
  tags       = local.common_tags
  
  private_network_uuid = digitalocean_vpc.main.id
}

# Spaces for backups
resource "digitalocean_spaces_bucket" "backups" {
  count  = var.environment == "production" ? 1 : 0
  name   = "faceit-bot-backups"
  region = var.region
  acl    = "private"
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    id      = "backup-retention"
    enabled = true
    
    expiration {
      days = 30
    }
    
    noncurrent_version_expiration {
      days = 7
    }
  }
}

# Firewall rules
resource "digitalocean_firewall" "bot" {
  name = "faceit-bot-${var.environment}-firewall"
  
  droplet_ids = [digitalocean_droplet.bot.id]
  
  # SSH access
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.environment == "production" ? ["YOUR_IP/32"] : ["0.0.0.0/0"]
  }
  
  # HTTP
  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0"]
  }
  
  # HTTPS
  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0"]
  }
  
  # Health check endpoint
  inbound_rule {
    protocol         = "tcp"
    port_range       = "8080"
    source_addresses = ["0.0.0.0/0"]
  }
  
  # Allow all outbound traffic
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0"]
  }
  
  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0"]
  }
  
  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0"]
  }
}

# Project to organize resources
resource "digitalocean_project" "faceit_bot" {
  name        = "FACEIT Telegram Bot - ${var.environment}"
  description = "Infrastructure for FACEIT Telegram Bot ${var.environment} environment"
  purpose     = "Web Application"
  environment = var.environment == "production" ? "Production" : "Staging"
  
  resources = concat(
    [
      digitalocean_droplet.bot.urn,
      digitalocean_database_cluster.postgres.urn,
    ],
    var.environment == "production" ? [
      digitalocean_floating_ip.bot[0].urn,
      digitalocean_spaces_bucket.backups[0].urn,
      digitalocean_database_replica.read_replica[0].urn,
    ] : []
  )
}

# Monitoring alert policies
resource "digitalocean_monitor_alert" "cpu_alert" {
  alerts {
    email = ["admin@yourdomain.com"]
  }
  window      = "5m"
  type        = "v1/insights/droplet/cpu"
  compare     = "GreaterThan"
  value       = 80
  enabled     = true
  entities    = [digitalocean_droplet.bot.id]
  description = "Alert when CPU usage exceeds 80%"
}

resource "digitalocean_monitor_alert" "memory_alert" {
  alerts {
    email = ["admin@yourdomain.com"]
  }
  window      = "5m"
  type        = "v1/insights/droplet/memory_utilization_percent"
  compare     = "GreaterThan"
  value       = 90
  enabled     = true
  entities    = [digitalocean_droplet.bot.id]
  description = "Alert when memory usage exceeds 90%"
}

# Outputs
output "droplet_ip" {
  value       = digitalocean_droplet.bot.ipv4_address
  description = "The public IP address of the droplet"
}

output "floating_ip" {
  value       = var.environment == "production" ? digitalocean_floating_ip.bot[0].ip_address : null
  description = "The floating IP address (production only)"
}

output "database_host" {
  value       = digitalocean_database_cluster.postgres.host
  sensitive   = true
  description = "The database host"
}

output "database_port" {
  value       = digitalocean_database_cluster.postgres.port
  description = "The database port"
}

output "database_uri" {
  value       = digitalocean_database_cluster.postgres.uri
  sensitive   = true
  description = "The database connection URI"
}

output "database_private_uri" {
  value       = digitalocean_database_cluster.postgres.private_uri
  sensitive   = true
  description = "The private database connection URI"
}

output "vpc_ip_range" {
  value       = digitalocean_vpc.main.ip_range
  description = "The IP range of the VPC"
}