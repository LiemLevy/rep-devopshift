"""
AWS Infrastructure Deployer
A comprehensive tool for deploying AWS infrastructure using Terraform, Jinja2, and boto3.
"""

import os
import json
import sys
import time
from typing import Dict, Optional, Tuple
from jinja2 import Template
from python_terraform import Terraform, IsFlagged
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Configuration Constants
AMI_OPTIONS = {
    "ubuntu": "ami-0c02fb55956c7d316",        # Ubuntu 20.04 LTS us-east-1
    "amazon_linux": "ami-0b898040803850657"   # Amazon Linux 2 us-east-1
}

INSTANCE_TYPES = {
    "t3.small": "t3.small",
    "t3.medium": "t3.medium"
}

AVAILABILITY_ZONES = ["us-east-1a", "us-east-1b"]
ALLOWED_REGION = "us-east-1"

# Complete Terraform Template with proper networking
TERRAFORM_TEMPLATE = """
provider "aws" {
  region = "{{ region }}"
}

# VPC Configuration
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {
    Name = "main-vpc"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  
  tags = {
    Name = "main-igw"
  }
}

# Public Subnets
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index + 1}.0/24"
  availability_zone       = element(["us-east-1a", "us-east-1b"], count.index)
  map_public_ip_on_launch = true
  
  tags = {
    Name = "public-subnet-${count.index + 1}"
  }
}

# Route Table for Public Subnets
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  
  tags = {
    Name = "public-route-table"
  }
}

# Route Table Associations
resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Security Group for EC2 Instance
resource "aws_security_group" "instance_sg" {
  name        = "instance_security_group"
  description = "Security group for EC2 instance"
  vpc_id      = aws_vpc.main.id
  
  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.lb_sg.id]
  }
  
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "instance-sg"
  }
}

# Security Group for Load Balancer
resource "aws_security_group" "lb_sg" {
  name        = "lb_security_group"
  description = "Allow HTTP inbound traffic for ALB"
  vpc_id      = aws_vpc.main.id
  
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "lb-sg"
  }
}

# EC2 Instance
resource "aws_instance" "web_server" {
  ami                    = "{{ ami }}"
  instance_type          = "{{ instance_type }}"
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.instance_sg.id]
  
  user_data = <<-EOF
    #!/bin/bash
    yum update -y
    yum install -y httpd
    systemctl start httpd
    systemctl enable httpd
    echo "<h1>Hello from $(hostname -f)</h1>" > /var/www/html/index.html
  EOF
  
  tags = {
    Name = "WebServer"
  }
}

# Application Load Balancer
resource "aws_lb" "application_lb" {
  name               = "{{ load_balancer_name }}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb_sg.id]
  subnets            = aws_subnet.public[*].id
  
  enable_deletion_protection = false
  
  tags = {
    Name = "{{ load_balancer_name }}"
  }
}

# Target Group
resource "aws_lb_target_group" "web_target_group" {
  name     = "web-target-group"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/"
    matcher             = "200"
  }
  
  tags = {
    Name = "web-target-group"
  }
}

# Target Group Attachment
resource "aws_lb_target_group_attachment" "web_instance_attachment" {
  target_group_arn = aws_lb_target_group.web_target_group.arn
  target_id        = aws_instance.web_server.id
  port             = 80
}

# Load Balancer Listener
resource "aws_lb_listener" "http_listener" {
  load_balancer_arn = aws_lb.application_lb.arn
  port              = "80"
  protocol          = "HTTP"
  
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web_target_group.arn
  }
}

# Outputs
output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.web_server.id
}

output "instance_public_ip" {
  description = "Public IP address of the EC2 instance"
  value       = aws_instance.web_server.public_ip
}

output "load_balancer_dns" {
  description = "DNS name of the load balancer"
  value       = aws_lb.application_lb.dns_name
}

output "load_balancer_arn" {
  description = "ARN of the load balancer"
  value       = aws_lb.application_lb.arn
}

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}
"""


class AWSCredentialsValidator:
    """Validates AWS credentials and permissions."""
    
    @staticmethod
    def validate_credentials(region: str) -> bool:
        """
        Validate AWS credentials and basic permissions.
        
        Args:
            region: AWS region to validate against
            
        Returns:
            bool: True if credentials are valid, False otherwise
        """
        try:
            sts_client = boto3.client('sts', region_name=region)
            sts_client.get_caller_identity()
            return True
        except (NoCredentialsError, ClientError) as e:
            print(f"AWS credentials validation failed: {e}")
            return False


class TerraformManager:
    """Manages Terraform operations."""
    
    def __init__(self, working_dir: str):
        self.working_dir = working_dir
        self.terraform = Terraform(working_dir=working_dir)
        
    def initialize(self) -> bool:
        """Initialize Terraform."""
        try:
            print("Initializing Terraform...")
            return_code, stdout, stderr = self.terraform.init(capture_output=False)
            if return_code != 0:
                print(f"Terraform init failed: {stderr}")
                return False
            print("Terraform initialized successfully!")
            return True
        except Exception as e:
            print(f"Error during Terraform initialization: {e}")
            return False
    
    def plan(self) -> bool:
        """Create Terraform plan."""
        try:
            print("Creating Terraform plan...")
            return_code, stdout, stderr = self.terraform.plan(capture_output=False)
            if return_code != 0:
                print(f"Terraform plan failed: {stderr}")
                return False
            print("Terraform plan created successfully!")
            return True
        except Exception as e:
            print(f"Error during Terraform planning: {e}")
            return False
    
    def apply(self) -> Tuple[bool, Dict]:
        """Apply Terraform configuration."""
        try:
            print("Applying Terraform configuration...")
            return_code, stdout, stderr = self.terraform.apply(
                skip_plan=True, 
                capture_output=False, 
                no_color=IsFlagged
            )
            if return_code != 0:
                print(f"Terraform apply failed: {stderr}")
                return False, {}
            
            # Get outputs
            outputs = self.terraform.output(json=IsFlagged)
            print("Terraform applied successfully!")
            return True, outputs
        except Exception as e:
            print(f"Error during Terraform apply: {e}")
            return False, {}
    
    def destroy(self) -> bool:
        """Destroy Terraform resources."""
        try:
            print("Destroying Terraform resources...")
            return_code, stdout, stderr = self.terraform.destroy(
                capture_output=False, 
                no_color=IsFlagged,
                auto_approve=True
            )
            if return_code != 0:
                print(f"Terraform destroy failed: {stderr}")
                return False
            print("Resources destroyed successfully!")
            return True
        except Exception as e:
            print(f"Error during Terraform destroy: {e}")
            return False


class AWSResourceValidator:
    """Validates AWS resources using boto3."""
    
    def __init__(self, region: str):
        self.region = region
        self.ec2_client = boto3.client('ec2', region_name=region)
        self.elbv2_client = boto3.client('elbv2', region_name=region)
    
    def validate_ec2_instance(self, instance_id: str) -> Dict:
        """
        Validate EC2 instance and return its details.
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            Dict: Instance details including state and public IP
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            
            instance_details = {
                'instance_id': instance_id,
                'state': instance['State']['Name'],
                'public_ip': instance.get('PublicIpAddress'),
                'private_ip': instance.get('PrivateIpAddress'),
                'instance_type': instance['InstanceType'],
                'availability_zone': instance['Placement']['AvailabilityZone']
            }
            
            print(f"EC2 Instance {instance_id} is in state: {instance_details['state']}")
            return instance_details
            
        except ClientError as e:
            print(f"Error validating EC2 instance: {e}")
            return {}
    
    def validate_load_balancer(self, lb_dns: str) -> Dict:
        """
        Validate Application Load Balancer and return its details.
        
        Args:
            lb_dns: Load balancer DNS name
            
        Returns:
            Dict: Load balancer details including state
        """
        try:
            response = self.elbv2_client.describe_load_balancers()
            
            for lb in response['LoadBalancers']:
                if lb['DNSName'] == lb_dns:
                    lb_details = {
                        'dns_name': lb['DNSName'],
                        'state': lb['State']['Code'],
                        'type': lb['Type'],
                        'scheme': lb['Scheme'],
                        'vpc_id': lb['VpcId']
                    }
                    print(f"Load Balancer {lb_dns} is in state: {lb_details['state']}")
                    return lb_details
            
            print(f"Load Balancer with DNS {lb_dns} not found")
            return {}
            
        except ClientError as e:
            print(f"Error validating Load Balancer: {e}")
            return {}


class AWSInfrastructureDeployer:
    """Main class for AWS infrastructure deployment."""
    
    def __init__(self):
        self.terraform_dir = "./terraform"
        self.tf_file = os.path.join(self.terraform_dir, "main.tf")
        self.region = ALLOWED_REGION
        self.deployment_config = {}
        self.terraform_outputs = {}
        self.validation_results = {}
        
    def get_user_input(self) -> bool:
        """
        Get user input for deployment configuration.
        
        Returns:
            bool: True if input is valid, False otherwise
        """
        try:
            print("=" * 60)
            print("AWS Infrastructure Deployment Configuration")
            print("=" * 60)
            
            # AMI Selection
            print("\nSelect AMI:")
            print("1) Ubuntu 20.04 LTS")
            print("2) Amazon Linux 2")
            
            while True:
                ami_choice = input("Choose (1 or 2): ").strip()
                if ami_choice in ["1", "2"]:
                    break
                print("Invalid choice. Please enter 1 or 2.")
            
            self.deployment_config['ami'] = (
                AMI_OPTIONS["ubuntu"] if ami_choice == "1" 
                else AMI_OPTIONS["amazon_linux"]
            )
            
            # Instance Type Selection
            print("\nSelect instance type:")
            print("1) t3.small")
            print("2) t3.medium")
            
            while True:
                inst_choice = input("Choose (1 or 2): ").strip()
                if inst_choice in ["1", "2"]:
                    break
                print("Invalid choice. Please enter 1 or 2.")
            
            self.deployment_config['instance_type'] = (
                INSTANCE_TYPES["t3.small"] if inst_choice == "1" 
                else INSTANCE_TYPES["t3.medium"]
            )
            
            # Region Validation
            region_input = input(f"\nEnter AWS region (default {ALLOWED_REGION}): ").strip()
            if region_input and region_input != ALLOWED_REGION:
                print(f"Region '{region_input}' is not allowed. Using {ALLOWED_REGION}")
            self.deployment_config['region'] = ALLOWED_REGION
            
            # Availability Zone Selection
            print(f"\nSelect Availability Zone in region {ALLOWED_REGION}:")
            for i, az in enumerate(AVAILABILITY_ZONES, 1):
                print(f"{i}) {az}")
            
            while True:
                az_choice = input("Choose (1 or 2): ").strip()
                if az_choice in ["1", "2"]:
                    break
                print("Invalid choice. Please enter 1 or 2.")
            
            self.deployment_config['availability_zone'] = (
                AVAILABILITY_ZONES[0] if az_choice == "1" 
                else AVAILABILITY_ZONES[1]
            )
            
            # Load Balancer Name
            while True:
                alb_name = input("\nEnter Application Load Balancer name: ").strip()
                if alb_name and len(alb_name) <= 32:
                    break
                print("Please enter a valid ALB name (max 32 characters).")
            
            self.deployment_config['load_balancer_name'] = alb_name
            
            print("\n" + "=" * 60)
            print("Configuration Summary:")
            print("=" * 60)
            for key, value in self.deployment_config.items():
                print(f"{key.replace('_', ' ').title()}: {value}")
            print("=" * 60)
            
            return True
            
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return False
        except Exception as e:
            print(f"Error getting user input: {e}")
            return False
    
    def generate_terraform_file(self) -> bool:
        """
        Generate Terraform configuration file using Jinja2.
        
        Returns:
            bool: True if file generated successfully, False otherwise
        """
        try:
            # Create terraform directory
            os.makedirs(self.terraform_dir, exist_ok=True)
            
            # Render template
            template = Template(TERRAFORM_TEMPLATE)
            tf_content = template.render(**self.deployment_config)
            
            # Write to file
            with open(self.tf_file, "w", encoding="utf-8") as f:
                f.write(tf_content)
            
            print(f"Terraform file generated successfully: {self.tf_file}")
            return True
            
        except Exception as e:
            print(f"Error generating Terraform file: {e}")
            return False
    
    def deploy_infrastructure(self) -> bool:
        """
        Deploy infrastructure using Terraform.
        
        Returns:
            bool: True if deployment successful, False otherwise
        """
        try:
            # Check if Terraform is installed
            if not os.system("terraform --version > /dev/null 2>&1") == 0:
                print("Error: Terraform is not installed or not in PATH.")
                return False
            
            # Initialize Terraform manager
            tf_manager = TerraformManager(self.terraform_dir)
            
            # Initialize Terraform
            if not tf_manager.initialize():
                return False
            
            # Create plan
            if not tf_manager.plan():
                return False
            
            # Apply configuration
            success, outputs = tf_manager.apply()
            if not success:
                return False
            
            # Store outputs
            self.terraform_outputs = outputs
            print("Infrastructure deployed successfully!")
            return True
            
        except Exception as e:
            print(f"Error deploying infrastructure: {e}")
            return False
    
    def validate_deployment(self) -> bool:
        """
        Validate deployed resources using boto3.
        
        Returns:
            bool: True if validation successful, False otherwise
        """
        try:
            # Validate AWS credentials
            if not AWSCredentialsValidator.validate_credentials(self.region):
                return False
            
            # Initialize validator
            validator = AWSResourceValidator(self.region)
            
            # Get instance ID and LB DNS from outputs
            instance_id = self.terraform_outputs.get('instance_id', {}).get('value')
            lb_dns = self.terraform_outputs.get('load_balancer_dns', {}).get('value')
            
            if not instance_id or not lb_dns:
                print("Error: Missing Terraform outputs for validation")
                return False
            
            # Validate EC2 instance
            print("Validating EC2 instance...")
            instance_details = validator.validate_ec2_instance(instance_id)
            if not instance_details:
                return False
            
            # Validate Load Balancer
            print("Validating Application Load Balancer...")
            lb_details = validator.validate_load_balancer(lb_dns)
            if not lb_details:
                return False
            
            # Store validation results
            self.validation_results = {
                'instance_id': instance_details['instance_id'],
                'instance_state': instance_details['state'],
                'public_ip': instance_details['public_ip'],
                'load_balancer_dns': lb_details['dns_name'],
                'load_balancer_state': lb_details['state'],
                'validation_timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            print("Deployment validation completed successfully!")
            return True
            
        except Exception as e:
            print(f"Error validating deployment: {e}")
            return False
    
    def save_validation_results(self) -> bool:
        """
        Save validation results to JSON file.
        
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            with open("aws_validation.json", "w", encoding="utf-8") as f:
                json.dump(self.validation_results, f, indent=4)
            
            print("Validation results saved to aws_validation.json")
            return True
            
        except Exception as e:
            print(f"Error saving validation results: {e}")
            return False
    
    def cleanup_resources(self) -> bool:
        """
        Clean up deployed resources.
        
        Returns:
            bool: True if cleanup successful, False otherwise
        """
        try:
            confirm = input("\nDo you want to destroy the deployed resources? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("Cleanup cancelled.")
                return True
            
            tf_manager = TerraformManager(self.terraform_dir)
            return tf_manager.destroy()
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
            return False
    
    def run(self) -> bool:
        """
        Main execution method.
        
        Returns:
            bool: True if execution successful, False otherwise
        """
        try:
            print("AWS Infrastructure Deployer")
            print("=" * 60)
            
            # Get user input
            if not self.get_user_input():
                return False
            
            # Generate Terraform file
            if not self.generate_terraform_file():
                return False
            
            # Deploy infrastructure
            if not self.deploy_infrastructure():
                return False
            
            # Validate deployment
            if not self.validate_deployment():
                return False
            
            # Save validation results
            if not self.save_validation_results():
                return False
            
            print("\n" + "=" * 60)
            print("Deployment Summary:")
            print("=" * 60)
            print(f"Instance ID: {self.validation_results.get('instance_id')}")
            print(f"Instance State: {self.validation_results.get('instance_state')}")
            print(f"Public IP: {self.validation_results.get('public_ip')}")
            print(f"Load Balancer DNS: {self.validation_results.get('load_balancer_dns')}")
            print(f"Load Balancer State: {self.validation_results.get('load_balancer_state')}")
            print("=" * 60)
            
            # Offer cleanup
            self.cleanup_resources()
            
            return True
            
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False


def main():
    """Main entry point."""
    try:
        deployer = AWSInfrastructureDeployer()
        success = deployer.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
    
