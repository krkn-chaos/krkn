#!/usr/bin/env python3

"""
Test suite for ingress network shaping plugin

This test suite covers the ingress_shaping module functions using mocks
to avoid needing actual Kubernetes infrastructure.

Test Coverage:
- Serialization of config and output objects
- Interface discovery: get_default_interface, verify_interface, get_node_interfaces
- Virtual interface management: create_ifb, delete_ifb, create_virtual_interfaces, delete_virtual_interfaces
- Job management: get_job_pods, wait_for_job, delete_jobs
- Traffic shaping command generation: get_ingress_cmd
- Filter application: apply_ingress_filter
- End-to-end network_chaos flows: parallel, serial, error cases

IMPORTANT: These tests use mocking and do NOT require any Kubernetes cluster.
All API calls are mocked via unittest.mock.

Usage:
    python -m unittest tests/test_ingress_network_plugin.py -v

    # Run with coverage
    python -m coverage run -a -m unittest tests/test_ingress_network_plugin.py -v

Assisted By: Claude Code
"""
import os
from pathlib import Path
import subprocess
import tempfile
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

    def test_get_default_interface(self):
        """Test getting default interface from a node"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kubecli.create_pod.return_value = None
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "default via 192.168.1.1 dev eth0 proto dhcp metric 100\n"
            "172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1"
        )
        mock_kubecli.delete_pod.return_value = None

        result = ingress_shaping.get_default_interface(
            node="test-node",
            pod_template=mock_pod_template,
            kubecli=mock_kubecli,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

        self.assertEqual(result, ["eth0"])
        mock_kubecli.create_pod.assert_called_once()
        mock_kubecli.exec_cmd_in_pod.assert_called_once()
        mock_kubecli.delete_pod.assert_called_once()

    def test_verify_interface_with_empty_list(self):
        """Test verifying interface when input list is empty"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kubecli.create_pod.return_value = None
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "default via 192.168.1.1 dev eth0 proto dhcp metric 100\n"
        )
        mock_kubecli.delete_pod.return_value = None

        result = ingress_shaping.verify_interface(
            input_interface_list=[],
            node="test-node",
            pod_template=mock_pod_template,
            kubecli=mock_kubecli,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

        self.assertEqual(result, ["eth0"])

    def test_verify_interface_with_valid_interfaces(self):
        """Test verifying interface with valid interface list"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kubecli.create_pod.return_value = None
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "eth0             UP             192.168.1.10/24\n"
            "eth1             UP             10.0.0.5/24\n"
            "lo               UNKNOWN        127.0.0.1/8\n"
        )
        mock_kubecli.delete_pod.return_value = None

        result = ingress_shaping.verify_interface(
            input_interface_list=["eth0", "eth1"],
            node="test-node",
            pod_template=mock_pod_template,
            kubecli=mock_kubecli,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

        self.assertEqual(result, ["eth0", "eth1"])

    def test_verify_interface_accepts_actual_name_with_peer_suffix_in_br_output(self):
        """Accept the kernel ifname when ip -br decorates it with its peer index."""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "lo UNKNOWN 127.0.0.1/8\neth0@if15 UP 192.168.1.10/24\n",
            "lo\neth0\n",
        ]

        with self.assertLogs(level="INFO") as captured_logs:
            result = ingress_shaping.verify_interface(
                input_interface_list=["eth0"],
                node="test-node",
                pod_template=mock_pod_template,
                kubecli=mock_kubecli,
                image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools",
            )

        self.assertEqual(result, ["eth0"])
        self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 2)
        self.assertEqual(
            mock_kubecli.exec_cmd_in_pod.call_args_list[1].args[0],
            ["ls -1 /sys/class/net"],
        )
        self.assertTrue(
            any(
                "eth0" in message and "test-node" in message and "/sys/class/net" in message
                for message in captured_logs.output
            )
        )

    def test_verify_interface_preserves_configured_display_name(self):
        """Keep accepting and returning the exact interface token users configured."""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"
        mock_kubecli.exec_cmd_in_pod.return_value = "eth0@if15 UP 192.168.1.10/24\n"

        result = ingress_shaping.verify_interface(
            input_interface_list=["eth0@if15"],
            node="test-node",
            pod_template=mock_pod_template,
            kubecli=mock_kubecli,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools",
        )

        self.assertEqual(result, ["eth0@if15"])
        mock_kubecli.exec_cmd_in_pod.assert_called_once()

    def test_verify_interface_accepts_literal_at_in_actual_ifname(self):
        """Match an actual ifname containing @ exactly as reported by ip -j."""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "eth0@if15@if17 UP 192.168.1.10/24\n",
            "eth0@if15\n",
        ]

        result = ingress_shaping.verify_interface(
            input_interface_list=["eth0@if15"],
            node="test-node",
            pod_template=mock_pod_template,
            kubecli=mock_kubecli,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools",
        )

        self.assertEqual(result, ["eth0@if15"])

    def test_verify_interface_with_invalid_interface(self):
        """Test verifying interface with an interface that doesn't exist"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml_content"

        mock_kubecli.create_pod.return_value = None
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "eth0             UP             192.168.1.10/24\nlo UNKNOWN 127.0.0.1/8\n",
            "eth0\nlo\n",
        ]
        mock_kubecli.delete_pod.return_value = None

        with self.assertRaises(Exception) as context:
            ingress_shaping.verify_interface(
                input_interface_list=["eth0", "eth99"],
                node="test-node",
                pod_template=mock_pod_template,
                kubecli=mock_kubecli,
                image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
            )

        self.assertIn("Interface eth99 not found", str(context.exception))

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.check_node_ingress_qdiscs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_default_interface')
    def test_get_node_interfaces_with_label_selector(self, mock_get_default_interface, mock_check_qdiscs):
        """Test getting node interfaces using label selector"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_kubecli.get_node.return_value = ["node1", "node2"]
        mock_get_default_interface.return_value = ["eth0"]

        result = ingress_shaping.get_node_interfaces(
            node_interface_dict=None,
            label_selector="node-role.kubernetes.io/worker",
            instance_count=2,
            pod_template=mock_pod_template,
            kubecli=mock_kubecli,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

        self.assertEqual(result, {"node1": ["eth0"], "node2": ["eth0"]})
        self.assertEqual(mock_get_default_interface.call_count, 2)
        mock_check_qdiscs.assert_called_once_with(
            {"node1": ["eth0"], "node2": ["eth0"]}, mock_pod_template, mock_kubecli,
            "quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.check_node_ingress_qdiscs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.verify_interface')
    def test_get_node_interfaces_with_node_dict(self, mock_verify_interface, mock_check_qdiscs):
        """Test getting node interfaces with provided node interface dictionary"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_kubecli.get_node.return_value = ["node1"]
        mock_verify_interface.return_value = ["eth0", "eth1"]

        result = ingress_shaping.get_node_interfaces(
            node_interface_dict={"node1": ["eth0", "eth1"]},
            label_selector=None,
            instance_count=1,
            pod_template=mock_pod_template,
            kubecli=mock_kubecli,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

        self.assertEqual(result, {"node1": ["eth0", "eth1"]})
        mock_verify_interface.assert_called_once()
        mock_check_qdiscs.assert_called_once()

    def test_ingress_qdisc_probe_accepts_clean_interface(self):
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "qdisc noqueue 0: root refcnt 2\nKRKN_QDISC_PROBE_OK\n"
        )

        ingress_shaping.check_node_ingress_qdiscs(
            {"node1": ["eth0"]}, mock_pod_template, mock_kubecli, "test-image"
        )

        self.assertIn("tc qdisc show dev eth0", mock_kubecli.exec_cmd_in_pod.call_args.args[0][0])
        mock_kubecli.delete_pod.assert_called_once()
        mock_kubecli.create_job.assert_not_called()

    def test_ingress_qdisc_probe_rejects_existing_qdisc(self):
        for kind in ("ingress", "clsact"):
            with self.subTest(kind=kind):
                mock_kubecli = Mock()
                mock_pod_template = Mock()
                mock_pod_template.render.return_value = "pod_yaml"
                mock_kubecli.exec_cmd_in_pod.return_value = (
                    f"qdisc {kind} ffff: parent ffff:fff1\nKRKN_QDISC_PROBE_OK\n"
                )

                with self.assertRaisesRegex(RuntimeError, f"already has an ingress qdisc \\({kind}\\)"):
                    ingress_shaping.check_node_ingress_qdiscs(
                        {"node1": ["eth0"]}, mock_pod_template, mock_kubecli, "test-image"
                    )

                mock_kubecli.delete_pod.assert_called_once()
                mock_kubecli.create_job.assert_not_called()

    def test_ingress_qdisc_probe_fails_closed_when_tc_fails(self):
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"
        mock_kubecli.exec_cmd_in_pod.return_value = 'Cannot find device "eth0"'

        with self.assertRaisesRegex(RuntimeError, "Could not inspect qdiscs"):
            ingress_shaping.check_node_ingress_qdiscs(
                {"node1": ["eth0"]}, mock_pod_template, mock_kubecli, "test-image"
            )

        mock_kubecli.delete_pod.assert_called_once()
        mock_kubecli.create_job.assert_not_called()

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.verify_interface')
    def test_get_node_interfaces_rejects_occupied_qdisc_before_shaping(self, mock_verify_interface):
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"
        mock_kubecli.get_node.return_value = ["node1"]
        mock_verify_interface.return_value = ["eth0"]
        mock_kubecli.exec_cmd_in_pod.return_value = (
            "qdisc ingress ffff: parent ffff:fff1\nKRKN_QDISC_PROBE_OK\n"
        )

        with self.assertRaisesRegex(RuntimeError, "already has an ingress qdisc"):
            ingress_shaping.get_node_interfaces(
                {"node1": ["eth0"]}, None, 1, mock_pod_template, mock_kubecli, "test-image"
            )

        mock_kubecli.create_job.assert_not_called()
        mock_kubecli.delete_pod.assert_called_once()

    def test_get_node_interfaces_no_selector_no_dict(self):
        """Test that exception is raised when both node dict and label selector are missing"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()

        with self.assertRaises(Exception) as context:
            ingress_shaping.get_node_interfaces(
                node_interface_dict=None,
                label_selector=None,
                instance_count=1,
                pod_template=mock_pod_template,
                kubecli=mock_kubecli,
                image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
            )

        self.assertIn("label selector must be provided", str(context.exception))

    def test_create_ifb(self):
        """Test creating virtual interfaces"""
        mock_kubecli = Mock()
        mock_kubecli.exec_cmd_in_pod.return_value = "IFB_CREATED\nIFB_READY\n"

        ingress_shaping.create_ifb(kubecli=mock_kubecli, number=2, pod_name="test-pod")

        self.assertEqual(mock_kubecli.exec_cmd_in_pod.call_count, 2)
        first_call = mock_kubecli.exec_cmd_in_pod.call_args_list[0]
        self.assertIn("ip link add dev ifb0 type ifb", first_call.args[0][0])

    def test_create_ifb_failure_removes_only_owned_device(self):
        mock_kubecli = Mock()
        mock_kubecli.exec_cmd_in_pod.side_effect = [
            "IFB_CREATED\nIFB_READY\n", "RTNETLINK answers: File exists", ""
        ]

        with self.assertRaisesRegex(RuntimeError, "Could not create ifb1"):
            ingress_shaping.create_ifb(mock_kubecli, 2, "test-pod")

        cleanup = mock_kubecli.exec_cmd_in_pod.call_args_list[2].args[0][0]
        self.assertEqual(cleanup, "ip link del dev ifb0")

    def test_delete_ifb(self):
        """Test deleting virtual interfaces"""
        mock_kubecli = Mock()
        mock_kubecli.exec_cmd_in_pod.return_value = "IFB_DELETED\n"

        ingress_shaping.delete_ifb(kubecli=mock_kubecli, pod_name="test-pod", number=1)

        mock_kubecli.exec_cmd_in_pod.assert_called_once()
        call_args = mock_kubecli.exec_cmd_in_pod.call_args[0][0]
        self.assertIn("ip link del dev ifb0", call_args[0])

    def test_delete_ifb_legacy_call_remains_supported(self):
        mock_kubecli = Mock()

        ingress_shaping.delete_ifb(mock_kubecli, "test-pod")

        mock_kubecli.exec_cmd_in_pod.assert_called_once_with(
            ["/host", "modprobe", "-r", "ifb"], "test-pod", "default",
            base_command="chroot",
        )

    def test_get_job_pods(self):
        """Test getting pods associated with a job"""
        mock_kubecli = Mock()
        mock_api_response = Mock()
        mock_api_response.metadata.labels = {"controller-uid": "test-uid-123"}
        mock_kubecli.list_pods.return_value = ["pod1", "pod2"]

        result = ingress_shaping.get_job_pods(kubecli=mock_kubecli, api_response=mock_api_response)

        self.assertEqual(result, "pod1")
        mock_kubecli.list_pods.assert_called_once_with(
            label_selector="controller-uid=test-uid-123",
            namespace="default"
        )

    @patch('time.sleep', return_value=None)
    @patch('time.time')
    def test_wait_for_job_success(self, mock_time, mock_sleep):
        """Test waiting for jobs to complete successfully"""
        mock_kubecli = Mock()
        mock_time.side_effect = [0, 10, 20]

        mock_response1 = Mock()
        mock_response1.status.succeeded = 1
        mock_response1.status.failed = None

        mock_response2 = Mock()
        mock_response2.status.succeeded = 1
        mock_response2.status.failed = None

        mock_kubecli.get_job_status.side_effect = [mock_response1, mock_response2]

        ingress_shaping.wait_for_job(
            kubecli=mock_kubecli,
            job_list=["job1", "job2"],
            timeout=300
        )

        self.assertEqual(mock_kubecli.get_job_status.call_count, 2)

    @patch('time.sleep', return_value=None)
    @patch('time.time')
    def test_wait_for_job_reports_failed_job(self, mock_time, mock_sleep):
        mock_kubecli = Mock()
        mock_time.return_value = 0
        response = Mock()
        response.status.succeeded = None
        response.status.failed = 1
        mock_kubecli.get_job_status.return_value = response

        with self.assertRaisesRegex(RuntimeError, "Ingress job job1 failed"):
            ingress_shaping.wait_for_job(mock_kubecli, ["job1"])

        mock_sleep.assert_not_called()

    @patch('time.sleep', return_value=None)
    @patch('time.time')
    def test_wait_for_job_timeout(self, mock_time, mock_sleep):
        """Test waiting for jobs times out"""
        mock_kubecli = Mock()
        mock_time.side_effect = [0, 350]

        mock_response = Mock()
        mock_response.status.succeeded = None
        mock_response.status.failed = None

        mock_kubecli.get_job_status.return_value = mock_response

        with self.assertRaises(Exception) as context:
            ingress_shaping.wait_for_job(
                kubecli=mock_kubecli,
                job_list=["job1"],
                timeout=300
            )

        self.assertIn("timeout", str(context.exception))

    def test_delete_jobs(self):
        """Test deleting jobs"""
        mock_kubecli = Mock()

        mock_response = Mock()
        mock_response.status.failed = None
        mock_kubecli.get_job_status.return_value = mock_response
        mock_kubecli.delete_job.return_value = None

        ingress_shaping.delete_jobs(
            kubecli=mock_kubecli,
            job_list=["job1", "job2"]
        )

        self.assertEqual(mock_kubecli.get_job_status.call_count, 2)
        self.assertEqual(mock_kubecli.delete_job.call_count, 2)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_job_pods')
    def test_delete_jobs_with_failed_job(self, mock_get_job_pods):
        """Test deleting jobs when one has failed"""
        mock_kubecli = Mock()

        mock_response = Mock()
        mock_response.status.failed = 1

        mock_pod_status = Mock()
        mock_pod_status.status.container_statuses = []

        mock_log_response = Mock()
        mock_log_response.data.decode.return_value = "Error log content"

        mock_kubecli.get_job_status.return_value = mock_response
        mock_get_job_pods.return_value = "failed-pod"
        mock_kubecli.read_pod.return_value = mock_pod_status
        mock_kubecli.get_pod_log.return_value = mock_log_response
        mock_kubecli.delete_job.return_value = None

        ingress_shaping.delete_jobs(
            kubecli=mock_kubecli,
            job_list=["failed-job"]
        )

        mock_kubecli.read_pod.assert_called_once()
        mock_kubecli.get_pod_log.assert_called_once()

    def test_get_ingress_cmd_basic(self):
        """Test generating ingress traffic shaping commands"""
        result = ingress_shaping.get_ingress_cmd(
            interface_list=["eth0"],
            network_parameters={"latency": "50ms"},
            duration=120
        )

        self.assertIn("tc qdisc add dev eth0 handle ffff: ingress", result)
        self.assertTrue(result.startswith("set -e;"))
        self.assertIn("tc filter add dev eth0", result)
        self.assertIn("ifb0", result)
        self.assertIn("delay 50ms", result)
        self.assertIn("sleep 120", result)
        self.assertIn("tc qdisc del", result)

    def test_ingress_command_cleans_only_qdiscs_it_created(self):
        command = ingress_shaping.get_ingress_cmd(
            ["eth0"], {"latency": "2s"}, duration=0
        )
        cases = (
            ("", 0, True, True),
            ("qdisc add dev eth0 handle ffff: ingress", 2, False, False),
            ("filter add dev eth0 parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev ifb0", 2, False, True),
        )
        for failed_call, expected_status, delete_ifb, delete_ingress in cases:
            with self.subTest(failed_call=failed_call), tempfile.TemporaryDirectory() as tmp:
                tc_log = Path(tmp) / "tc.log"
                fake_tc = Path(tmp) / "tc"
                fake_tc.write_text(
                    '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TC_LOG"\n'
                    '[ "$*" = "$TC_FAIL" ] && exit 2\nexit 0\n'
                )
                fake_tc.chmod(0o755)
                fake_sleep = Path(tmp) / "sleep"
                fake_sleep.write_text("#!/bin/sh\nexit 0\n")
                fake_sleep.chmod(0o755)
                env = dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}",
                           TC_LOG=str(tc_log), TC_FAIL=failed_call)

                result = subprocess.run(
                    ["/bin/sh", "-c", command], env=env, capture_output=True, text=True
                )
                calls = tc_log.read_text().splitlines()
                self.assertEqual(result.returncode, expected_status, result.stderr)
                self.assertEqual("qdisc del dev ifb0 root" in calls, delete_ifb)
                self.assertEqual(
                    "qdisc del dev eth0 handle ffff: ingress" in calls, delete_ingress
                )

    def test_ingress_command_renders_as_valid_job_yaml(self):
        command = ingress_shaping.get_ingress_cmd(
            ["eth0"], {"latency": "2s"}, duration=12
        )
        template = ingress_shaping.Environment(
            loader=ingress_shaping.FileSystemLoader(
                str(Path(ingress_shaping.__file__).parent)
            )
        ).get_template("job.j2")
        job = ingress_shaping.yaml.safe_load(
            template.render(
                jobname="test", nodename="kind-worker", image="test-image", cmd=command
            )
        )

        self.assertEqual(
            job["spec"]["template"]["spec"]["containers"][0]["command"],
            ["/bin/sh", "-c", command],
        )

    def test_get_ingress_cmd_multiple_interfaces(self):
        """Test generating commands for multiple interfaces"""
        result = ingress_shaping.get_ingress_cmd(
            interface_list=["eth0", "eth1"],
            network_parameters={"latency": "50ms", "bandwidth": "100mbit"},
            duration=120
        )

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
    def test_apply_ingress_filter(self, mock_get_cmd, mock_create_virtual, mock_yaml):
        """Test applying ingress filters to a node"""
        mock_kubecli = Mock()
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
        mock_kubecli.create_job.return_value = Mock()

        result = ingress_shaping.apply_ingress_filter(
            cfg=mock_cfg,
            interface_list=["eth0"],
            node="node1",
            pod_template=mock_pod_template,
            job_template=mock_job_template,
            kubecli=mock_kubecli,
            create_interfaces=True,
            param_selector="all",
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

        mock_create_virtual.assert_called_once()
        mock_get_cmd.assert_called_once()
        mock_kubecli.create_job.assert_called_once()
        self.assertEqual(result, "test-job")

    def test_create_virtual_interfaces(self):
        """Test creating virtual interfaces on a node"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"

        mock_kubecli.create_pod.return_value = None
        mock_kubecli.exec_cmd_in_pod.return_value = "IFB_CREATED\nIFB_READY\n"
        mock_kubecli.delete_pod.return_value = None

        ingress_shaping.create_virtual_interfaces(
            kubecli=mock_kubecli,
            interface_list=["eth0", "eth1"],
            node="test-node",
            pod_template=mock_pod_template,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools"
        )

        mock_kubecli.create_pod.assert_called_once()
        mock_kubecli.delete_pod.assert_called_once()

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_ifb')
    def test_delete_virtual_interfaces(self, mock_delete_ifb):
        """Test deleting virtual interfaces from nodes"""
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"

        mock_kubecli.create_pod.return_value = None
        mock_kubecli.delete_pod.return_value = None

        ingress_shaping.delete_virtual_interfaces(
            kubecli=mock_kubecli,
            node_list=["node1", "node2"],
            pod_template=mock_pod_template,
            image="quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-tools",
            interface_counts={"node1": 1, "node2": 1},
        )

        self.assertEqual(mock_kubecli.create_pod.call_count, 2)
        self.assertEqual(mock_delete_ifb.call_count, 2)
        self.assertTrue(all(
            call.kwargs == {"number": 1} for call in mock_delete_ifb.call_args_list
        ))
        self.assertEqual(mock_kubecli.delete_pod.call_count, 2)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_ifb')
    def test_delete_virtual_interfaces_legacy_call_remains_supported(self, mock_delete_ifb):
        mock_kubecli = Mock()
        mock_pod_template = Mock()
        mock_pod_template.render.return_value = "pod_yaml"

        ingress_shaping.delete_virtual_interfaces(
            mock_kubecli, ["node1"], mock_pod_template, "test-image"
        )

        mock_delete_ifb.assert_called_once_with(
            mock_kubecli, unittest.mock.ANY, number=None
        )

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.wait_for_job')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.apply_ingress_filter')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.KrknKubernetes')
    def test_network_chaos_parallel_execution(
        self, mock_kubecli_class, mock_get_nodes, mock_apply_filter,
        mock_wait_job, mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos with parallel execution"""
        mock_kubecli_class.return_value = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_get_nodes.return_value = {"node1": ["eth0"], "node2": ["eth1"]}
        mock_apply_filter.side_effect = ["job1", "job2"]

        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=2,
            network_params={"latency": "50ms"},
            execution_type="parallel",
            test_duration=120,
            wait_duration=30
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

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
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.KrknKubernetes')
    def test_network_chaos_serial_execution(
        self, mock_kubecli_class, mock_get_nodes, mock_apply_filter,
        mock_wait_job, mock_delete_virtual, mock_delete_jobs, mock_sleep, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos with serial execution"""
        mock_kubecli_class.return_value = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_get_nodes.return_value = {"node1": ["eth0"]}
        mock_apply_filter.return_value = "job1"

        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms", "bandwidth": "100mbit"},
            execution_type="serial",
            test_duration=120,
            wait_duration=30
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        self.assertEqual(output_id, "success")
        self.assertEqual(output_data.execution_type, "serial")
        self.assertEqual(mock_apply_filter.call_count, 2)
        self.assertEqual(mock_wait_job.call_count, 2)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.KrknKubernetes')
    def test_network_chaos_invalid_execution_type(
        self, mock_kubecli_class, mock_get_nodes, mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos with invalid execution type"""
        mock_kubecli_class.return_value = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_get_nodes.return_value = {"node1": ["eth0"]}

        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms"},
            execution_type="invalid_type",
            test_duration=120
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        self.assertEqual(output_id, "error")
        self.assertIn("Invalid execution type", output_data.error)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.KrknKubernetes')
    def test_network_chaos_get_nodes_error(
        self, mock_kubecli_class, mock_get_nodes, mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos when getting nodes fails"""
        mock_kubecli_class.return_value = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_get_nodes.side_effect = Exception("Failed to get nodes")

        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms"}
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        self.assertEqual(output_id, "error")
        self.assertIn("Failed to get nodes", output_data.error)

    @patch('krkn.scenario_plugins.native.network.ingress_shaping.Environment')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.FileSystemLoader')
    @patch('yaml.safe_load')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_jobs')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.delete_virtual_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.apply_ingress_filter')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.get_node_interfaces')
    @patch('krkn.scenario_plugins.native.network.ingress_shaping.KrknKubernetes')
    def test_network_chaos_apply_filter_error(
        self, mock_kubecli_class, mock_get_nodes, mock_apply_filter,
        mock_delete_virtual, mock_delete_jobs, mock_yaml,
        mock_file_loader, mock_env
    ):
        """Test network chaos when applying filter fails"""
        mock_kubecli_class.return_value = Mock()
        mock_yaml.return_value = {"metadata": {"name": "test-pod"}}
        mock_get_nodes.return_value = {"node1": ["eth0"]}
        mock_apply_filter.side_effect = Exception("Failed to apply filter")

        cfg = ingress_shaping.NetworkScenarioConfig(
            label_selector="node-role.kubernetes.io/worker",
            instance_count=1,
            network_params={"latency": "50ms"},
            execution_type="parallel"
        )

        output_id, output_data = ingress_shaping.network_chaos(params=cfg, run_id="test-run")

        self.assertEqual(output_id, "error")
        self.assertIn("Failed to apply filter", output_data.error)
        mock_delete_virtual.assert_called_once()


if __name__ == "__main__":
    unittest.main()
