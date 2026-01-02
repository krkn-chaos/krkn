import unittest
from unittest.mock import Mock, patch
from arcaflow_plugin_sdk import plugin

from krkn.scenario_plugins.native.network import ingress_shaping


class NetworkScenariosTest(unittest.TestCase):

    def test_serialization(self):
        """Test serialization of configuration and output objects"""
        plugin.test_object_serialization(
            ingress_shaping.NetworkScenarioConfig(
                node_interface_name={"foo": ["bar"]},
                network_params={
                    "latency": "50ms",
                    "loss": "0.02",
                    "bandwidth": "100mbit",
                },
            ),
            self.fail,
        )
        plugin.test_object_serialization(
            ingress_shaping.NetworkScenarioSuccessOutput(
                filter_direction="ingress",
                test_interfaces={"foo": ["bar"]},
                network_parameters={
                    "latency": "50ms",
                    "loss": "0.02",
                    "bandwidth": "100mbit",
                },
                execution_type="parallel",
            ),
            self.fail,
        )
        plugin.test_object_serialization(
            ingress_shaping.NetworkScenarioErrorOutput(
                error="Hello World",
            ),
            self.fail,
        )

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_get_default_interface(self, mock_kube_helper):
        """Test getting default interface from a node"""
        # Setup mocks
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kube_helper.create_pod.return_value = None
        mock_kube_helper.exec_cmd_in_pod.return_value = (
            "default via 192.168.1.1 dev eth0 proto dhcp metric 100\n"
            "172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1"
        )
        mock_kube_helper.delete_pod.return_value = None

        # Test
        result = ingress_shaping.get_default_interface(
            node="test-node",
            pod_template=mock_pod_template,
            cli=mock_cli,
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        self.assertEqual(result, ["eth0"])
        mock_kube_helper.create_pod.assert_called_once()
        mock_kube_helper.exec_cmd_in_pod.assert_called_once()
        mock_kube_helper.delete_pod.assert_called_once()

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_verify_interface_with_empty_list(self, mock_kube_helper):
        """Test verifying interface when input list is empty"""
        # Setup mocks
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kube_helper.create_pod.return_value = None
        mock_kube_helper.exec_cmd_in_pod.return_value = (
            "default via 192.168.1.1 dev eth0 proto dhcp metric 100\n"
        )
        mock_kube_helper.delete_pod.return_value = None

        # Test
        result = ingress_shaping.verify_interface(
            input_interface_list=[],
            node="test-node",
            pod_template=mock_pod_template,
            cli=mock_cli,
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        self.assertEqual(result, ["eth0"])

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_verify_interface_with_valid_interfaces(self, mock_kube_helper):
        """Test verifying interface with valid interface list"""
        # Setup mocks
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kube_helper.create_pod.return_value = None
        mock_kube_helper.exec_cmd_in_pod.return_value = (
            "eth0             UP             192.168.1.10/24\n"
            "eth1             UP             10.0.0.5/24\n"
            "lo               UNKNOWN        127.0.0.1/8\n"
        )
        mock_kube_helper.delete_pod.return_value = None

        # Test
        result = ingress_shaping.verify_interface(
            input_interface_list=["eth0", "eth1"],
            node="test-node",
            pod_template=mock_pod_template,
            cli=mock_cli,
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        self.assertEqual(result, ["eth0", "eth1"])

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_verify_interface_with_invalid_interface(self, mock_kube_helper):
        """Test verifying interface with an interface that doesn't exist"""
        # Setup mocks
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kube_helper.create_pod.return_value = None
        mock_kube_helper.exec_cmd_in_pod.return_value = (
            "eth0             UP             192.168.1.10/24\n"
            "lo               UNKNOWN        127.0.0.1/8\n"
        )
        mock_kube_helper.delete_pod.return_value = None

        # Test - should raise exception
        with self.assertRaises(Exception) as context:
            ingress_shaping.verify_interface(
                input_interface_list=["eth0", "eth99"],
                node="test-node",
                pod_template=mock_pod_template,
                cli=mock_cli,
                image="quay.io/krkn-chaos/krkn:tools"
            )

        self.assertIn("Interface eth99 not found", str(context.exception))

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_default_interface')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_get_node_interfaces_with_label_selector(self, mock_kube_helper, mock_get_default_interface):
        """Test getting node interfaces using label selector"""
        # Setup mocks
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_kube_helper.get_node.return_value = ["node1", "node2"]
        mock_get_default_interface.return_value = ["eth0"]

        # Test
        result = ingress_shaping.get_node_interfaces(
            node_interface_dict=None,
            label_selector="node-role.kubernetes.io/worker",
            instance_count=2,
            pod_template=mock_pod_template,
            cli=mock_cli,
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        self.assertEqual(result, {"node1": ["eth0"], "node2": ["eth0"]})
        self.assertEqual(mock_get_default_interface.call_count, 2)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.verify_interface')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_get_node_interfaces_with_node_dict(self, mock_kube_helper, mock_verify_interface):
        """Test getting node interfaces with provided node interface dictionary"""
        # Setup mocks
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_kube_helper.get_node.return_value = ["node1"]
        mock_verify_interface.return_value = ["eth0", "eth1"]

        # Test
        result = ingress_shaping.get_node_interfaces(
            node_interface_dict={"node1": ["eth0", "eth1"]},
            label_selector=None,
            instance_count=1,
            pod_template=mock_pod_template,
            cli=mock_cli,
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        self.assertEqual(result, {"node1": ["eth0", "eth1"]})
        mock_verify_interface.assert_called_once()

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_get_node_interfaces_no_selector_no_dict(self, mock_kube_helper):
        """Test that exception is raised when both node dict and label selector are missing"""
        mock_cli = Mock()
        mock_pod_template = Mock()

        with self.assertRaises(Exception) as context:
            ingress_shaping.get_node_interfaces(
                node_interface_dict=None,
                label_selector=None,
                instance_count=1,
                pod_template=mock_pod_template,
                cli=mock_cli,
                image="quay.io/krkn-chaos/krkn:tools"
            )

        self.assertIn("label selector must be provided", str(context.exception))

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_create_ifb(self, mock_kube_helper):
        """Test creating virtual interfaces"""
        mock_cli = Mock()
        mock_kube_helper.exec_cmd_in_pod.return_value = None

        # Test
        ingress_shaping.create_ifb(cli=mock_cli, number=2, pod_name="test-pod")

        # Assertions
        # Should call modprobe once and ip link set for each interface
        self.assertEqual(mock_kube_helper.exec_cmd_in_pod.call_count, 3)

        # Verify modprobe call
        first_call = mock_kube_helper.exec_cmd_in_pod.call_args_list[0]
        self.assertIn("modprobe", first_call[0][1])
        self.assertIn("numifbs=2", first_call[0][1])

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_delete_ifb(self, mock_kube_helper):
        """Test deleting virtual interfaces"""
        mock_cli = Mock()
        mock_kube_helper.exec_cmd_in_pod.return_value = None

        # Test
        ingress_shaping.delete_ifb(cli=mock_cli, pod_name="test-pod")

        # Assertions
        mock_kube_helper.exec_cmd_in_pod.assert_called_once()
        call_args = mock_kube_helper.exec_cmd_in_pod.call_args[0][1]
        self.assertIn("modprobe", call_args)
        self.assertIn("-r", call_args)
        self.assertIn("ifb", call_args)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_get_job_pods(self, mock_kube_helper):
        """Test getting pods associated with a job"""
        mock_cli = Mock()
        mock_api_response = Mock()
        mock_api_response.metadata.labels = {"controller-uid": "test-uid-123"}

        mock_kube_helper.list_pods.return_value = ["pod1", "pod2"]

        # Test
        result = ingress_shaping.get_job_pods(cli=mock_cli, api_response=mock_api_response)

        # Assertions
        self.assertEqual(result, "pod1")
        mock_kube_helper.list_pods.assert_called_once_with(
            mock_cli,
            label_selector="controller-uid=test-uid-123",
            namespace="default"
        )

    @patch('time.sleep', return_value=None)
    @patch('time.time')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_wait_for_job_success(self, mock_kube_helper, mock_time, mock_sleep):
        """Test waiting for jobs to complete successfully"""
        mock_batch_cli = Mock()
        mock_time.side_effect = [0, 10, 20]  # Simulate time progression

        # First job succeeds
        mock_response1 = Mock()
        mock_response1.status.succeeded = 1
        mock_response1.status.failed = None

        # Second job succeeds
        mock_response2 = Mock()
        mock_response2.status.succeeded = 1
        mock_response2.status.failed = None

        mock_kube_helper.get_job_status.side_effect = [mock_response1, mock_response2]

        # Test
        ingress_shaping.wait_for_job(
            batch_cli=mock_batch_cli,
            job_list=["job1", "job2"],
            timeout=300
        )

        # Assertions
        self.assertEqual(mock_kube_helper.get_job_status.call_count, 2)

    @patch('time.sleep', return_value=None)
    @patch('time.time')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_wait_for_job_timeout(self, mock_kube_helper, mock_time, mock_sleep):
        """Test waiting for jobs times out"""
        mock_batch_cli = Mock()
        mock_time.side_effect = [0, 350]  # Simulate timeout

        mock_response = Mock()
        mock_response.status.succeeded = None
        mock_response.status.failed = None

        mock_kube_helper.get_job_status.return_value = mock_response

        # Test - should raise exception
        with self.assertRaises(Exception) as context:
            ingress_shaping.wait_for_job(
                batch_cli=mock_batch_cli,
                job_list=["job1"],
                timeout=300
            )

        self.assertIn("timeout", str(context.exception))

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_delete_jobs(self, mock_kube_helper):
        """Test deleting jobs"""
        mock_cli = Mock()
        mock_batch_cli = Mock()

        mock_response = Mock()
        mock_response.status.failed = None
        mock_kube_helper.get_job_status.return_value = mock_response
        mock_kube_helper.delete_job.return_value = None

        # Test
        ingress_shaping.delete_jobs(
            cli=mock_cli,
            batch_cli=mock_batch_cli,
            job_list=["job1", "job2"]
        )

        # Assertions
        self.assertEqual(mock_kube_helper.get_job_status.call_count, 2)
        self.assertEqual(mock_kube_helper.delete_job.call_count, 2)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_job_pods')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_delete_jobs_with_failed_job(self, mock_kube_helper, mock_get_job_pods):
        """Test deleting jobs when one has failed"""
        mock_cli = Mock()
        mock_batch_cli = Mock()

        mock_response = Mock()
        mock_response.status.failed = 1

        mock_pod_status = Mock()
        mock_pod_status.status.container_statuses = []

        mock_log_response = Mock()
        mock_log_response.data.decode.return_value = "Error log content"

        mock_kube_helper.get_job_status.return_value = mock_response
        mock_get_job_pods.return_value = "failed-pod"
        mock_kube_helper.read_pod.return_value = mock_pod_status
        mock_kube_helper.get_pod_log.return_value = mock_log_response
        mock_kube_helper.delete_job.return_value = None

        # Test
        ingress_shaping.delete_jobs(
            cli=mock_cli,
            batch_cli=mock_batch_cli,
            job_list=["failed-job"]
        )

        # Assertions
        mock_kube_helper.read_pod.assert_called_once()
        mock_kube_helper.get_pod_log.assert_called_once()

    def test_get_ingress_cmd_basic(self):
        """Test generating ingress traffic shaping commands"""
        result = ingress_shaping.get_ingress_cmd(
            interface_list=["eth0"],
            network_parameters={"latency": "50ms"},
            duration=120
        )

        # Assertions
        self.assertIn("tc qdisc add dev eth0 handle ffff: ingress", result)
        self.assertIn("tc filter add dev eth0", result)
        self.assertIn("ifb0", result)
        self.assertIn("delay 50ms", result)
        self.assertIn("sleep 120", result)
        self.assertIn("tc qdisc del", result)

    def test_get_ingress_cmd_multiple_interfaces(self):
        """Test generating commands for multiple interfaces"""
        result = ingress_shaping.get_ingress_cmd(
            interface_list=["eth0", "eth1"],
            network_parameters={"latency": "50ms", "bandwidth": "100mbit"},
            duration=120
        )

        # Assertions
        self.assertIn("eth0", result)
        self.assertIn("eth1", result)
        self.assertIn("ifb0", result)
        self.assertIn("ifb1", result)
        self.assertIn("delay 50ms", result)
        self.assertIn("rate 100mbit", result)

    def test_get_ingress_cmd_all_parameters(self):
        """Test generating commands with all network parameters"""
        result = ingress_shaping.get_ingress_cmd(
            interface_list=["eth0"],
            network_parameters={
                "latency": "50ms",
                "loss": "0.02",
                "bandwidth": "100mbit"
            },
            duration=120
        )

        # Assertions
        self.assertIn("delay 50ms", result)
        self.assertIn("loss 0.02", result)
        self.assertIn("rate 100mbit", result)

    def test_get_ingress_cmd_invalid_interface(self):
        """Test that invalid interface names raise an exception"""
        with self.assertRaises(Exception) as context:
            ingress_shaping.get_ingress_cmd(
                interface_list=["eth0; rm -rf /"],
                network_parameters={"latency": "50ms"},
                duration=120
            )

        self.assertIn("does not match the required regex pattern", str(context.exception))

    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.create_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_ingress_cmd')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_apply_ingress_filter(self, mock_kube_helper, mock_get_cmd, mock_create_virtual, mock_yaml):
        """Test applying ingress filters to a node"""
        # Setup mocks
        mock_cli = Mock()
        mock_batch_cli = Mock()
        mock_pod_template = Mock()
        mock_job_template = Mock()
        mock_job_template.render.return_value = "job_yaml"

        mock_cfg = ingress_shaping.NetworkScenarioConfig(
            node_interface_name={"node1": ["eth0"]},
            network_params={"latency": "50ms"},
            test_duration=120
        )

        mock_yaml.return_value = {"metadata": {"name": "test-job"}}
        mock_get_cmd.return_value = "tc commands"
        mock_kube_helper.create_job.return_value = Mock()

        # Test
        result = ingress_shaping.apply_ingress_filter(
            cfg=mock_cfg,
            interface_list=["eth0"],
            node="node1",
            pod_template=mock_pod_template,
            job_template=mock_job_template,
            batch_cli=mock_batch_cli,
            cli=mock_cli,
            create_interfaces=True,
            param_selector="all",
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        mock_create_virtual.assert_called_once()
        mock_get_cmd.assert_called_once()
        mock_kube_helper.create_job.assert_called_once()
        self.assertEqual(result, "test-job")

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_create_virtual_interfaces(self, mock_kube_helper):
        """Test creating virtual interfaces on a node"""
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"

        mock_kube_helper.create_pod.return_value = None
        mock_kube_helper.exec_cmd_in_pod.return_value = None
        mock_kube_helper.delete_pod.return_value = None

        # Test
        ingress_shaping.create_virtual_interfaces(
            cli=mock_cli,
            interface_list=["eth0", "eth1"],
            node="test-node",
            pod_template=mock_pod_template,
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        mock_kube_helper.create_pod.assert_called_once()
        mock_kube_helper.delete_pod.assert_called_once()

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_ifb')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_delete_virtual_interfaces(self, mock_kube_helper, mock_delete_ifb):
        """Test deleting virtual interfaces from nodes"""
        mock_cli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"

        mock_kube_helper.create_pod.return_value = None
        mock_kube_helper.delete_pod.return_value = None

        # Test
        ingress_shaping.delete_virtual_interfaces(
            cli=mock_cli,
            node_list=["node1", "node2"],
            pod_template=mock_pod_template,
            image="quay.io/krkn-chaos/krkn:tools"
        )

        # Assertions
        self.assertEqual(mock_kube_helper.create_pod.call_count, 2)
        self.assertEqual(mock_delete_ifb.call_count, 2)
        self.assertEqual(mock_kube_helper.delete_pod.call_count, 2)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.wait_for_job')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.apply_ingress_filter')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_network_chaos_parallel_execution(
        self, mock_kube_helper, mock_get_nodes, mock_apply_filter,
        mock_wait_job, mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos with parallel execution"""
        # Setup mocks
        mock_cli = Mock()
        mock_batch_cli = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_kube_helper.setup_kubernetes.return_value = (mock_cli, mock_batch_cli)
        mock_get_nodes.return_value = {"node1": ["eth0"], "node2": ["eth1"]}
        mock_apply_filter.side_effect = ["job1", "job2"]

        # Test
        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=2,
            network_params={"latency": "50ms"},
            execution_type="parallel",
            test_duration=120,
            wait_duration=30
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        # Assertions
        self.assertEqual(output_id, "success")
        self.assertEqual(output_data.filter_direction, "ingress")
        self.assertEqual(output_data.execution_type, "parallel")
        self.assertEqual(mock_apply_filter.call_count, 2)
        mock_wait_job.assert_called_once()
        mock_delete_virtual.assert_called_once()

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('time.sleep', return_value=None)
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.wait_for_job')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.apply_ingress_filter')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_network_chaos_serial_execution(
        self, mock_kube_helper, mock_get_nodes, mock_apply_filter,
        mock_wait_job, mock_delete_virtual, mock_delete_jobs, mock_sleep, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos with serial execution"""
        # Setup mocks
        mock_cli = Mock()
        mock_batch_cli = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_kube_helper.setup_kubernetes.return_value = (mock_cli, mock_batch_cli)
        mock_get_nodes.return_value = {"node1": ["eth0"]}
        mock_apply_filter.return_value = "job1"

        # Test
        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms", "bandwidth": "100mbit"},
            execution_type="serial",
            test_duration=120,
            wait_duration=30
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        # Assertions
        self.assertEqual(output_id, "success")
        self.assertEqual(output_data.execution_type, "serial")
        # Should be called once per parameter per node
        self.assertEqual(mock_apply_filter.call_count, 2)
        # Should wait for jobs twice (once per parameter)
        self.assertEqual(mock_wait_job.call_count, 2)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_network_chaos_invalid_execution_type(
        self, mock_kube_helper, mock_get_nodes, mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos with invalid execution type"""
        # Setup mocks
        mock_cli = Mock()
        mock_batch_cli = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_kube_helper.setup_kubernetes.return_value = (mock_cli, mock_batch_cli)
        mock_get_nodes.return_value = {"node1": ["eth0"]}

        # Test
        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms"},
            execution_type="invalid_type",
            test_duration=120
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        # Assertions
        self.assertEqual(output_id, "error")
        self.assertIn("Invalid execution type", output_data.error)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_network_chaos_get_nodes_error(
        self, mock_kube_helper, mock_get_nodes, mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos when getting nodes fails"""
        # Setup mocks
        mock_cli = Mock()
        mock_batch_cli = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_kube_helper.setup_kubernetes.return_value = (mock_cli, mock_batch_cli)
        mock_get_nodes.side_effect = Exception("Failed to get nodes")

        # Test
        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms"}
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        # Assertions
        self.assertEqual(output_id, "error")
        self.assertIn("Failed to get nodes", output_data.error)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.apply_ingress_filter')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.kube_helper')
    def test_network_chaos_apply_filter_error(
        self, mock_kube_helper, mock_get_nodes, mock_apply_filter,
        mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos when applying filter fails"""
        # Setup mocks
        mock_cli = Mock()
        mock_batch_cli = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_kube_helper.setup_kubernetes.return_value = (mock_cli, mock_batch_cli)
        mock_get_nodes.return_value = {"node1": ["eth0"]}
        mock_apply_filter.side_effect = Exception("Failed to apply filter")

        # Test
        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms"},
            execution_type="parallel"
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        # Assertions
        self.assertEqual(output_id, "error")
        self.assertIn("Failed to apply filter", output_data.error)
        # Cleanup should still be called
        mock_delete_virtual.assert_called_once()


if __name__ == "__main__":
    unittest.main()
