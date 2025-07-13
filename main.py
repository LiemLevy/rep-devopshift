import os
import json
import sys
from jinja2 import Template
from python_terraform import Terraform, IsFlagged
import boto3
from botocore.exceptions import ClientError

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

TERRAFORM_TEMPLATE = """
provider "aws" {
  region = "{{ region }}"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  count = 2
  vpc_id = aws_vpc.main.id
  cidr_block = "10.0.${count.index}.0/24"
  availability_zone = element(["us-east-1a", "us-east-1b"], count.index)
}

resource "aws_security_group" "lb_sg" {
  name        = "lb_security_group"
  description = "Allow HTTP inbound traffic"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web_server" {
  ami           = "{{ ami }}"
  instance_type = "{{ instance_type }}"
  availability_zone = "{{ availability_zone }}"

  tags = {
    Name = "WebServer"
  }
}

resource "aws_lb" "application_lb" {
  name               = "{{ load_balancer_name }}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb_sg.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "web_target_group" {
  name     = "web-target-group"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
}

resource "aws_lb_listener" "http_listener" {
  load_balancer_arn = aws_lb.application_lb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web_target_group.arn
  }
}

resource "aws_lb_target_group_attachment" "web_instance_attachment" {
  target_group_arn = aws_lb_target_group.web_target_group.arn
  target_id        = aws_instance.web_server.id
}

output "instance_id" {
  value = aws_instance.web_server.id
}

output "load_balancer_dns" {
  value = aws_lb.application_lb.dns_name
}
"""

class AWSInfrastructureDeployer:
    def __init__(self):
        self.terraform_dir = "./terraform"
        self.tf_file = os.path.join(self.terraform_dir, "main.tf")
        self.region = ALLOWED_REGION
        self.terraform = Terraform(working_dir=self.terraform_dir)
        self.boto_ec2 = None
        self.boto_elbv2 = None
        self.instance_id = None
        self.load_balancer_dns = None
        self.public_ip = None

    def get_user_input(self):
        try:
            print("Select AMI:")
            print("1) Ubuntu 20.04 LTS")
            print("2) Amazon Linux 2")
            ami_choice = input("Choose (1 or 2): ").strip()
            if ami_choice == "1":
                self.ami = AMI_OPTIONS["ubuntu"]
            elif ami_choice == "2":
                self.ami = AMI_OPTIONS["amazon_linux"]
            else:
                print("Invalid choice, defaulting to Ubuntu")
                self.ami = AMI_OPTIONS["ubuntu"]

            print("Select instance type:")
            print("1) t3.small")
            print("2) t3.medium")
            inst_choice = input("Choose (1 or 2): ").strip()
            if inst_choice == "1":
                self.instance_type = INSTANCE_TYPES["t3.small"]
            elif inst_choice == "2":
                self.instance_type = INSTANCE_TYPES["t3.medium"]
            else:
                print("Invalid choice, defaulting to t3.small")
                self.instance_type = INSTANCE_TYPES["t3.small"]

            region_input = input(f"Enter AWS region (default {ALLOWED_REGION}): ").strip()
            if region_input != "" and region_input != ALLOWED_REGION:
                print(f"Region '{region_input}' is not allowed. Defaulting to {ALLOWED_REGION}")
                self.region = ALLOWED_REGION
            else:
                self.region = region_input or ALLOWED_REGION

            print(f"Select Availability Zone in region {self.region}:")
            for i, az in enumerate(AVAILABILITY_ZONES, 1):
                print(f"{i}) {az}")
            az_choice = input("Choose (1 or 2): ").strip()
            if az_choice == "1":
                self.availability_zone = AVAILABILITY_ZONES[0]
            elif az_choice == "2":
                self.availability_zone = AVAILABILITY_ZONES[1]
            else:
                print(f"Invalid choice, defaulting to {AVAILABILITY_ZONES[0]}")
                self.availability_zone = AVAILABILITY_ZONES[0]

            alb_name = input("Enter Application Load Balancer name: ").strip()
            if alb_name == "":
                alb_name = "my-application-lb"
                print(f"No name entered, defaulting to {alb_name}")
            self.load_balancer_name = alb_name
        except Exception as e:
            print(f"Error getting user input: {e}")
            sys.exit(1)

    def generate_terraform_file(self):
        try:
            os.makedirs(self.terraform_dir, exist_ok=True)
            template = Template(TERRAFORM_TEMPLATE)
            tf_content = template.render(
                region=self.region,
                ami=self.ami,
                instance_type=self.instance_type,
                availability_zone=self.availability_zone,
                load_balancer_name=self.load_balancer_name
            )
            with open(self.tf_file, "w", encoding="utf-8") as f:
                f.write(tf_content)
            print(f"Terraform file created successfully: {self.tf_file}")
        except Exception as e:
            print(f"Error creating Terraform file: {e}")
            sys.exit(1)

    def run_terraform(self):
        try:
            print("Running terraform init...")
            return_code, stdout, stderr = self.terraform.init(capture_output=False)
            if return_code != 0:
                print(f"terraform init failed: {stderr}")
                sys.exit(1)

            print("Running terraform plan...")
            return_code, stdout, stderr = self.terraform.plan(capture_output=False)
            if return_code != 0:
                print(f"terraform plan failed: {stderr}")
                sys.exit(1)

            print("Running terraform apply...")
            return_code, stdout, stderr = self.terraform.apply(skip_plan=True, capture_output=False, no_color=IsFlagged)
            if return_code != 0:
                print(f"terraform apply failed: {stderr}")
                sys.exit(1)

            output = self.terraform.output(json=IsFlagged)
            if 'instance_id' in output and 'load_balancer_dns' in output:
                self.instance_id = output['instance_id']['value']
                self.load_balancer_dns = output['load_balancer_dns']['value']
            else:
                print("Terraform outputs not found, will attempt to get data via boto3")
        except FileNotFoundError:
            print("Error: Terraform executable not found. Please install Terraform and ensure 'terraform' is in your PATH.")
            sys.exit(1)
        except Exception as e:
            print(f"Error running Terraform: {e}")
            sys.exit(1)

    def setup_boto_clients(self):
        try:
            self.boto_ec2 = boto3.client("ec2", region_name=self.region)
            self.boto_elbv2 = boto3.client("elbv2", region_name=self.region)
        except Exception as e:
            print(f"Error setting up boto3 clients: {e}")
            sys.exit(1)

    def validate_aws_resources(self):
        try:
            # Validate EC2 Instance
            if not self.instance_id:
                response = self.boto_ec2.describe_instances(
                    Filters=[{"Name": "tag:Name", "Values": ["WebServer"]}]
                )
                reservations = response.get("Reservations", [])
                if not reservations:
                    print("No EC2 instance found with tag 'WebServer'")
                    sys.exit(1)
                instance = reservations[0]["Instances"][0]
                self.instance_id = instance["InstanceId"]
            else:
                instance_resp = self.boto_ec2.describe_instances(InstanceIds=[self.instance_id])
                instance = instance_resp["Reservations"][0]["Instances"][0]

            state = instance["State"]["Name"]
            if state != "running":
                print(f"Instance is in state '{state}', expected 'running'")
                sys.exit(1)

            self.public_ip = instance.get("PublicIpAddress", None)
            if not self.public_ip:
                print("No public IP found for the instance")
                sys.exit(1)

            # Validate ALB
            if not self.load_balancer_dns:
                lbs = self.boto_elbv2.describe_load_balancers()["LoadBalancers"]
                alb = next((lb for lb in lbs if lb["LoadBalancerName"] == self.load_balancer_name), None)
                if alb is None:
                    print(f"Load Balancer '{self.load_balancer_name}' not found in AWS")
                    sys.exit(1)
                self.load_balancer_dns = alb["DNSName"]

            print("AWS resources validated successfully!")
        except ClientError as e:
            print(f"boto3 client error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error validating AWS resources: {e}")
            sys.exit(1)

    def save_validation_json(self):
        data = {
            "instance_id": self.instance_id,
            "instance_state": "running",
            "public_ip": self.public_ip,
            "load_balancer_dns": self.load_balancer_dns
        }
        try:
            with open("aws_validation.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            print("Validation data saved to aws_validation.json")
        except Exception as e:
            print(f"Error saving validation JSON: {e}")

    def run(self):
        self.get_user_input()
        self.generate_terraform_file()
        self.run_terraform()
        self.setup_boto_clients()
        self.validate_aws_resources()
        self.save_validation_json()

if __name__ == "__main__":
    deployer = AWSInfrastructureDeployer()
    deployer.run()
import os
import json
import sys
from jinja2 import Template
from python_terraform import Terraform, IsFlagged
import boto3
from botocore.exceptions import ClientError

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

TERRAFORM_TEMPLATE = """
provider "aws" {
  region = "{{ region }}"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  count = 2
  vpc_id = aws_vpc.main.id
  cidr_block = "10.0.${count.index}.0/24"
  availability_zone = element(["us-east-1a", "us-east-1b"], count.index)
}

resource "aws_security_group" "lb_sg" {
  name        = "lb_security_group"
  description = "Allow HTTP inbound traffic"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web_server" {
  ami           = "{{ ami }}"
  instance_type = "{{ instance_type }}"
  availability_zone = "{{ availability_zone }}"

  tags = {
    Name = "WebServer"
  }
}

resource "aws_lb" "application_lb" {
  name               = "{{ load_balancer_name }}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb_sg.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "web_target_group" {
  name     = "web-target-group"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
}

resource "aws_lb_listener" "http_listener" {
  load_balancer_arn = aws_lb.application_lb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web_target_group.arn
  }
}

resource "aws_lb_target_group_attachment" "web_instance_attachment" {
  target_group_arn = aws_lb_target_group.web_target_group.arn
  target_id        = aws_instance.web_server.id
}

output "instance_id" {
  value = aws_instance.web_server.id
}

output "load_balancer_dns" {
  value = aws_lb.application_lb.dns_name
}
"""

class AWSInfrastructureDeployer:
    def __init__(self):
        self.terraform_dir = "./terraform"
        self.tf_file = os.path.join(self.terraform_dir, "main.tf")
        self.region = ALLOWED_REGION
        self.terraform = Terraform(working_dir=self.terraform_dir)
        self.boto_ec2 = None
        self.boto_elbv2 = None
        self.instance_id = None
        self.load_balancer_dns = None
        self.public_ip = None

    def get_user_input(self):
        try:
            print("Select AMI:")
            print("1) Ubuntu 20.04 LTS")
            print("2) Amazon Linux 2")
            ami_choice = input("Choose (1 or 2): ").strip()
            if ami_choice == "1":
                self.ami = AMI_OPTIONS["ubuntu"]
            elif ami_choice == "2":
                self.ami = AMI_OPTIONS["amazon_linux"]
            else:
                print("Invalid choice, defaulting to Ubuntu")
                self.ami = AMI_OPTIONS["ubuntu"]

            print("Select instance type:")
            print("1) t3.small")
            print("2) t3.medium")
            inst_choice = input("Choose (1 or 2): ").strip()
            if inst_choice == "1":
                self.instance_type = INSTANCE_TYPES["t3.small"]
            elif inst_choice == "2":
                self.instance_type = INSTANCE_TYPES["t3.medium"]
            else:
                print("Invalid choice, defaulting to t3.small")
                self.instance_type = INSTANCE_TYPES["t3.small"]

            region_input = input(f"Enter AWS region (default {ALLOWED_REGION}): ").strip()
            if region_input != "" and region_input != ALLOWED_REGION:
                print(f"Region '{region_input}' is not allowed. Defaulting to {ALLOWED_REGION}")
                self.region = ALLOWED_REGION
            else:
                self.region = region_input or ALLOWED_REGION

            print(f"Select Availability Zone in region {self.region}:")
            for i, az in enumerate(AVAILABILITY_ZONES, 1):
                print(f"{i}) {az}")
            az_choice = input("Choose (1 or 2): ").strip()
            if az_choice == "1":
                self.availability_zone = AVAILABILITY_ZONES[0]
            elif az_choice == "2":
                self.availability_zone = AVAILABILITY_ZONES[1]
            else:
                print(f"Invalid choice, defaulting to {AVAILABILITY_ZONES[0]}")
                self.availability_zone = AVAILABILITY_ZONES[0]

            alb_name = input("Enter Application Load Balancer name: ").strip()
            if alb_name == "":
                alb_name = "my-application-lb"
                print(f"No name entered, defaulting to {alb_name}")
            self.load_balancer_name = alb_name
        except Exception as e:
            print(f"Error getting user input: {e}")
            sys.exit(1)

    def generate_terraform_file(self):
        try:
            os.makedirs(self.terraform_dir, exist_ok=True)
            template = Template(TERRAFORM_TEMPLATE)
            tf_content = template.render(
                region=self.region,
                ami=self.ami,
                instance_type=self.instance_type,
                availability_zone=self.availability_zone,
                load_balancer_name=self.load_balancer_name
            )
            with open(self.tf_file, "w", encoding="utf-8") as f:
                f.write(tf_content)
            print(f"Terraform file created successfully: {self.tf_file}")
        except Exception as e:
            print(f"Error creating Terraform file: {e}")
            sys.exit(1)

    def run_terraform(self):
        try:
            print("Running terraform init...")
            return_code, stdout, stderr = self.terraform.init(capture_output=False)
            if return_code != 0:
                print(f"terraform init failed: {stderr}")
                sys.exit(1)

            print("Running terraform plan...")
            return_code, stdout, stderr = self.terraform.plan(capture_output=False)
            if return_code != 0:
                print(f"terraform plan failed: {stderr}")
                sys.exit(1)

            print("Running terraform apply...")
            return_code, stdout, stderr = self.terraform.apply(skip_plan=True, capture_output=False, no_color=IsFlagged)
            if return_code != 0:
                print(f"terraform apply failed: {stderr}")
                sys.exit(1)

            output = self.terraform.output(json=IsFlagged)
            if 'instance_id' in output and 'load_balancer_dns' in output:
                self.instance_id = output['instance_id']['value']
                self.load_balancer_dns = output['load_balancer_dns']['value']
            else:
                print("Terraform outputs not found, will attempt to get data via boto3")
        except FileNotFoundError:
            print("Error: Terraform executable not found. Please install Terraform and ensure 'terraform' is in your PATH.")
            sys.exit(1)
        except Exception as e:
            print(f"Error running Terraform: {e}")
            sys.exit(1)

    def setup_boto_clients(self):
        try:
            self.boto_ec2 = boto3.client("ec2", region_name=self.region)
            self.boto_elbv2 = boto3.client("elbv2", region_name=self.region)
        except Exception as e:
            print(f"Error setting up boto3 clients: {e}")
            sys.exit(1)

    def validate_aws_resources(self):
        try:
            # Validate EC2 Instance
            if not self.instance_id:
                response = self.boto_ec2.describe_instances(
                    Filters=[{"Name": "tag:Name", "Values": ["WebServer"]}]
                )
                reservations = response.get("Reservations", [])
                if not reservations:
                    print("No EC2 instance found with tag 'WebServer'")
                    sys.exit(1)
                instance = reservations[0]["Instances"][0]
                self.instance_id = instance["InstanceId"]
            else:
                instance_resp = self.boto_ec2.describe_instances(InstanceIds=[self.instance_id])
                instance = instance_resp["Reservations"][0]["Instances"][0]

            state = instance["State"]["Name"]
            if state != "running":
                print(f"Instance is in state '{state}', expected 'running'")
                sys.exit(1)

            self.public_ip = instance.get("PublicIpAddress", None)
            if not self.public_ip:
                print("No public IP found for the instance")
                sys.exit(1)

            # Validate ALB
            if not self.load_balancer_dns:
                lbs = self.boto_elbv2.describe_load_balancers()["LoadBalancers"]
                alb = next((lb for lb in lbs if lb["LoadBalancerName"] == self.load_balancer_name), None)
                if alb is None:
                    print(f"Load Balancer '{self.load_balancer_name}' not found in AWS")
                    sys.exit(1)
                self.load_balancer_dns = alb["DNSName"]

            print("AWS resources validated successfully!")
        except ClientError as e:
            print(f"boto3 client error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error validating AWS resources: {e}")
            sys.exit(1)

    def save_validation_json(self):
        data = {
            "instance_id": self.instance_id,
            "instance_state": "running",
            "public_ip": self.public_ip,
            "load_balancer_dns": self.load_balancer_dns
        }
        try:
            with open("aws_validation.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            print("Validation data saved to aws_validation.json")
        except Exception as e:
            print(f"Error saving validation JSON: {e}")

    def run(self):
        self.get_user_input()
        self.generate_terraform_file()
        self.run_terraform()
        self.setup_boto_clients()
        self.validate_aws_resources()
        self.save_validation_json()

if __name__ == "__main__":
    deployer = AWSInfrastructureDeployer()
    deployer.run()
