#!/usr/bin/env python3

"""
Test suite for PvcScenarioPlugin class

Usage:
    python -m coverage run -a -m unittest tests/test_pvc_scenario_plugin.py -v

Assisted By: Claude Code
"""

import unittest
from unittest.mock import MagicMock, patch

from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.pvc.pvc_scenario_plugin import PvcScenarioPlugin
from types import SimpleNamespace
import base64
import json
import yaml
import time
from krkn.rollback.config import RollbackContent


class TestPvcScenarioPlugin(unittest.TestCase):

    def setUp(self):
        """
        Set up test fixtures for PvcScenarioPlugin
        """
        self.plugin = PvcScenarioPlugin()

    def test_get_scenario_types(self):
        """
        Test get_scenario_types returns correct scenario type
        """
        result = self.plugin.get_scenario_types()

        self.assertEqual(result, ["pvc_scenarios"])
        self.assertEqual(len(result), 1)

    def test_to_kbytes_valid_and_invalid(self):
        plugin = PvcScenarioPlugin()
        # valid value
        val = plugin.to_kbytes("10Ki")
        self.assertEqual(val, 10)

        # invalid value should raise
        with self.assertRaises(RuntimeError):
            plugin.to_kbytes("10k")

    def test_remove_temp_file_success_and_failure(self):
        plugin = PvcScenarioPlugin()
        kubecli = MagicMock()
        # exec_cmd_in_pod called twice: rm and ls
        kubecli.exec_cmd_in_pod.side_effect = [None, "total 0\n-rw-r--r-- 1 root root 0 Jan 1 00:00 otherfile"]

        # should not raise when file is absent after removal
        plugin.remove_temp_file("kraken.tmp", "/mnt/kraken/kraken.tmp", "pod", "ns", "cont", "/mnt/kraken", 1, kubecli)

        # Now simulate failure: ls still shows the file -> should raise RuntimeError
        kubecli2 = MagicMock()
        kubecli2.exec_cmd_in_pod.side_effect = [None, "total 0\n-rw-r--r-- 1 root root 0 Jan 1 00:00 kraken.tmp"]
        with self.assertRaises(RuntimeError):
            plugin.remove_temp_file("kraken.tmp", "/mnt/kraken/kraken.tmp", "pod", "ns", "cont", "/mnt/kraken", 1, kubecli2)

    def test_rollback_temp_file_success_and_warning(self):
        plugin = PvcScenarioPlugin()

        # Build rollback payload
        rollback_data = {
            "pod_name": "pod",
            "container_name": "cont",
            "full_path": "/mnt/kraken/kraken.tmp",
            "file_name": "kraken.tmp",
            "mount_path": "/mnt/kraken"
        }
        encoded = base64.b64encode(json.dumps(rollback_data).encode('utf-8')).decode('utf-8')

        rollback_content = SimpleNamespace(namespace="ns", resource_identifier=encoded)

        lib_tel = MagicMock()
        kubecli = MagicMock()
        # First exec: rm -f -> returns something; second exec: ls -> no file
        kubecli.exec_cmd_in_pod.side_effect = ["rm ok", "total 0\n-rw-r--r-- 1 root root 0 Jan 1 00:00 otherfile"]
        lib_tel.get_lib_kubernetes.return_value = kubecli

        # Should not raise
        PvcScenarioPlugin.rollback_temp_file(rollback_content, lib_tel)

        # Now simulate file still present (warning path)
        kubecli2 = MagicMock()
        kubecli2.exec_cmd_in_pod.side_effect = ["rm ok", "total 0\n-rw-r--r-- 1 root root 0 Jan 1 00:00 kraken.tmp"]
        lib_tel2 = MagicMock()
        lib_tel2.get_lib_kubernetes.return_value = kubecli2

        # Should not raise (warning only)
        PvcScenarioPlugin.rollback_temp_file(rollback_content, lib_tel2)

    def test_run_input_validation_missing_namespace(self):
        plugin = PvcScenarioPlugin()

        # scenario file with namespace set to None
        cfg = {"pvc_scenario": {"namespace": None, "pvc_name": None, "pod_name": None}}

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=MagicMock(), scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_creates_temp_file_with_fallocate(self):
        """Run full happy path where fallocate exists and file creation succeeds."""
        plugin = PvcScenarioPlugin()
        plugin.rollback_handler = MagicMock()

        cfg = {
            "pvc_scenario": {
                "pvc_name": "mypvc",
                "pod_name": None,
                "namespace": "ns",
                "fill_percentage": "60",
                "duration": 0,
                "block_size": "102400",
            }
        }

        kubecli = MagicMock()
        # get_pvc_info returns object with podNames
        pvc_obj = SimpleNamespace(podNames=["mypod"])
        kubecli.get_pvc_info.return_value = pvc_obj

        # pod object: volumes and containers
        vol = SimpleNamespace(pvcName="mypvc", name="vol1")
        mount = SimpleNamespace(name="vol1", mountPath="/mnt")
        container = SimpleNamespace(name="cont", volumeMounts=[mount])
        pod_obj = SimpleNamespace(volumes=[vol], containers=[container])
        kubecli.get_pod_info.return_value = pod_obj

        # exec_cmd_in_pod: df -> tokens where index2=used, index3=avail
        df_output = "filesystem 0 100 100 50% /mnt"
        # sequence of exec calls: df, command -v fallocate, command -v dd, create file, ls
        kubecli.exec_cmd_in_pod.side_effect = [
            df_output,
            "/usr/bin/fallocate",
            None,
            "",
            "-rw-r-- 1 root root 0 Jan 1 00:00 kraken.tmp",
            # responses for remove_temp_file: rm and ls (no kraken.tmp present)
            "rm ok",
            "total 0\n-rw-r--r-- 1 root root 0 Jan 1 00:00 otherfile",
        ]

        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        # patch open/yaml to load our cfg
        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                # avoid actual sleep and cerberus publish
                with patch("time.sleep", return_value=None):
                    with patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.cerberus.publish_kraken_status"):
                        ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)

    def test_run_pvc_has_no_pods(self):
        """When PVC has no pods, random.choice will raise and run should return 1"""
        plugin = PvcScenarioPlugin()
        cfg = {"pvc_scenario": {"pvc_name": "mypvc", "namespace": "ns"}}

        kubecli = MagicMock()
        pvc_obj = SimpleNamespace(podNames=[])
        kubecli.get_pvc_info.return_value = pvc_obj
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_pod_not_found(self):
        """If pod is not found, run should return 1"""
        plugin = PvcScenarioPlugin()
        cfg = {"pvc_scenario": {"pod_name": "mypod", "namespace": "ns"}}

        kubecli = MagicMock()
        kubecli.get_pod_info.return_value = None
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_invalid_fill_percentage(self):
        """If target fill percentage is lower than current, run should return 1"""
        plugin = PvcScenarioPlugin()
        cfg = {"pvc_scenario": {"pod_name": "mypod", "namespace": "ns", "fill_percentage": "40"}}

        kubecli = MagicMock()
        # df output implies current fill 50%
        kubecli.exec_cmd_in_pod.return_value = "filesystem 0 100 100 50% /mnt"
        pod_obj = SimpleNamespace(volumes=[SimpleNamespace(pvcName="pvc", name="vol1")], containers=[SimpleNamespace(name="cont", volumeMounts=[SimpleNamespace(name="vol1", mountPath="/mnt")])])
        kubecli.get_pod_info.return_value = pod_obj
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_dd_fallback(self):
        """If fallocate missing but dd present, the dd branch should be used and succeed"""
        plugin = PvcScenarioPlugin()
        plugin.rollback_handler = MagicMock()

        cfg = {"pvc_scenario": {"pvc_name": "mypvc", "namespace": "ns", "fill_percentage": "60", "block_size": "1024", "duration": 0}}

        kubecli = MagicMock()
        pvc_obj = SimpleNamespace(podNames=["mypod"])
        kubecli.get_pvc_info.return_value = pvc_obj
        vol = SimpleNamespace(pvcName="mypvc", name="vol1")
        mount = SimpleNamespace(name="vol1", mountPath="/mnt")
        container = SimpleNamespace(name="cont", volumeMounts=[mount])
        pod_obj = SimpleNamespace(volumes=[vol], containers=[container])
        kubecli.get_pod_info.return_value = pod_obj

        # sequence: df, command -v fallocate (None), command -v dd (present), create dd, ls, rm, ls after rm
        kubecli.exec_cmd_in_pod.side_effect = ["filesystem 0 100 100 50% /mnt", None, "/usr/bin/dd", "", "-rw-r-- kraken.tmp", "rm ok", "total 0\n-rw-r-- otherfile"]

        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch("time.sleep", return_value=None):
                    with patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.cerberus.publish_kraken_status"):
                        ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)

    def test_run_pod_does_not_use_pvc(self):
        """If pod has no pvc volumes, run should return 1"""
        plugin = PvcScenarioPlugin()
        cfg = {"pvc_scenario": {"pod_name": "mypod", "namespace": "ns"}}

        kubecli = MagicMock()
        # volumes exist but none have pvcName set
        pod_obj = SimpleNamespace(volumes=[SimpleNamespace(pvcName=None, name="vol1")], containers=[])
        kubecli.get_pod_info.return_value = pod_obj
        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_run_file_creation_failure_calls_remove(self):
        """If file creation fails (ls doesn't show file), plugin should call remove_temp_file and return 1"""
        plugin = PvcScenarioPlugin()
        plugin.rollback_handler = MagicMock()

        cfg = {
            "pvc_scenario": {
                "pvc_name": "mypvc",
                "pod_name": None,
                "namespace": "ns",
                "fill_percentage": "60",
                "duration": 0,
                "block_size": "102400",
            }
        }

        kubecli = MagicMock()
        pvc_obj = SimpleNamespace(podNames=["mypod"])
        kubecli.get_pvc_info.return_value = pvc_obj

        vol = SimpleNamespace(pvcName="mypvc", name="vol1")
        mount = SimpleNamespace(name="vol1", mountPath="/mnt")
        container = SimpleNamespace(name="cont", volumeMounts=[mount])
        pod_obj = SimpleNamespace(volumes=[vol], containers=[container])
        kubecli.get_pod_info.return_value = pod_obj

        # df, fallocate present, dd None, create file exec, ls (no kraken.tmp), THEN remove_temp_file will be patched
        kubecli.exec_cmd_in_pod.side_effect = [
            "filesystem 0 100 100 50% /mnt",
            "/usr/bin/fallocate",
            None,
            "",  # create file exec
            "total 0\n-rw-r--r-- 1 root root 0 Jan 1 00:00 otherfile",
        ]

        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch.object(PvcScenarioPlugin, 'remove_temp_file') as mock_remove:
                    ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        mock_remove.assert_called()
        self.assertEqual(ret, 1)

    def test_run_with_pvc_and_pod_name_provided_ignores_pod_name(self):
        """When both pvc_name and pod_name are provided, pod_name is ignored and flow continues"""
        plugin = PvcScenarioPlugin()
        plugin.rollback_handler = MagicMock()

        cfg = {
            "pvc_scenario": {
                "pvc_name": "mypvc",
                "pod_name": "origpod",
                "namespace": "ns",
                "fill_percentage": "60",
                "duration": 0,
                "block_size": "102400",
            }
        }

        kubecli = MagicMock()
        pvc_obj = SimpleNamespace(podNames=["selectedpod"])
        kubecli.get_pvc_info.return_value = pvc_obj
        vol = SimpleNamespace(pvcName="mypvc", name="vol1")
        mount = SimpleNamespace(name="vol1", mountPath="/mnt")
        container = SimpleNamespace(name="cont", volumeMounts=[mount])
        pod_obj = SimpleNamespace(volumes=[vol], containers=[container])
        kubecli.get_pod_info.return_value = pod_obj

        kubecli.exec_cmd_in_pod.side_effect = [
            "filesystem 0 100 100 50% /mnt",
            "/usr/bin/fallocate",
            None,
            "",
            "-rw-r-- 1 root root 0 Jan 1 00:00 kraken.tmp",
            "rm ok",
            "total 0\n-rw-r--r-- 1 root root 0 Jan 1 00:00 otherfile",
        ]

        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                with patch("time.sleep", return_value=None):
                    with patch("krkn.scenario_plugins.pvc.pvc_scenario_plugin.cerberus.publish_kraken_status"):
                        ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 0)

    def test_run_no_binaries(self):
        """If neither fallocate nor dd are present, run should return 1"""
        plugin = PvcScenarioPlugin()
        cfg = {"pvc_scenario": {"pvc_name": "mypvc", "namespace": "ns", "fill_percentage": "60"}}

        kubecli = MagicMock()
        pvc_obj = SimpleNamespace(podNames=["mypod"])
        kubecli.get_pvc_info.return_value = pvc_obj
        vol = SimpleNamespace(pvcName="mypvc", name="vol1")
        mount = SimpleNamespace(name="vol1", mountPath="/mnt")
        container = SimpleNamespace(name="cont", volumeMounts=[mount])
        pod_obj = SimpleNamespace(volumes=[vol], containers=[container])
        kubecli.get_pod_info.return_value = pod_obj

        # both missing
        kubecli.exec_cmd_in_pod.side_effect = ["filesystem 0 100 100 50% /mnt", None, None]

        lib_tel = MagicMock()
        lib_tel.get_lib_kubernetes.return_value = kubecli

        with patch("builtins.open", unittest.mock.mock_open(read_data=yaml.dump(cfg))):
            with patch("yaml.full_load", return_value=cfg):
                ret = plugin.run(run_uuid="uuid", scenario="scenario.yaml", krkn_config={}, lib_telemetry=lib_tel, scenario_telemetry=MagicMock())

        self.assertEqual(ret, 1)

    def test_rollback_temp_file_exception_path(self):
        """Simulate exec raising during rollback to exercise exception handling"""
        rollback_data = {"pod_name": "pod", "container_name": "cont", "full_path": "/mnt/kraken/kraken.tmp", "file_name": "kraken.tmp", "mount_path": "/mnt/kraken"}
        encoded = base64.b64encode(json.dumps(rollback_data).encode('utf-8')).decode('utf-8')
        rollback_content = SimpleNamespace(namespace="ns", resource_identifier=encoded)

        lib_tel = MagicMock()
        kubecli = MagicMock()
        kubecli.exec_cmd_in_pod.side_effect = Exception("boom")
        lib_tel.get_lib_kubernetes.return_value = kubecli

        # should not raise
        PvcScenarioPlugin.rollback_temp_file(rollback_content, lib_tel)

if __name__ == "__main__":
    unittest.main()
