import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from unittest.mock import Mock, patch, call
import pulumi
import src.static_infrastructure as static_infrastructure

class TestBuildInfrastructure(unittest.TestCase):

    @patch('pulumi.Config')
    @patch('pulumi_aws.cloudformation.get_stack')
    @patch('pulumi_aws.ec2.get_vpc')
    @patch('pulumi_aws.ec2.SecurityGroup')
    @patch('pulumi_aws.ec2.LaunchTemplate')
    @patch('pulumi_aws.autoscaling.Group')
    @patch('pulumi_aws.lb.LoadBalancer')
    @patch('pulumi_aws.lb.TargetGroup')
    @patch('pulumi_aws.lb.Listener')
    @patch('pulumi_aws.iam.Role')
    @patch('pulumi_aws.iam.RolePolicy')
    @patch('pulumi_aws.lambda_.Function')
    @patch('pulumi.CustomResource')
    @patch('pulumi.export')
    def test_infrastructure_creation(self, mock_export, mock_custom_resource, mock_lambda_function,
                                     mock_role_policy, mock_role, mock_listener, mock_target_group,
                                     mock_load_balancer, mock_asg, mock_launch_template,
                                     mock_security_group, mock_get_vpc, mock_get_stack, mock_config):
        # Setup mock config
        mock_config.return_value.get.side_effect = lambda key, default=None: "t3.micro" if key == "instanceType" else default
        mock_config.return_value.get_int.return_value = 500
        mock_config.return_value.require.side_effect = lambda key: f"mock-{key}"

        # Setup mock CloudFormation stack
        mock_stack = Mock()
        mock_stack.outputs = {
            "VpcId": "mock-vpc-id",
            "PublicSubnet1": "mock-subnet-1",
            "PublicSubnet2": "mock-subnet-2",
            "ElasticIPs": "eip-1,eip-2"
        }
        mock_get_stack.return_value = mock_stack

        # Setup mock VPC
        mock_vpc = Mock()
        mock_vpc.id = "mock-vpc-id"
        mock_get_vpc.return_value = mock_vpc

        # Call the function to create infrastructure
        static_infrastructure.create_infrastructure()

        # Assert CloudFormation stack retrieval
        mock_get_stack.assert_called_once_with(name="ProxyVPCStack")

        # Assert VPC retrieval
        mock_get_vpc.assert_called_once_with(id="mock-vpc-id")

        # Assert Security Group creation
        mock_security_group.assert_called_once()
        security_group_args = mock_security_group.call_args[1]
        self.assertEqual(security_group_args['vpc_id'], mock_vpc.id)

        # Assert Launch Template creation
        mock_launch_template.assert_called_once()

        # Assert Auto Scaling Group creation
        mock_asg.assert_called_once()

        # Assert Load Balancer creation
        mock_load_balancer.assert_called_once()

        # Assert Target Group creation
        mock_target_group.assert_called_once()

        # Assert Listener creation
        mock_listener.assert_called_once()

        # Assert IAM Role and Policy creation
        mock_role.assert_called_once()
        mock_role_policy.assert_called_once()

        # Assert Lambda Function creation
        mock_lambda_function.assert_called_once()

        # Assert Custom Resource creation
        mock_custom_resource.assert_called_once()

        # Assert exports
        mock_export.assert_called()

if __name__ == '__main__':
    unittest.main()