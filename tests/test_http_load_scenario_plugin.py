import tempfile
import unittest
from unittest.mock import Mock, patch
import yaml

from krkn.scenario_plugins.http_load.http_load_scenario_plugin import HttpLoadScenarioPlugin


class TestHttpLoadScenarioPlugin(unittest.TestCase):

    def setUp(self):
        self.plugin = HttpLoadScenarioPlugin("http_load_scenarios")
        self.mock_telemetry = Mock()
        self.mock_kubernetes = Mock()
        self.mock_telemetry.get_lib_kubernetes.return_value = self.mock_kubernetes
        self.mock_scenario_telemetry = Mock()

    def test_get_scenario_types(self):
        result = self.plugin.get_scenario_types()
        self.assertEqual(result, ["http_load_scenarios"])

    def test_build_load_command_basic(self):
        cmd = self.plugin.build_load_command(
            target_url="http://example.com",
            duration=30,
            concurrency=10,
            requests_per_second=0,
            http_method="GET",
        )
        self.assertEqual(cmd, "hey -c 10 -z 30s -m GET 'http://example.com'")

    def test_build_load_command_with_rps(self):
        cmd = self.plugin.build_load_command(
            target_url="http://example.com",
            duration=60,
            concurrency=20,
            requests_per_second=100,
            http_method="POST",
        )
        self.assertEqual(cmd, "hey -c 20 -z 60s -m POST -q 100 'http://example.com'")

    def test_build_load_command_with_body_and_headers(self):
        cmd = self.plugin.build_load_command(
            target_url="http://example.com/api",
            duration=30,
            concurrency=10,
            requests_per_second=0,
            http_method="POST",
            request_body='{"key": "value"}',
            headers={"Authorization": "Bearer token123", "X-Custom": "header"},
            content_type="application/json",
        )
        self.assertIn("-c 10", cmd)
        self.assertIn("-z 30s", cmd)
        self.assertIn("-m POST", cmd)
        self.assertIn("-T 'application/json'", cmd)
        self.assertIn("-H 'Authorization: Bearer token123'", cmd)
        self.assertIn("-H 'X-Custom: header'", cmd)
        self.assertIn("-d '{\"key\": \"value\"}'", cmd)
        self.assertIn("'http://example.com/api'", cmd)

    def test_build_load_command_with_content_type_only(self):
        cmd = self.plugin.build_load_command(
            target_url="http://example.com",
            duration=10,
            concurrency=5,
            requests_per_second=0,
            http_method="POST",
            content_type="text/plain",
        )
        self.assertIn("-T 'text/plain'", cmd)

    def test_resolve_target_url_direct(self):
        result = self.plugin.resolve_target_url(
            kubecli=self.mock_kubernetes,
            target_url="http://direct.example.com",
            target_service="",
            target_ingress="",
            target_route="",
            target_port=80,
            target_path="",
            namespace="default",
        )
        self.assertEqual(result, "http://direct.example.com")

    def test_resolve_target_url_service(self):
        self.mock_kubernetes.service_exists.return_value = True

        result = self.plugin.resolve_target_url(
            kubecli=self.mock_kubernetes,
            target_url="",
            target_service="my-service",
            target_ingress="",
            target_route="",
            target_port=8080,
            target_path="api/v1",
            namespace="test-ns",
        )

        self.mock_kubernetes.service_exists.assert_called_once_with("my-service", "test-ns")
        self.assertEqual(result, "http://my-service.test-ns.svc.cluster.local:8080/api/v1")

    def test_resolve_target_url_service_not_found(self):
        self.mock_kubernetes.service_exists.return_value = False

        result = self.plugin.resolve_target_url(
            kubecli=self.mock_kubernetes,
            target_url="",
            target_service="nonexistent",
            target_ingress="",
            target_route="",
            target_port=80,
            target_path="",
            namespace="default",
        )

        self.assertIsNone(result)

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.client.NetworkingV1Api")
    def test_resolve_ingress_url(self, mock_networking_api):
        mock_api = Mock()
        mock_networking_api.return_value = mock_api

        mock_ingress = Mock()
        mock_ingress.spec.rules = [Mock(host="ingress.example.com", http=Mock(paths=[Mock(path="/api")]))]
        mock_ingress.spec.tls = None
        mock_api.read_namespaced_ingress.return_value = mock_ingress

        result = self.plugin.resolve_ingress_url(
            kubecli=self.mock_kubernetes,
            ingress_name="my-ingress",
            namespace="default",
            target_path="",
        )

        self.assertEqual(result, "http://ingress.example.com/api")

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.client.NetworkingV1Api")
    def test_resolve_ingress_url_with_tls(self, mock_networking_api):
        mock_api = Mock()
        mock_networking_api.return_value = mock_api

        mock_ingress = Mock()
        mock_ingress.spec.rules = [Mock(host="secure.example.com", http=None)]
        mock_ingress.spec.tls = [Mock(hosts=["secure.example.com"])]
        mock_api.read_namespaced_ingress.return_value = mock_ingress

        result = self.plugin.resolve_ingress_url(
            kubecli=self.mock_kubernetes,
            ingress_name="secure-ingress",
            namespace="default",
            target_path="/health",
        )

        self.assertEqual(result, "https://secure.example.com/health")

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.client.CustomObjectsApi")
    def test_resolve_route_url(self, mock_custom_api):
        mock_api = Mock()
        mock_custom_api.return_value = mock_api

        mock_api.get_namespaced_custom_object.return_value = {
            "spec": {
                "host": "route.apps.example.com",
                "tls": {"termination": "edge"},
                "path": "/app",
            }
        }

        result = self.plugin.resolve_route_url(
            kubecli=self.mock_kubernetes,
            route_name="my-route",
            namespace="openshift-project",
            target_path="",
        )

        self.assertEqual(result, "https://route.apps.example.com/app")

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.client.CustomObjectsApi")
    def test_resolve_route_url_no_tls(self, mock_custom_api):
        mock_api = Mock()
        mock_custom_api.return_value = mock_api

        mock_api.get_namespaced_custom_object.return_value = {
            "spec": {
                "host": "route.apps.example.com",
            }
        }

        result = self.plugin.resolve_route_url(
            kubecli=self.mock_kubernetes,
            route_name="my-route",
            namespace="openshift-project",
            target_path="/api",
        )

        self.assertEqual(result, "http://route.apps.example.com/api")

    def test_run_missing_target(self):
        config = {"http_load": {"namespace": "default"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_file = f.name

        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario=temp_file,
            krkn_config={"cerberus": {"cerberus_enabled": False}},
            lib_telemetry=self.mock_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry,
        )
        self.assertEqual(result, 1)

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.cerberus")
    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.Environment")
    def test_run_success_with_service(self, mock_env_class, mock_cerberus):
        config = {
            "http_load": {
                "target_service": "my-service",
                "target_port": 80,
                "namespace": "default",
                "duration": 10,
                "concurrency": 5,
                "number_of_pods": 1,
                "image": "test-image",
            }
        }

        mock_template = Mock()
        mock_template.render.return_value = """
apiVersion: batch/v1
kind: Job
metadata:
  name: http-load-test
  namespace: default
spec:
  template:
    spec:
      containers:
      - name: http-load
        image: test-image
        command: ["/bin/sh", "-c", "hey -c 5 -z 10s -m GET 'http://my-service.default.svc.cluster.local:80'"]
      restartPolicy: Never
  backoffLimit: 0
"""
        mock_env = Mock()
        mock_env.get_template.return_value = mock_template
        mock_env_class.return_value = mock_env

        self.mock_kubernetes.service_exists.return_value = True
        self.mock_kubernetes.create_job.return_value = Mock()

        mock_job_status = Mock()
        mock_job_status.status.succeeded = 1
        mock_job_status.status.failed = None
        mock_job_status.metadata.labels = {"controller-uid": "test-uid"}
        self.mock_kubernetes.get_job_status.return_value = mock_job_status
        self.mock_kubernetes.list_pods.return_value = ["test-pod"]

        mock_log_response = Mock()
        mock_log_response.data = b"Summary:\n  Requests/sec: 100\n"
        self.mock_kubernetes.get_pod_log.return_value = mock_log_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_file = f.name

        result = self.plugin.run(
            run_uuid="test-uuid-1234",
            scenario=temp_file,
            krkn_config={"cerberus": {"cerberus_enabled": False}},
            lib_telemetry=self.mock_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry,
        )

        self.assertEqual(result, 0)
        self.mock_kubernetes.service_exists.assert_called_once_with("my-service", "default")
        self.mock_kubernetes.create_job.assert_called_once()
        self.mock_kubernetes.delete_job.assert_called()
        mock_cerberus.publish_kraken_status.assert_called_once()

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.cerberus")
    def test_run_service_not_found(self, mock_cerberus):
        config = {
            "http_load": {
                "target_service": "nonexistent-service",
                "namespace": "default",
            }
        }

        self.mock_kubernetes.service_exists.return_value = False

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_file = f.name

        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario=temp_file,
            krkn_config={"cerberus": {"cerberus_enabled": False}},
            lib_telemetry=self.mock_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry,
        )

        self.assertEqual(result, 1)
        self.mock_kubernetes.service_exists.assert_called_once_with("nonexistent-service", "default")

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.cerberus")
    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.Environment")
    def test_run_create_job_failure(self, mock_env_class, mock_cerberus):
        config = {
            "http_load": {
                "target_url": "http://example.com",
                "namespace": "default",
                "duration": 10,
                "concurrency": 5,
                "number_of_pods": 1,
            }
        }

        mock_template = Mock()
        mock_template.render.return_value = """
apiVersion: batch/v1
kind: Job
metadata:
  name: http-load-test
  namespace: default
spec:
  template:
    spec:
      containers:
      - name: http-load
        image: williamyeh/hey:latest
        command: ["/bin/sh", "-c", "hey"]
      restartPolicy: Never
  backoffLimit: 0
"""
        mock_env = Mock()
        mock_env.get_template.return_value = mock_template
        mock_env_class.return_value = mock_env

        self.mock_kubernetes.create_job.return_value = None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_file = f.name

        result = self.plugin.run(
            run_uuid="test-uuid",
            scenario=temp_file,
            krkn_config={"cerberus": {"cerberus_enabled": False}},
            lib_telemetry=self.mock_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry,
        )
        self.assertEqual(result, 1)

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.cerberus")
    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.client.NetworkingV1Api")
    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.Environment")
    def test_run_with_ingress_target(self, mock_env_class, mock_networking_api, mock_cerberus):
        config = {
            "http_load": {
                "target_ingress": "my-ingress",
                "namespace": "default",
                "duration": 10,
                "concurrency": 5,
                "number_of_pods": 1,
            }
        }

        mock_api = Mock()
        mock_networking_api.return_value = mock_api
        mock_ingress = Mock()
        mock_ingress.spec.rules = [Mock(host="ingress.example.com", http=Mock(paths=[Mock(path="/api")]))]
        mock_ingress.spec.tls = None
        mock_api.read_namespaced_ingress.return_value = mock_ingress

        mock_template = Mock()
        mock_template.render.return_value = """
apiVersion: batch/v1
kind: Job
metadata:
  name: http-load-test
  namespace: default
spec:
  template:
    spec:
      containers:
      - name: http-load
        image: williamyeh/hey:latest
        command: ["/bin/sh", "-c", "hey"]
      restartPolicy: Never
  backoffLimit: 0
"""
        mock_env = Mock()
        mock_env.get_template.return_value = mock_template
        mock_env_class.return_value = mock_env

        self.mock_kubernetes.create_job.return_value = Mock()
        mock_job_status = Mock()
        mock_job_status.status.succeeded = 1
        mock_job_status.status.failed = None
        mock_job_status.metadata.labels = {"controller-uid": "test-uid"}
        self.mock_kubernetes.get_job_status.return_value = mock_job_status
        self.mock_kubernetes.list_pods.return_value = ["test-pod"]
        mock_log_response = Mock()
        mock_log_response.data = b"Summary: OK"
        self.mock_kubernetes.get_pod_log.return_value = mock_log_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_file = f.name

        result = self.plugin.run(
            run_uuid="test-uuid-1234",
            scenario=temp_file,
            krkn_config={"cerberus": {"cerberus_enabled": False}},
            lib_telemetry=self.mock_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry,
        )

        self.assertEqual(result, 0)
        mock_api.read_namespaced_ingress.assert_called_once()

    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.cerberus")
    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.client.CustomObjectsApi")
    @patch("krkn.scenario_plugins.http_load.http_load_scenario_plugin.Environment")
    def test_run_with_route_target(self, mock_env_class, mock_custom_api, mock_cerberus):
        config = {
            "http_load": {
                "target_route": "my-route",
                "namespace": "openshift-project",
                "duration": 10,
                "concurrency": 5,
                "number_of_pods": 1,
            }
        }

        mock_api = Mock()
        mock_custom_api.return_value = mock_api
        mock_api.get_namespaced_custom_object.return_value = {
            "spec": {
                "host": "route.apps.example.com",
                "tls": {"termination": "edge"},
            }
        }

        mock_template = Mock()
        mock_template.render.return_value = """
apiVersion: batch/v1
kind: Job
metadata:
  name: http-load-test
  namespace: openshift-project
spec:
  template:
    spec:
      containers:
      - name: http-load
        image: williamyeh/hey:latest
        command: ["/bin/sh", "-c", "hey"]
      restartPolicy: Never
  backoffLimit: 0
"""
        mock_env = Mock()
        mock_env.get_template.return_value = mock_template
        mock_env_class.return_value = mock_env

        self.mock_kubernetes.create_job.return_value = Mock()
        mock_job_status = Mock()
        mock_job_status.status.succeeded = 1
        mock_job_status.status.failed = None
        mock_job_status.metadata.labels = {"controller-uid": "test-uid"}
        self.mock_kubernetes.get_job_status.return_value = mock_job_status
        self.mock_kubernetes.list_pods.return_value = ["test-pod"]
        mock_log_response = Mock()
        mock_log_response.data = b"Summary: OK"
        self.mock_kubernetes.get_pod_log.return_value = mock_log_response

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_file = f.name

        result = self.plugin.run(
            run_uuid="test-uuid-1234",
            scenario=temp_file,
            krkn_config={"cerberus": {"cerberus_enabled": False}},
            lib_telemetry=self.mock_telemetry,
            scenario_telemetry=self.mock_scenario_telemetry,
        )

        self.assertEqual(result, 0)
        mock_api.get_namespaced_custom_object.assert_called_once_with(
            group="route.openshift.io",
            version="v1",
            namespace="openshift-project",
            plural="routes",
            name="my-route",
        )


if __name__ == "__main__":
    unittest.main()
