variable "name" {
  description = "Name prefix for every resource."
  type        = string
  default     = "boomerang"
}

variable "region" {
  description = "AWS region. Must be one where the Bedrock models you use are available."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.small"
}

variable "allowed_cidr" {
  description = "CIDR allowed to reach the app ports. Set this to your own IP (e.g. 203.0.113.4/32)."
  type        = string

  validation {
    condition     = var.allowed_cidr != "0.0.0.0/0"
    error_message = "Refusing to expose the app to the whole internet. Use your own IP, or put an ALB in front."
  }
}
