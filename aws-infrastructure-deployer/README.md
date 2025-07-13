AWS Infrastructure Deployer
A comprehensive Python-based tool for deploying AWS infrastructure using Terraform, Jinja2, and boto3. This tool automates the deployment of an EC2 instance with an Application Load Balancer (ALB) and validates the deployment using AWS APIs.
Features

Dynamic Terraform Configuration: Uses Jinja2 templates to generate Terraform files based on user input
Complete Networking Setup: Includes VPC, subnets, internet gateway, route tables, and security groups
Terraform Integration: Automated Terraform initialization, planning, and deployment
AWS Validation: Validates deployed resources using boto3
Error Handling: Comprehensive error handling and user input validation
Clean Code Structure: Object-oriented design with modular components
Resource Cleanup: Built-in capability to destroy deployed resources

Prerequisites
Required Software

Python 3.7+
Terraform (latest version)
AWS CLI configured with appropriate credentials

Python Dependencies
bashpip install jinja2 python-terraform boto3
AWS Permissions
Your AWS credentials must have permissions for:

EC2 (instances, VPCs, subnets, security groups)
ELB v2 (Application Load Balancers)
IAM (for role assumptions if needed)

Project Structure
aws-infrastructure-deployer/
├── main.py                    # Main deployment script
├── terraform/                 # Generated Terraform files
│   └── main.tf               # Generated Terraform configuration
├── aws_validation.json        # Validation results
└── README.md                 # This file
Usage
Basic Usage
bashpython main.py
Interactive Configuration
The script will prompt you for:

AMI Selection:

Ubuntu 20.04 LTS
Amazon Linux 2


Instance Type:

t3.small
t3.medium


Region: Only us-east-1 is allowed (as per requirements)
Availability Zone:

us-east-1a
us-east-1b


Load Balancer Name: Custom name for your ALB

Example Session
AWS Infrastructure Deployment Configuration
============================================================

Select AMI:
1) Ubuntu 20.04 LTS
2) Amazon Linux 2
Choose (1 or 2): 1

Select instance type:
1) t3.small
2) t3.medium
Choose (1 or 2): 1

Enter AWS region (default us-east-1): 

Select Availability Zone in region us-east-1:
1) us-east-1a
2) us-east-1b
Choose (1 or 2): 1

Enter Application Load Balancer name: my-test-alb
Architecture
Infrastructure Components
The tool deploys the following AWS resources:

VPC: 10.0.0.0/16 CIDR block
Public Subnets: Two subnets in different AZs
Internet Gateway: For public internet access
Route Tables: Routing configuration for public subnets
Security Groups:

ALB security group (port 80 inbound)
EC2 security group (port 80 from ALB, port 22 from internet)


EC2 Instance: Web server with Apache httpd
Application Load Balancer: Routes traffic to EC2 instance
Target Group: Health checks and routing configuration

Code Architecture
The code is structured using object-oriented principles:

AWSCredentialsValidator: Validates AWS credentials
TerraformManager: Handles all Terraform operations
AWSResourceValidator: Validates deployed resources using boto3
AWSInfrastructureDeployer: Main orchestrator class

Generated Files
Terraform Configuration (terraform/main.tf)
Complete Terraform configuration including:

Provider configuration
VPC and networking resources
Security groups
EC2 instance with user data
Application Load Balancer setup
Outputs for validation

Validation Results (aws_validation.json)
json{
    "instance_id": "i-0123456789abcdef0",
    "instance_state": "running",
    "public_ip": "3.92.102.45",
    "load_balancer_dns": "my-test-alb-123456.us-east-1.elb.amazonaws.com",
    "load_balancer_state": "active",
    "validation_timestamp": "2024-01-15 10:30:45"
}
Error Handling
The tool includes comprehensive error handling for:

Missing AWS credentials
Invalid user input
Terraform execution failures
AWS API errors
Resource validation failures

Security Features

Network Security: Proper security group configuration
Access Control: EC2 instance only accessible from ALB
Public Access: Load balancer accessible from internet
SSH Access: SSH port 22 available for management

Cleanup
The script automatically offers to clean up resources after deployment:
Do you want to destroy the deployed resources? (yes/no): yes
You can also manually destroy resources:
bashcd terraform
terraform destroy
Troubleshooting
Common Issues

Terraform not found:

Ensure Terraform is installed and in PATH
Check with: terraform --version


AWS credentials not configured:

Configure AWS CLI: aws configure
Or set environment variables


Permission errors:

Ensure AWS credentials have required permissions
Check IAM policies


Resource limits:

Check AWS service limits
Ensure sufficient quota for resources



Validation Failures
If validation fails, check:

AWS region settings
Resource naming conflicts
Service availability

Customization
Modifying AMI Options
Edit the AMI_OPTIONS dictionary in the script:
pythonAMI_OPTIONS = {
    "ubuntu": "ami-0c02fb55956c7d316",
    "amazon_linux": "ami-0b898040803850657",
    "custom": "ami-your-custom-ami"
}
Adding Instance Types
Modify the INSTANCE_TYPES dictionary:
pythonINSTANCE_TYPES = {
    "t3.small": "t3.small",
    "t3.medium": "t3.medium",
    "t3.large": "t3.large"
}
Extending Terraform Template
The Terraform template can be extended to include additional resources by modifying the TERRAFORM_TEMPLATE string.
Best Practices

Always test in a development environment first
Review generated Terraform files before deployment
Monitor AWS costs during deployment
Clean up resources after testing
Keep AWS credentials secure
