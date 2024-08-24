import pulumi
from pulumi_aws import ec2, autoscaling, lb, iam, lambda_, cloudformation

def create_infrastructure():
    # Reference the CloudFormation stack
    vpc_stack = cloudformation.get_stack(name="ProxyVPCStack")

    # Get outputs from the CloudFormation stack
    vpc_id = vpc_stack.outputs["VpcId"]
    public_subnet_1_id = vpc_stack.outputs["PublicSubnet1"]
    public_subnet_2_id = vpc_stack.outputs["PublicSubnet2"]
    elastic_ip_allocation_ids = vpc_stack.outputs["ElasticIPs"].split(',')

    # Get VPC
    vpc = ec2.get_vpc(id=vpc_id)

    # Configuration
    config = pulumi.Config()
    instance_type = config.get("instanceType") or "t3.micro"
    key_name = config.require("keyName")
    number_of_proxies = config.get_int("numberOfProxies") or 500
    ami_id = config.require("amiId")

    # Security Group
    security_group = ec2.SecurityGroup("proxy-security-group",
        description="Security group for proxy servers",
        vpc_id=vpc.id,
        ingress=[
            ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=22, to_port=22, cidr_blocks=["0.0.0.0/0"]),
            ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=3128, to_port=3128, cidr_blocks=["0.0.0.0/0"])
        ],
        egress=[
            ec2.SecurityGroupEgressArgs(protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"])
        ])

    # Launch Template
    user_data = """#!/bin/bash
yum update -y
yum install -y squid
systemctl enable squid
systemctl start squid
"""

    launch_template = ec2.LaunchTemplate("proxy-launch-template",
        image_id=ami_id,
        instance_type=instance_type,
        key_name=key_name,
        vpc_security_group_ids=[security_group.id],
        user_data=pulumi.Output.from_input(user_data).apply(lambda ud: ud.encode().decode('ascii')))

    # Auto Scaling Group
    asg = autoscaling.Group("proxy-asg",
        vpc_zone_identifiers=[public_subnet_1_id, public_subnet_2_id],
        launch_template=autoscaling.GroupLaunchTemplateArgs(
            id=launch_template.id,
            version="$Latest"
        ),
        min_size=number_of_proxies,
        max_size=number_of_proxies,
        desired_capacity=number_of_proxies,
        health_check_type="EC2",
        health_check_grace_period=300)

    # Network Load Balancer
    load_balancer = lb.LoadBalancer("proxy-load-balancer",
        load_balancer_type="network",
        subnets=[public_subnet_1_id, public_subnet_2_id])

    target_group = lb.TargetGroup("proxy-target-group",
        port=3128,
        protocol="TCP",
        vpc_id=vpc.id,
        target_type="instance")

    listener = lb.Listener("proxy-listener",
        load_balancer_arn=load_balancer.arn,
        port=3128,
        protocol="TCP",
        default_actions=[lb.ListenerDefaultActionArgs(
            type="forward",
            target_group_arn=target_group.arn
        )])

    # Lambda function to associate Elastic IPs
    lambda_role = iam.Role("lambda-execution-role",
        assume_role_policy={
            "Version": "2012-10-17",
            "Statement": [{
                "Action": "sts:AssumeRole",
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com",
                },
            }],
        },
        managed_policy_arns=["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"])

    lambda_role_policy = iam.RolePolicy("lambda-role-policy",
        role=lambda_role.id,
        policy={
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "ec2:AssociateAddress",
                    "ec2:DescribeInstances",
                    "autoscaling:DescribeAutoScalingGroups",
                ],
                "Resource": "*",
            }],
        })

    lambda_code = """
import boto3
import cfnresponse

def handler(event, context):
    if event['RequestType'] == 'Create' or event['RequestType'] == 'Update':
        ec2 = boto3.client('ec2')
        asg = boto3.client('autoscaling')
        
        asg_name = event['ResourceProperties']['AutoScalingGroupName']
        eip_ids = event['ResourceProperties']['ElasticIPs']
        
        response = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        instance_ids = [i['InstanceId'] for i in response['AutoScalingGroups'][0]['Instances']]
        
        for i, instance_id in enumerate(instance_ids):
            if i < len(eip_ids):
                ec2.associate_address(InstanceId=instance_id, AllocationId=eip_ids[i])
    
    cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
"""

    associate_eips_function = lambda_.Function("associate-eips-function",
        code=pulumi.AssetArchive({
            "index.py": pulumi.StringAsset(lambda_code),
        }),
        handler="index.handler",
        runtime="python3.8",
        role=lambda_role.arn,
        timeout=300)

    # Custom resource to trigger the Lambda function
    custom_resource = pulumi.CustomResource("associate-eips-custom-resource",
        "Custom::AssociateElasticIPs",
        {
            "ServiceToken": associate_eips_function.arn,
            "AutoScalingGroupName": asg.name,
            "ElasticIPs": elastic_ip_allocation_ids,
        })

    # Outputs
    pulumi.export("proxy_load_balancer_dns", load_balancer.dns_name)

# This is the entry point for the Pulumi program
if __name__ == "__main__":
    create_infrastructure()