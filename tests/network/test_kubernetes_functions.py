#!/usr/bin/env python3

"""
Test suite for krkn.scenario_plugins.native.network.kubernetes_functions module

Usage:
    python3 -m coverage run --source=krkn -m pytest tests/network/test_kubernetes_functions.py -v
    python3 -m coverage report -m --include=krkn/scenario_plugins/native/network/kubernetes_functions.py
"""

import unittest
from unittest.mock import MagicMock, patch, call
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from kubernetes.client.rest import ApiException

from krkn.scenario_plugins.native.network import kubernetes_functions as kube_funcs


class TestSetupKubernetes(unittest.TestCase):
    """Test suite for setup_kubernetes function"""

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.client')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.config')
    def test_setup_kubernetes_with_path(self, mock_config, mock_client):
        """Test setup_kubernetes with custom kubeconfig path"""
        mock_cli = MagicMock()
        mock_batch_cli = MagicMock()
        mock_client.CoreV1Api.return_value = mock_cli
        mock_client.BatchV1Api.return_value = mock_batch_cli

        cli, batch_cli = kube_funcs.setup_kubernetes("/path/to/kubeconfig")

        mock_config.load_kube_config.assert_called_once_with("/path/to/kubeconfig")
        self.assertEqual(cli, mock_cli)
        self.assertEqual(batch_cli, mock_batch_cli)

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.client')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.config')
    def test_setup_kubernetes_default_path(self, mock_config, mock_client):
        """Test setup_kubernetes with default kubeconfig path"""
        mock_config.KUBE_CONFIG_DEFAULT_LOCATION = "~/.kube/config"
        mock_cli = MagicMock()
        mock_batch_cli = MagicMock()
        mock_client.CoreV1Api.return_value = mock_cli
        mock_client.BatchV1Api.return_value = mock_batch_cli

        cli, batch_cli = kube_funcs.setup_kubernetes(None)

        mock_config.load_kube_config.assert_called_once_with("~/.kube/config")


class TestCreateJob(unittest.TestCase):
    """Test suite for create_job function"""

    def test_create_job_success(self):
        """Test create_job with successful creation"""
        mock_batch_cli = MagicMock()
        mock_response = MagicMock()
        mock_batch_cli.create_namespaced_job.return_value = mock_response
        body = {"metadata": {"name": "test-job"}}

        result = kube_funcs.create_job(mock_batch_cli, body, "default")

        self.assertEqual(result, mock_response)
        mock_batch_cli.create_namespaced_job.assert_called_once_with(body=body, namespace="default")

    def test_create_job_already_exists(self):
        """Test create_job when job already exists (409 conflict)"""
        mock_batch_cli = MagicMock()
        api_exception = ApiException(status=409)
        mock_batch_cli.create_namespaced_job.side_effect = api_exception
        body = {"metadata": {"name": "test-job"}}

        result = kube_funcs.create_job(mock_batch_cli, body)

        self.assertIsNone(result)

    def test_create_job_api_exception_other(self):
        """Test create_job with non-409 ApiException"""
        mock_batch_cli = MagicMock()
        api_exception = ApiException(status=500)
        mock_batch_cli.create_namespaced_job.side_effect = api_exception
        body = {"metadata": {"name": "test-job"}}

        result = kube_funcs.create_job(mock_batch_cli, body)

        self.assertIsNone(result)

    def test_create_job_generic_exception(self):
        """Test create_job with generic exception"""
        mock_batch_cli = MagicMock()
        mock_batch_cli.create_namespaced_job.side_effect = Exception("Connection error")
        body = {"metadata": {"name": "test-job"}}

        with self.assertRaises(Exception):
            kube_funcs.create_job(mock_batch_cli, body)


class TestDeletePod(unittest.TestCase):
    """Test suite for delete_pod function"""

    def test_delete_pod_success(self):
        """Test delete_pod with successful deletion"""
        mock_cli = MagicMock()
        # First read returns pod, second raises 404
        mock_cli.read_namespaced_pod.side_effect = [
            MagicMock(),
            ApiException(status=404)
        ]

        kube_funcs.delete_pod(mock_cli, "test-pod", "default")

        mock_cli.delete_namespaced_pod.assert_called_once_with(name="test-pod", namespace="default")

    def test_delete_pod_already_deleted(self):
        """Test delete_pod when pod is already deleted (404)"""
        mock_cli = MagicMock()
        mock_cli.delete_namespaced_pod.side_effect = ApiException(status=404)

        kube_funcs.delete_pod(mock_cli, "test-pod", "default")

    def test_delete_pod_api_exception(self):
        """Test delete_pod with non-404 ApiException"""
        mock_cli = MagicMock()
        api_exception = ApiException(status=500)
        mock_cli.delete_namespaced_pod.side_effect = api_exception

        with self.assertRaises(ApiException):
            kube_funcs.delete_pod(mock_cli, "test-pod", "default")


class TestCreatePod(unittest.TestCase):
    """Test suite for create_pod function"""

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.time.sleep')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.time.time')
    def test_create_pod_success(self, mock_time, mock_sleep):
        """Test create_pod with successful creation"""
        mock_cli = MagicMock()
        mock_pod_stat = MagicMock()
        mock_pod_stat.status.phase = "Running"
        mock_cli.create_namespaced_pod.return_value = mock_pod_stat
        mock_cli.read_namespaced_pod.return_value = mock_pod_stat
        mock_time.return_value = 0
        body = {"metadata": {"name": "test-pod"}}

        kube_funcs.create_pod(mock_cli, body, "default")

        mock_cli.create_namespaced_pod.assert_called_once()

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.delete_pod')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.sys.exit')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.time.sleep')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.time.time')
    def test_create_pod_timeout(self, mock_time, mock_sleep, mock_exit, mock_delete_pod):
        """Test create_pod with timeout"""
        mock_cli = MagicMock()
        mock_pod_stat = MagicMock()
        mock_pod_stat.status.phase = "Pending"
        mock_pod_stat.status.container_statuses = []
        mock_cli.create_namespaced_pod.return_value = mock_pod_stat
        mock_cli.read_namespaced_pod.return_value = mock_pod_stat
        # Use callable to handle multiple time.time() calls (including from logging)
        time_counter = [0]
        def mock_time_func():
            time_counter[0] += 200  # Each call increments by 200 to exceed timeout
            return time_counter[0]
        mock_time.side_effect = mock_time_func
        body = {"metadata": {"name": "test-pod"}}

        mock_exit.side_effect = SystemExit(1)
        
        with self.assertRaises(SystemExit):
            kube_funcs.create_pod(mock_cli, body, "default", timeout=120)

        mock_delete_pod.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.delete_pod')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.sys.exit')
    def test_create_pod_exception(self, mock_exit, mock_delete_pod):
        """Test create_pod with exception during creation"""
        mock_cli = MagicMock()
        mock_cli.create_namespaced_pod.side_effect = Exception("Creation failed")
        body = {"metadata": {"name": "test-pod"}}

        mock_exit.side_effect = SystemExit(1)
        
        with self.assertRaises(SystemExit):
            kube_funcs.create_pod(mock_cli, body, "default")

        mock_delete_pod.assert_called_once()


class TestExecCmdInPod(unittest.TestCase):
    """Test suite for exec_cmd_in_pod function"""

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.stream')
    def test_exec_cmd_in_pod_success(self, mock_stream):
        """Test exec_cmd_in_pod with successful execution"""
        mock_cli = MagicMock()
        mock_stream.return_value = "command output"

        result = kube_funcs.exec_cmd_in_pod(mock_cli, ["ls", "-la"], "test-pod", "default")

        self.assertEqual(result, "command output")
        mock_stream.assert_called_once()

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.stream')
    def test_exec_cmd_in_pod_with_container(self, mock_stream):
        """Test exec_cmd_in_pod with specific container"""
        mock_cli = MagicMock()
        mock_stream.return_value = "output"

        result = kube_funcs.exec_cmd_in_pod(
            mock_cli, ["echo", "test"], "test-pod", "default", container="my-container"
        )

        self.assertEqual(result, "output")
        # Verify container parameter was passed
        call_kwargs = mock_stream.call_args[1]
        self.assertEqual(call_kwargs['container'], 'my-container')

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.stream')
    def test_exec_cmd_in_pod_exception(self, mock_stream):
        """Test exec_cmd_in_pod with exception"""
        mock_cli = MagicMock()
        mock_stream.side_effect = Exception("Exec failed")

        result = kube_funcs.exec_cmd_in_pod(mock_cli, ["ls"], "test-pod", "default")

        self.assertFalse(result)


class TestCreateIfb(unittest.TestCase):
    """Test suite for create_ifb function"""

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.exec_cmd_in_pod')
    def test_create_ifb(self, mock_exec):
        """Test create_ifb creates virtual interfaces"""
        mock_cli = MagicMock()
        mock_exec.return_value = ""

        kube_funcs.create_ifb(mock_cli, 3, "test-pod")

        # Should be called 4 times: 1 for modprobe + 3 for each interface
        self.assertEqual(mock_exec.call_count, 4)


class TestDeleteIfb(unittest.TestCase):
    """Test suite for delete_ifb function"""

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.exec_cmd_in_pod')
    def test_delete_ifb(self, mock_exec):
        """Test delete_ifb removes virtual interfaces"""
        mock_cli = MagicMock()
        mock_exec.return_value = ""

        kube_funcs.delete_ifb(mock_cli, "test-pod")

        mock_exec.assert_called_once_with(
            mock_cli,
            ['chroot', '/host', 'modprobe', '-r', 'ifb'],
            "test-pod",
            'default'
        )


class TestListPods(unittest.TestCase):
    """Test suite for list_pods function"""

    def test_list_pods_success(self):
        """Test list_pods with successful listing"""
        mock_cli = MagicMock()
        mock_pod1 = MagicMock()
        mock_pod1.metadata.name = "pod-1"
        mock_pod2 = MagicMock()
        mock_pod2.metadata.name = "pod-2"
        mock_ret = MagicMock()
        mock_ret.items = [mock_pod1, mock_pod2]
        mock_cli.list_namespaced_pod.return_value = mock_ret

        result = kube_funcs.list_pods(mock_cli, "default")

        self.assertEqual(result, ["pod-1", "pod-2"])

    def test_list_pods_with_label_selector(self):
        """Test list_pods with label selector"""
        mock_cli = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.name = "labeled-pod"
        mock_ret = MagicMock()
        mock_ret.items = [mock_pod]
        mock_cli.list_namespaced_pod.return_value = mock_ret

        result = kube_funcs.list_pods(mock_cli, "default", label_selector="app=test")

        mock_cli.list_namespaced_pod.assert_called_once_with(
            "default", pretty=True, label_selector="app=test"
        )
        self.assertEqual(result, ["labeled-pod"])

    def test_list_pods_api_exception(self):
        """Test list_pods with ApiException"""
        mock_cli = MagicMock()
        mock_cli.list_namespaced_pod.side_effect = ApiException(status=500)

        with self.assertRaises(ApiException):
            kube_funcs.list_pods(mock_cli, "default")


class TestGetJobStatus(unittest.TestCase):
    """Test suite for get_job_status function"""

    def test_get_job_status_success(self):
        """Test get_job_status with successful retrieval"""
        mock_batch_cli = MagicMock()
        mock_status = MagicMock()
        mock_batch_cli.read_namespaced_job_status.return_value = mock_status

        result = kube_funcs.get_job_status(mock_batch_cli, "test-job", "default")

        self.assertEqual(result, mock_status)
        mock_batch_cli.read_namespaced_job_status.assert_called_once_with(
            name="test-job", namespace="default"
        )

    def test_get_job_status_exception(self):
        """Test get_job_status with exception"""
        mock_batch_cli = MagicMock()
        mock_batch_cli.read_namespaced_job_status.side_effect = Exception("Not found")

        with self.assertRaises(Exception):
            kube_funcs.get_job_status(mock_batch_cli, "test-job")


class TestGetPodLog(unittest.TestCase):
    """Test suite for get_pod_log function"""

    def test_get_pod_log_success(self):
        """Test get_pod_log with successful retrieval"""
        mock_cli = MagicMock()
        mock_log = MagicMock()
        mock_cli.read_namespaced_pod_log.return_value = mock_log

        result = kube_funcs.get_pod_log(mock_cli, "test-pod", "default")

        self.assertEqual(result, mock_log)
        mock_cli.read_namespaced_pod_log.assert_called_once_with(
            name="test-pod",
            namespace="default",
            _return_http_data_only=True,
            _preload_content=False
        )


class TestReadPod(unittest.TestCase):
    """Test suite for read_pod function"""

    def test_read_pod_success(self):
        """Test read_pod with successful retrieval"""
        mock_cli = MagicMock()
        mock_pod = MagicMock()
        mock_cli.read_namespaced_pod.return_value = mock_pod

        result = kube_funcs.read_pod(mock_cli, "test-pod", "default")

        self.assertEqual(result, mock_pod)
        mock_cli.read_namespaced_pod.assert_called_once_with(
            name="test-pod", namespace="default"
        )


class TestDeleteJob(unittest.TestCase):
    """Test suite for delete_job function"""

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.client')
    def test_delete_job_success(self, mock_client):
        """Test delete_job with successful deletion"""
        mock_batch_cli = MagicMock()
        mock_response = MagicMock()
        mock_response.status = "deleted"
        mock_batch_cli.delete_namespaced_job.return_value = mock_response
        mock_client.V1DeleteOptions.return_value = MagicMock()

        result = kube_funcs.delete_job(mock_batch_cli, "test-job", "default")

        self.assertEqual(result, mock_response)

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.client')
    def test_delete_job_already_deleted(self, mock_client):
        """Test delete_job when job already deleted (ApiException)"""
        mock_batch_cli = MagicMock()
        mock_batch_cli.delete_namespaced_job.side_effect = ApiException(status=404)
        mock_client.V1DeleteOptions.return_value = MagicMock()

        result = kube_funcs.delete_job(mock_batch_cli, "test-job")

        self.assertIsNone(result)

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.sys.exit')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.client')
    def test_delete_job_generic_exception(self, mock_client, mock_exit):
        """Test delete_job with generic exception"""
        mock_batch_cli = MagicMock()
        mock_batch_cli.delete_namespaced_job.side_effect = Exception("Delete failed")
        mock_client.V1DeleteOptions.return_value = MagicMock()
        mock_exit.side_effect = SystemExit(1)

        with self.assertRaises(SystemExit):
            kube_funcs.delete_job(mock_batch_cli, "test-job")

        mock_exit.assert_called_once_with(1)


class TestListReadyNodes(unittest.TestCase):
    """Test suite for list_ready_nodes function"""

    def test_list_ready_nodes_success(self):
        """Test list_ready_nodes with ready nodes"""
        mock_cli = MagicMock()
        
        # Create mock nodes with Ready condition
        mock_node1 = MagicMock()
        mock_node1.metadata.name = "node-1"
        mock_cond1 = MagicMock()
        mock_cond1.type = "Ready"
        mock_cond1.status = "True"
        mock_node1.status.conditions = [mock_cond1]
        
        mock_node2 = MagicMock()
        mock_node2.metadata.name = "node-2"
        mock_cond2 = MagicMock()
        mock_cond2.type = "Ready"
        mock_cond2.status = "False"
        mock_node2.status.conditions = [mock_cond2]
        
        mock_ret = MagicMock()
        mock_ret.items = [mock_node1, mock_node2]
        mock_cli.list_node.return_value = mock_ret

        result = kube_funcs.list_ready_nodes(mock_cli)

        self.assertEqual(result, ["node-1"])

    def test_list_ready_nodes_with_label_selector(self):
        """Test list_ready_nodes with label selector"""
        mock_cli = MagicMock()
        mock_node = MagicMock()
        mock_node.metadata.name = "labeled-node"
        mock_cond = MagicMock()
        mock_cond.type = "Ready"
        mock_cond.status = "True"
        mock_node.status.conditions = [mock_cond]
        mock_ret = MagicMock()
        mock_ret.items = [mock_node]
        mock_cli.list_node.return_value = mock_ret

        result = kube_funcs.list_ready_nodes(mock_cli, label_selector="role=worker")

        mock_cli.list_node.assert_called_once_with(pretty=True, label_selector="role=worker")
        self.assertEqual(result, ["labeled-node"])

    def test_list_ready_nodes_api_exception(self):
        """Test list_ready_nodes with ApiException"""
        mock_cli = MagicMock()
        mock_cli.list_node.side_effect = ApiException(status=500)

        with self.assertRaises(ApiException):
            kube_funcs.list_ready_nodes(mock_cli)


class TestGetNode(unittest.TestCase):
    """Test suite for get_node function"""

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.list_ready_nodes')
    def test_get_node_by_name(self, mock_list_ready):
        """Test get_node when node_name is in ready nodes"""
        mock_cli = MagicMock()
        mock_list_ready.return_value = ["node-1", "node-2", "node-3"]

        result = kube_funcs.get_node("node-1", "app=test", 1, mock_cli)

        self.assertEqual(result, ["node-1"])

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.list_ready_nodes')
    def test_get_node_not_in_ready_nodes(self, mock_list_ready):
        """Test get_node when node_name is not in ready nodes"""
        mock_cli = MagicMock()
        # First call for node_name check returns list without the node
        # Second call with label_selector returns available nodes
        mock_list_ready.side_effect = [
            ["node-2", "node-3"],  # node-1 not in list
            ["node-2", "node-3"]   # available nodes with label selector
        ]

        result = kube_funcs.get_node("node-1", "app=test", 1, mock_cli)

        self.assertEqual(len(result), 1)
        self.assertIn(result[0], ["node-2", "node-3"])

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.list_ready_nodes')
    def test_get_node_no_ready_nodes(self, mock_list_ready):
        """Test get_node raises exception when no ready nodes"""
        mock_cli = MagicMock()
        mock_list_ready.side_effect = [[], []]

        with self.assertRaises(Exception) as ctx:
            kube_funcs.get_node(None, "app=test", 1, mock_cli)

        self.assertIn("Ready nodes with the provided label selector do not exist", str(ctx.exception))

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.random.randint')
    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.list_ready_nodes')
    def test_get_node_multiple_nodes(self, mock_list_ready, mock_randint):
        """Test get_node selecting multiple nodes"""
        mock_cli = MagicMock()
        mock_list_ready.side_effect = [
            [],  # node_name check
            ["node-1", "node-2", "node-3", "node-4"]  # available nodes
        ]
        mock_randint.side_effect = [0, 1]  # Select first and second node

        result = kube_funcs.get_node(None, "app=test", 2, mock_cli)

        self.assertEqual(len(result), 2)

    @patch('krkn.scenario_plugins.native.network.kubernetes_functions.list_ready_nodes')
    def test_get_node_all_nodes(self, mock_list_ready):
        """Test get_node when instance_kill_count equals number of nodes"""
        mock_cli = MagicMock()
        mock_list_ready.side_effect = [
            [],  # node_name check
            ["node-1", "node-2"]  # available nodes
        ]

        result = kube_funcs.get_node(None, "app=test", 2, mock_cli)

        self.assertEqual(result, ["node-1", "node-2"])


if __name__ == "__main__":
    unittest.main()
