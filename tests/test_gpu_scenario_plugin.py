import json
import os
import tempfile
import threading
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from kubernetes.client import ApiClient, CoreV1Api
from kubernetes.client.exceptions import ApiException
from urllib3.response import HTTPResponse

from krkn.rollback.config import RollbackContent

from krkn.scenario_plugins.gpu.gpu_scenario_plugin import GpuScenarioPlugin


class GpuScenarioPluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = GpuScenarioPlugin()
        runtime_patch = patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.NodeV1Api")
        self.runtime_api = runtime_patch.start().return_value
        self.addCleanup(runtime_patch.stop)

    def test_environment_overrides_and_selector_validation(self):
        config = {"node-selector": "role=gpu", "gpu-vram": "20%", "image": "image"}
        with patch.dict(os.environ, {"NODE_SELECTOR": "pool=gpu", "GPU_VRAM": "2Gi"}):
            result = self.plugin._load_config(config)
        self.assertEqual(result["node-selector"], "pool=gpu")
        self.assertEqual(result["gpu-vram"], "2Gi")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertLogs(level="ERROR") as captured:
                result = self._run_with_config(
                    {"node-selector": "a=b", "pod-label-selector": "app=gpu"}
                )
        self.assertEqual(result, 1)
        self.assertIn("specify exactly one", captured.output[0])

    def test_compute_fault_generates_worker_without_vram_allocation(self):
        config = {
            "fault-type": "compute-pressure", "node-selector": "role=gpu",
            "gpu-ids": "1,0", "gpu-compute-duty-cycle": "20%,30%", "duration": 10, "image": "image",
        }
        with patch.dict(os.environ, {"GPU_COMPUTE_DUTY_CYCLE": "35%, 40"}, clear=True), \
                patch.object(self.plugin, "_select_nodes", return_value=["n1"]), \
                patch.object(self.plugin, "_register_rollback", return_value=True), \
                patch.object(self.plugin, "_deploy_workers") as deploy, \
                patch.object(self.plugin, "_coordinate"), \
                patch.object(self.plugin, "_delete_bounded", return_value=True):
            self.assertEqual(self._run_with_config(config), 0)
        worker = deploy.call_args.args[2][0]["spec"]["containers"][0]
        env = {entry["name"]: entry["value"] for entry in worker["env"]}
        self.assertEqual(env["GPU_FAULT_TYPE"], "compute-pressure")
        self.assertEqual(env["GPU_IDS"], "1,0")
        self.assertEqual(env["GPU_COMPUTE_DUTY_CYCLE"], "35,40")
        self.assertNotIn("GPU_VRAM", env)
        self.assertNotIn("GPU_MEMORY_RESERVE", env)

    def test_compute_duty_cycle_count_must_match_explicit_gpu_ids(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(self.plugin, "_select_nodes", return_value=["n1"]), \
                patch.object(self.plugin, "_deploy_workers") as deploy, \
                self.assertLogs(level="ERROR") as captured:
            self.assertEqual(self._run_with_config({
                "fault-type": "compute-pressure", "node-selector": "role=gpu",
                "gpu-ids": "0", "gpu-compute-duty-cycle": "20,30",
            }), 1)
        self.assertIn("one value per GPU ID", captured.output[0])
        deploy.assert_not_called()

    def test_pod_targeting_groups_and_rejects_bad_matching_pods(self):
        def pod(name, node, gpu=True, phase="Running"):
            resources = {"nvidia.com/mig-1g.5gb": "1"} if gpu else {}
            container = SimpleNamespace(resources=SimpleNamespace(limits=resources, requests={}))
            return SimpleNamespace(
                metadata=SimpleNamespace(namespace="target", name=name, uid=name + "-uid"),
                status=SimpleNamespace(phase=phase), spec=SimpleNamespace(node_name=node, containers=[container]),
            )

        lib = SimpleNamespace(cli=SimpleNamespace(list_namespaced_pod=MagicMock(return_value=SimpleNamespace(
            items=[pod("a", "node-1"), pod("a", "node-1"), pod("b", "node-1"), pod("c", "node-2")]
        ))))
        selected = self.plugin._select_pods(lib, "target", "app=gpu", {})
        self.assertEqual([target["name"] for target in selected["node-1"]], ["a", "b"])
        self.assertEqual(selected["node-2"][0]["uid"], "c-uid")
        lib.cli.list_namespaced_pod.return_value.items = [pod("bad", "node-1", gpu=False)]
        with self.assertRaisesRegex(ValueError, "no NVIDIA GPU"):
            self.plugin._select_pods(lib, "target", "app=gpu", {})
        lib.cli.list_namespaced_pod.return_value.items = [pod("bad", None)]
        with self.assertRaisesRegex(ValueError, "not Running"):
            self.plugin._select_pods(lib, "target", "app=gpu", {})

    def test_node_selection_uses_nvidia_capacity_and_hard_fails_shortage(self):
        def node(allocatable, capacity):
            return SimpleNamespace(status=SimpleNamespace(allocatable=allocatable, capacity=capacity))

        nodes = {"gpu": node({}, {"nvidia.com/gpu": "0", "nvidia.com/mig-1g.5gb": "2"}),
                 "cpu": node({"cpu": "4"}, {"cpu": "4"}),
                 "nic": node({"nvidia.com/hostdev": "2"}, {"nvidia.com/hostdev": "2"})}
        lib = SimpleNamespace(
            cli=SimpleNamespace(read_node=MagicMock(side_effect=lambda name: nodes[name])),
            list_nodes=MagicMock(return_value=["gpu", "cpu", "nic"]),
        )
        with patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.random.sample", return_value=["gpu"]):
            self.assertEqual(self.plugin._select_nodes(lib, "role=gpu", {"number-of-nodes": 1}), ["gpu"])
        self.assertEqual(self.plugin._select_nodes(lib, "role=gpu", {}), ["gpu"])
        with self.assertRaisesRegex(ValueError, "only 1 are available"):
            self.plugin._select_nodes(lib, "role=gpu", {"number-of-nodes": 2})
        with self.assertRaisesRegex(ValueError, "positive integer"):
            self.plugin._select_nodes(lib, "role=gpu", {"number-of-nodes": 0})

    def test_worker_manifest_target_mounts_and_runtime_options(self):
        manifest = self.plugin._worker_pod(
            "worker", "node-1", "default", "image", "vram-pressure", "all", 30,
            120, 30, {"runtime-class-name": "nvidia", "driver-root": "/run/nvidia/driver",
                      "service-account": "gpu-runner", "image-pull-secrets": "secret-a,secret-b"},
            [{"namespace": "target", "name": "application", "uid": "uid-1"}],
            {"GPU_VRAM": "20%", "GPU_MEMORY_RESERVE": "64Mi"},
        )
        spec = manifest["spec"]
        container = spec["containers"][0]
        env = {item["name"]: item["value"] for item in container["env"]}
        self.assertNotIn("command", container)
        self.assertTrue(container["securityContext"]["privileged"])
        self.assertEqual(spec["restartPolicy"], "Never")
        self.assertEqual(spec["terminationGracePeriodSeconds"], 10)
        self.assertFalse(spec["automountServiceAccountToken"])
        self.assertEqual(spec["runtimeClassName"], "nvidia")
        self.assertEqual(spec["serviceAccountName"], "gpu-runner")
        self.assertEqual(spec["imagePullSecrets"], [{"name": "secret-a"}, {"name": "secret-b"}])
        self.assertNotIn("gpu", container["resources"])
        self.assertEqual(json.loads(env["GPU_TARGET_PODS"])[0]["uid"], "uid-1")
        mounts = {mount["mountPath"]: mount for mount in container["volumeMounts"]}
        self.assertTrue(mounts["/var/lib/kubelet/pod-resources"]["readOnly"])
        self.assertTrue(mounts["/host-driver"]["readOnly"])
        self.assertIn("/host-driver/usr/lib64", env["LD_LIBRARY_PATH"])
        self.assertIn("/host-driver/usr/bin", env["PATH"])
        self.assertEqual(env["PATH"].split(":")[0], "/opt/venv/bin")
        self.assertEqual(spec["activeDeadlineSeconds"], 240)

    def test_run_registers_before_deploy_and_cleans_after_worker_failure(self):
        lib = SimpleNamespace(cli=MagicMock())
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = lib
        config = {"node-selector": "role=gpu", "number-of-nodes": 2,
                  "fault-type": "vram-pressure", "image": "image", "gpu-vram": "20%",
                  "duration": 10}
        with patch.dict(os.environ, {}, clear=True), tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as scenario:
            import yaml
            yaml.safe_dump(config, scenario)
            scenario.flush()
            with patch.object(self.plugin, "_select_nodes", return_value=["n1", "n2"]), \
                    patch.object(self.plugin, "_register_rollback", return_value=True) as register, \
                    patch.object(self.plugin, "_deploy_workers", side_effect=RuntimeError("worker failed")) as deploy, \
                    patch.object(self.plugin, "_delete_bounded") as delete:
                result = self.plugin.run("run-id", scenario.name, telemetry, MagicMock())
        self.assertEqual(result, 1)
        self.assertEqual(register.call_count, 2)
        self.assertEqual(deploy.call_count, 1)
        self.assertEqual(delete.call_count, 2)
        manifests = deploy.call_args.args[2]
        self.assertEqual([body["spec"]["nodeName"] for body in manifests], ["n1", "n2"])
        self.assertTrue(all(body["spec"]["runtimeClassName"] == "nvidia" for body in manifests))

    def test_run_cleans_worker_after_runtime_failure(self):
        import yaml
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = SimpleNamespace(cli=MagicMock())
        config = {
            "node-selector": "role=gpu", "fault-type": "vram-pressure",
            "image": "image", "gpu-vram": "20%", "duration": 10,
        }
        with patch.dict(os.environ, {}, clear=True), tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as scenario:
            yaml.safe_dump(config, scenario)
            scenario.flush()
            with patch.object(self.plugin, "_select_nodes", return_value=["n1"]), \
                    patch.object(self.plugin, "_register_rollback", return_value=True), \
                    patch.object(self.plugin, "_deploy_workers"), \
                    patch.object(self.plugin, "_coordinate", side_effect=RuntimeError("GPU worker failed")), \
                    patch.object(self.plugin, "_delete_bounded", return_value=True) as delete:
                self.assertEqual(self.plugin.run("run-id", scenario.name, telemetry, MagicMock()), 1)
        delete.assert_called_once()

    def test_pod_mode_requires_target_namespace(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertLogs(level="ERROR") as captured:
                result = self._run_with_config({"pod-label-selector": "app=gpu"})
        self.assertEqual(result, 1)
        self.assertIn("target-namespace is required", captured.output[0])

    def test_pod_mode_samples_nodes_and_cleanup_failure_returns_error(self):
        import yaml
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = SimpleNamespace(cli=MagicMock())
        config = {
            "pod-label-selector": "app=gpu", "target-namespace": "target",
            "number-of-nodes": 1, "fault-type": "vram-pressure", "image": "image",
            "gpu-vram": "0.5%", "duration": 10,
        }
        groups = {
            "n1": [{"namespace": "target", "name": "app-1", "uid": "uid-1"}],
            "n2": [{"namespace": "target", "name": "app-2", "uid": "uid-2"}],
        }
        with patch.dict(os.environ, {}, clear=True), tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as scenario:
            yaml.safe_dump(config, scenario)
            scenario.flush()
            with patch.object(self.plugin, "_select_pods", return_value=groups) as select, \
                    patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.random.sample", return_value=["n2"]), \
                    patch.object(self.plugin, "_register_rollback", return_value=True), \
                    patch.object(self.plugin, "_deploy_workers") as deploy, \
                    patch.object(self.plugin, "_coordinate") as coordinate, \
                    patch.object(self.plugin, "_delete_bounded", return_value=False):
                result = self.plugin.run("run-id", scenario.name, telemetry, MagicMock())
        self.assertEqual(result, 1)
        select.assert_called_once_with(telemetry.get_lib_kubernetes.return_value, "target", "app=gpu", config)
        self.assertEqual(coordinate.call_args.args[2], ["n2"])
        env = {item["name"]: item["value"] for item in deploy.call_args.args[2][0]["spec"]["containers"][0]["env"]}
        self.assertEqual(json.loads(env["GPU_TARGET_PODS"])[0]["name"], "app-2")

    def test_ready_barrier_revalidates_targets_before_release_and_completes(self):
        targets_by_name = {
            "app-1": SimpleNamespace(metadata=SimpleNamespace(uid="original-1"), spec=SimpleNamespace(node_name="n1"),
                                     status=SimpleNamespace(phase="Running")),
            "app-2": SimpleNamespace(metadata=SimpleNamespace(uid="original-2"), spec=SimpleNamespace(node_name="n2"),
                                     status=SimpleNamespace(phase="Running")),
        }
        cli = MagicMock()
        cli.read_namespaced_pod.side_effect = lambda name, namespace, **_kwargs: targets_by_name[name]
        phases = iter([
            ("n1", "ready"), ("n2", "ready"),
            ("n1", "holding"), ("n2", "holding"),
            ("n1", "complete"), ("n2", "complete"),
        ])
        ready_count = 0

        def event(_cli, name, _namespace):
            nonlocal ready_count
            node, phase = next(phases)
            self.assertEqual(name, f"worker-{node}")
            if phase == "ready":
                ready_count += 1
            return {"phase": phase, "gpus": [{"uuid": f"gpu-{node}", "requested": 1024}]}

        def release(_api_method, name, namespace, **kwargs):
            self.assertIn(name, ("worker-n1", "worker-n2"))
            self.assertEqual(namespace, "default")
            self.assertEqual(kwargs["command"], ["touch", "/tmp/krkn-gpu-start"])
            self.assertEqual(kwargs["_request_timeout"], 10)
            self.assertEqual(ready_count, 2)
            self.assertEqual(cli.read_namespaced_pod.call_count, 2)
            return ""

        lib = SimpleNamespace(cli=cli)
        with patch.object(self.plugin, "_last_event", side_effect=event), \
                patch.object(self.plugin, "_check_pod"), \
                patch.object(self.plugin, "_wait_success"), \
                patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.k8s_stream", side_effect=release) as stream, \
                patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.sleep"):
            self.plugin._coordinate(
                lib, [("worker-n1", "default"), ("worker-n2", "default")],
                ["n1", "n2"], {
                    "n1": [{"namespace": "target", "name": "app-1", "uid": "original-1"}],
                    "n2": [{"namespace": "target", "name": "app-2", "uid": "original-2"}],
                }, 5, 10, 5,
            )
        self.assertEqual(cli.read_namespaced_pod.call_count, 2)
        self.assertEqual(stream.call_count, 2)

    def test_setup_timeout_prevents_barrier_release(self):
        lib = SimpleNamespace(cli=MagicMock())
        with patch.object(self.plugin, "_last_event", return_value=None), \
                patch.object(self.plugin, "_check_pod"), \
                patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.monotonic", side_effect=[0, 6]), \
                patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.sleep"), \
                patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.k8s_stream") as stream:
            with self.assertRaisesRegex(TimeoutError, "ready barrier"):
                self.plugin._coordinate(lib, [("worker", "default")], ["n1"], {"n1": []}, 5, 10, 5)
        stream.assert_not_called()

    def test_replacement_or_worker_error_fails_before_release(self):
        lib = SimpleNamespace(cli=MagicMock())
        target = SimpleNamespace(metadata=SimpleNamespace(uid="replacement"), spec=SimpleNamespace(node_name="n1"))
        lib.cli.read_namespaced_pod.return_value = target
        with patch.object(self.plugin, "_last_event", return_value={"phase": "ready"}), \
                patch.object(self.plugin, "_check_pod"), patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "changed or is no longer Running"):
                self.plugin._coordinate(lib, [("worker", "default")], ["n1"],
                                        {"n1": [{"namespace": "target", "name": "app", "uid": "old"}]}, 5, 10, 5)
        with patch.object(self.plugin, "_last_event", return_value={"phase": "error", "message": "allocation failed"}), \
                patch.object(self.plugin, "_check_pod"):
            with self.assertRaisesRegex(RuntimeError, "allocation failed"):
                self.plugin._coordinate(lib, [("worker", "default")], ["n1"], {"n1": []}, 5, 10, 5)

    def test_log_polling_and_pod_exit_checks(self):
        cli = MagicMock()
        cli.read_namespaced_pod_log.return_value = HTTPResponse(
            body=BytesIO(json.dumps({"phase": "ready", "gpus": []}).encode()), preload_content=False,
        )
        self.assertEqual(self.plugin._last_event(cli, "worker", "default")["phase"], "ready")
        cli.read_namespaced_pod_log.assert_called_once_with(
            "worker", "default", tail_lines=1, _request_timeout=10, _preload_content=False,
        )
        cli.read_namespaced_pod_log.return_value = HTTPResponse(body=BytesIO(b"not-json"), preload_content=False)
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            self.plugin._last_event(cli, "worker", "default")

        failed = SimpleNamespace(
            status=SimpleNamespace(
                phase="Running",
                container_statuses=[SimpleNamespace(state=SimpleNamespace(
                    terminated=SimpleNamespace(exit_code=7)
                ))],
            )
        )
        cli.read_namespaced_pod.return_value = failed
        with self.assertRaisesRegex(RuntimeError, "exited 7"):
            self.plugin._check_pod(cli, "worker", "default")
        cli.read_namespaced_pod.return_value = SimpleNamespace(
            status=SimpleNamespace(phase="Succeeded", container_statuses=[])
        )
        with self.assertRaisesRegex(RuntimeError, "exited before completion"):
            self.plugin._check_pod(cli, "worker", "default", require_running=True)

    def test_single_json_event_survives_kubernetes_sdk_log_handling(self):
        with ApiClient() as api:
            cli = CoreV1Api(api)
            for phase in ("ready", "holding", "complete", "error"):
                event = {
                    "phase": phase, "message": "GPU's memory",
                    "gpus": [{"actual_bytes": 268435456}],
                    "free_delta_within_tolerance": True, "error": None,
                }
                response = HTTPResponse(
                    body=BytesIO(json.dumps(event).encode()), status=200,
                    headers={"Content-Type": "text/plain"}, preload_content=False,
                )
                with self.subTest(phase=phase), patch.object(api.rest_client, "GET", return_value=response):
                    self.assertEqual(self.plugin._last_event(cli, "worker", "default"), event)
                self.assertTrue(response.closed)

    def test_raw_log_reader_preserves_last_line_and_empty_logs(self):
        event = {"phase": "holding", "gpus": []}
        for payload, expected in (
            (json.dumps({"phase": "ready"}) + "\n" + json.dumps(event) + "\n", event),
            ("", None),
        ):
            with self.subTest(payload=payload), ApiClient() as api:
                response = HTTPResponse(
                    body=BytesIO(payload.encode()), status=200, preload_content=False,
                )
                with patch.object(api.rest_client, "GET", return_value=response):
                    self.assertEqual(self.plugin._last_event(CoreV1Api(api), "worker", "default"), expected)

    def test_success_wait_and_idempotent_cleanup(self):
        cli = MagicMock()
        cli.read_namespaced_pod.return_value = SimpleNamespace(status=SimpleNamespace(
            phase="Succeeded",
            container_statuses=[SimpleNamespace(state=SimpleNamespace(
                terminated=SimpleNamespace(exit_code=0)
            ))],
        ))
        self.plugin._wait_success(cli, "worker", "default", timeout=1)
        cli.read_namespaced_pod.return_value = SimpleNamespace(status=SimpleNamespace(
            phase="Succeeded",
            container_statuses=[SimpleNamespace(state=SimpleNamespace(
                terminated=SimpleNamespace(exit_code=2)
            ))],
        ))
        with self.assertRaisesRegex(RuntimeError, "did not exit successfully"):
            self.plugin._wait_success(cli, "worker", "default", timeout=1)

        cli.delete_namespaced_pod.side_effect = ApiException(status=404)
        self.assertTrue(self.plugin._delete_bounded(cli, "missing", "default"))
        cli.delete_namespaced_pod.assert_called_once_with(
            "missing", "default", grace_period_seconds=10, _request_timeout=10
        )
        cli.delete_namespaced_pod.side_effect = None
        cli.read_namespaced_pod.side_effect = ApiException(status=404)
        self.assertTrue(self.plugin._delete_bounded(cli, "worker", "default"))

    def test_serialized_rollback_and_parallel_deploy_errors(self):
        cli = MagicMock()
        cli.delete_namespaced_pod.side_effect = ApiException(status=404)
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = SimpleNamespace(cli=cli)
        self.plugin.rollback_gpu_pod(
            RollbackContent(namespace="default", resource_identifier="worker"), telemetry
        )
        cli.delete_namespaced_pod.assert_called_once_with(
            "worker", "default", grace_period_seconds=10, _request_timeout=10
        )

        cli.delete_namespaced_pod.side_effect = None
        cli.read_namespaced_pod.side_effect = ApiException(status=404)
        self.plugin.rollback_gpu_pod(
            RollbackContent(namespace="default", resource_identifier="worker"), telemetry
        )
        cli.delete_namespaced_pod.side_effect = ApiException(status=500)
        with self.assertRaises(ApiException):
            self.plugin.rollback_gpu_pod(
                RollbackContent(namespace="default", resource_identifier="worker"), telemetry
            )
        lib = SimpleNamespace(
            cli=MagicMock(), create_obj=MagicMock(side_effect=RuntimeError("create failed"))
        )
        with self.assertRaisesRegex(RuntimeError, "create failed"):
            self.plugin._deploy_workers(
                lib, [("one", "default"), ("two", "default")],
                [{"metadata": {"name": "one"}}, {"metadata": {"name": "two"}}], 5,
            )

    def test_runtime_class_override_does_not_require_discovery(self):
        lib = SimpleNamespace(cli=MagicMock())
        result = self.plugin._resolve_runtime_class(lib, {"runtime-class-name": "custom-gpu"})
        self.assertEqual(result, "custom-gpu")
        self.runtime_api.read_runtime_class.assert_not_called()

    def test_absent_nvidia_runtime_uses_default(self):
        self.runtime_api.read_runtime_class.side_effect = ApiException(status=404)
        config = {"runtime-class-name": self.plugin._resolve_runtime_class(SimpleNamespace(cli=MagicMock()), {})}
        manifest = self.plugin._worker_pod(
            "worker", "node", "default", "image", "vram-pressure", "all",
            1, 5, 5, config, [], {"GPU_VRAM": "1Mi", "GPU_MEMORY_RESERVE": "64Mi"},
        )
        self.assertNotIn("runtimeClassName", manifest["spec"])

    def test_runtime_discovery_errors_are_not_silently_ignored(self):
        for status in (403, 500):
            with self.subTest(status=status):
                self.runtime_api.read_runtime_class.side_effect = ApiException(status=status)
                with self.assertRaisesRegex(RuntimeError, "node.k8s.io/runtimeclasses"):
                    self.plugin._resolve_runtime_class(SimpleNamespace(cli=MagicMock()), {})

    def test_fast_exit_logs_are_captured_before_cleanup(self):
        import yaml
        for phase in ("Failed", "Running"):
            with self.subTest(phase=phase), tempfile.NamedTemporaryFile(mode="w") as scenario:
                yaml.safe_dump({
                    "node-selector": "role=gpu", "image": "image", "fault-type": "vram-pressure",
                    "duration": 20, "gpu-vram": "256Mi",
                }, scenario)
                scenario.flush()
                order = []
                worker_error = '{"phase":"error","message":"cannot load CUDA driver library"}'
                cli = MagicMock()
                cli.read_namespaced_pod.return_value = SimpleNamespace(status=SimpleNamespace(
                    phase=phase, container_statuses=[SimpleNamespace(
                        state=SimpleNamespace(terminated=SimpleNamespace(exit_code=1))
                    )],
                ))
                cli.read_namespaced_pod_log.side_effect = lambda *_args, **_kwargs: (
                    order.append("logs") or HTTPResponse(body=BytesIO(worker_error.encode()), preload_content=False)
                )
                lib = SimpleNamespace(cli=cli, create_obj=MagicMock())
                lib.create_obj.side_effect = lambda body, namespace, create: create(body=body, namespace=namespace)
                telemetry = MagicMock()
                telemetry.get_lib_kubernetes.return_value = lib
                with patch.dict(os.environ, {}, clear=True), \
                        patch.object(self.plugin, "_select_nodes", return_value=["node"]), \
                        patch.object(self.plugin, "_register_rollback", return_value=True), \
                        patch.object(self.plugin, "_delete_bounded", side_effect=lambda *_args: order.append("cleanup") or True), \
                        patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.sleep") as sleep, \
                        self.assertLogs(level="ERROR") as captured:
                    result = self.plugin.run("run-id", scenario.name, telemetry, MagicMock())
                self.assertEqual(result, 1)
                self.assertEqual(order, ["logs", "cleanup"])
                self.assertIn(worker_error, "\n".join(captured.output))
                sleep.assert_not_called()

    def test_startup_can_wait_for_running_without_reading_logs(self):
        cli = MagicMock()
        cli.read_namespaced_pod.side_effect = [
            SimpleNamespace(status=SimpleNamespace(phase=phase, container_statuses=[]))
            for phase in ("Pending", "Running")
        ]
        lib = SimpleNamespace(cli=cli, create_obj=MagicMock())
        lib.create_obj.side_effect = lambda body, namespace, create: create(body=body, namespace=namespace)
        with patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.monotonic", return_value=0), \
                patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.sleep"):
            self.plugin._start_worker(lib, {"metadata": {"name": "worker"}}, "default", 5, threading.Event())
        self.assertEqual(cli.read_namespaced_pod.call_count, 2)
        cli.read_namespaced_pod_log.assert_not_called()

    def test_startup_timeout_preserves_waiting_reason_when_logs_unavailable(self):
        cli = MagicMock()
        cli.read_namespaced_pod.return_value = SimpleNamespace(status=SimpleNamespace(
            phase="Pending", container_statuses=[SimpleNamespace(state=SimpleNamespace(
                terminated=None, waiting=SimpleNamespace(reason="ImagePullBackOff")
            ))],
        ))
        cli.read_namespaced_pod_log.side_effect = ApiException(status=400)
        lib = SimpleNamespace(cli=cli, create_obj=MagicMock())
        with patch("krkn.scenario_plugins.gpu.gpu_scenario_plugin.time.monotonic", side_effect=[0, 6]):
            with self.assertRaises(RuntimeError) as caught:
                self.plugin._start_worker(lib, {"metadata": {"name": "worker"}}, "default", 5, threading.Event())
        self.assertIn("ImagePullBackOff", str(caught.exception))
        self.assertIn("400", str(caught.exception))

    def _run_with_config(self, config):
        import yaml
        telemetry = MagicMock()
        telemetry.get_lib_kubernetes.return_value = SimpleNamespace(cli=MagicMock())
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as scenario:
            yaml.safe_dump({"image": "image", "fault-type": "vram-pressure",
                            "gpu-vram": "20%", "duration": 10, **config}, scenario)
            scenario.flush()
            return self.plugin.run("run-id", scenario.name, telemetry, MagicMock())


if __name__ == "__main__":
    unittest.main()
