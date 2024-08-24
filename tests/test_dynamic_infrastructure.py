import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest
from unittest.mock import Mock, patch, call
import pulumi
import src.dynamic_infrastructure as dynamic_infrastructure
import pulumi_aws.cloudformation

class TestBuildInfrastructure(unittest.TestCase):

    @patch('pulumi.Config')
    @patch('pulumi_aws.cloudformation.get_stack')
    @patch('pulumi_aws.ec2.SecurityGroup')
    @patch('pulumi_aws.ec2.LaunchTemplate')
    @patch('pulumi_aws.autoscaling.Group')
    @patch('pulumi_aws.lb.LoadBalancer')
    @patch('pulumi_aws.lb.TargetGroup')
    @patch('pulumi_aws.lb.Listener')
    @patch('pulumi.export')
    def test_infrastructure_creation(self, mock_export, mock_listener, mock_target_group, 
                                     mock_load_balancer, mock_asg, mock_launch_template, 
                                     mock_security_group, mock_get_stack, mock_config):
        # Setup mock config
        mock_config.return_value.get.side_effect = lambda key, default=None: "t3.micro" if key == "instanceType" else default
        mock_config.return_value.require.side_effect = lambda key: f"mock-{key}"

        # Setup mock CloudFormation stack
        mock_stack = Mock()
        mock_stack.outputs = {
            "VpcId": "mock-vpc-id",
            "PublicSubnet1": "mock-subnet-1",
            "PublicSubnet2": "mock-subnet-2"
        }
        mock_get_stack.return_value = mock_stack

        # Call the function to create infrastructure
        dynamic_infrastructure.create_infrastructure()

        # Assert Security Group creation
        mock_security_group.assert_called_once()
        sg_args = mock_security_group.call_args[1]
        self.assertEqual(sg_args['vpc_id'], "mock-vpc-id")
        self.assertEqual(len(sg_args['ingress']), 2)
        self.assertEqual(sg_args['ingress'][0].from_port, 22)
        self.assertEqual(sg_args['ingress'][1].from_port, 3128)

        # Assert Launch Template creation
        mock_launch_template.assert_called_once()
        lt_args = mock_launch_template.call_args[1]
        self.assertEqual(lt_args['image_id'], "mock-amiId")
        self.assertEqual(lt_args['instance_type'], "t3.micro")
        self.assertEqual(lt_args['key_name'], "mock-keyName")
        self.assertIsInstance(lt_args['user_data'], pulumi.Output)

        # Assert Auto Scaling Group creation
        mock_asg.assert_called_once()
        asg_args = mock_asg.call_args[1]
        self.assertEqual(asg_args['min_size'], 500)
        self.assertEqual(asg_args['max_size'], 1000)
        self.assertEqual(asg_args['desired_capacity'], 500)
        self.assertEqual(asg_args['health_check_type'], "EC2")
        self.assertEqual(asg_args['health_check_grace_period'], 300)

        # Assert Load Balancer creation
        mock_load_balancer.assert_called_once()
        lb_args = mock_load_balancer.call_args[1]
        self.assertEqual(lb_args['load_balancer_type'], "network")
        self.assertEqual(lb_args['subnets'], ["mock-subnet-1", "mock-subnet-2"])

        # Assert Target Group creation
        mock_target_group.assert_called_once()
        tg_args = mock_target_group.call_args[1]
        self.assertEqual(tg_args['port'], 3128)
        self.assertEqual(tg_args['protocol'], "TCP")
        self.assertEqual(tg_args['vpc_id'], "mock-vpc-id")
        self.assertEqual(tg_args['target_type'], "instance")

        # Assert Listener creation
        mock_listener.assert_called_once()
        listener_args = mock_listener.call_args[1]
        self.assertEqual(listener_args['port'], 3128)
        self.assertEqual(listener_args['protocol'], "TCP")

        # Assert exports
        mock_export.assert_called_once_with("proxy_load_balancer_dns", mock_load_balancer.return_value.dns_name)

if __name__ == '__main__':
    unittest.main()