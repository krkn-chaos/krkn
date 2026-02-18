import base64
import json
import logging
import time
from typing import Dict, List, Any

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_random_string

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class HttpLoadScenarioPlugin(AbstractScenarioPlugin):
    """
    HTTP Load Testing Scenario Plugin using Vegeta.
    
    Deploys Vegeta load testing pods inside the Kubernetes cluster for distributed
    HTTP load testing. Supports multiple concurrent pods, node affinity, authentication,
    and comprehensive results collection.
    """

    def __init__(self, scenario_type: str = "http_load_scenarios"):
        super().__init__(scenario_type=scenario_type)

    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """
        Main entry point for HTTP load scenario execution.
        
        Deploys Vegeta load testing pods inside the cluster for distributed load testing.
        
        :param run_uuid: Unique identifier for this chaos run
        :param scenario: Path to scenario configuration file
        :param krkn_config: Full krkn configuration dictionary
        :param lib_telemetry: Telemetry object for Kubernetes operations
        :param scenario_telemetry: Telemetry object for this scenario
        :return: 0 on success, 1 on failure
        """
        try:
            # Load scenario configuration
            with open(scenario, "r") as f:
                scenario_configs = yaml.full_load(f)

            if not scenario_configs:
                logging.error("Empty scenario configuration file")
                return 1

            # Process each scenario configuration
            for scenario_config in scenario_configs:
                if not isinstance(scenario_config, dict):
                    logging.error(f"Invalid scenario configuration format: {scenario_config}")
                    return 1

                # Get the http_load_scenario configuration
                config = scenario_config.get("http_load_scenario", scenario_config)
                
                # Validate configuration
                if not self._validate_config(config):
                    return 1

                # Execute the load test (deploy pods)
                result = self._execute_distributed_load_test(
                    config,
                    lib_telemetry,
                    scenario_telemetry
                )
                
                if result != 0:
                    return result

            logging.info("HTTP load test completed successfully")
            return 0

        except Exception as e:
            logging.error(f"HTTP load scenario failed with exception: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return 1

    def get_scenario_types(self) -> list[str]:
        """Return the scenario types this plugin handles."""
        return ["http_load_scenarios"]

    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate scenario configuration.
        
        :param config: Scenario configuration dictionary
        :return: True if valid, False otherwise
        """
        # Check for required fields
        if "targets" not in config:
            logging.error("Missing required field: targets")
            return False

        targets = config["targets"]
        
        # Validate targets configuration
        if "endpoints" not in targets:
            logging.error("targets must contain 'endpoints'")
            return False

        if "endpoints" in targets:
            endpoints = targets["endpoints"]
            if not isinstance(endpoints, list) or len(endpoints) == 0:
                logging.error("endpoints must be a non-empty list")
                return False

            # Validate each endpoint
            for idx, endpoint in enumerate(endpoints):
                if not isinstance(endpoint, dict):
                    logging.error(f"Endpoint {idx} must be a dictionary")
                    return False
                if "url" not in endpoint:
                    logging.error(f"Endpoint {idx} missing required field: url")
                    return False
                if "method" not in endpoint:
                    logging.error(f"Endpoint {idx} missing required field: method")
                    return False

        # Validate rate format
        if "rate" in config:
            rate = config["rate"]
            if not isinstance(rate, (str, int)):
                logging.error("rate must be a string (e.g., '200/1s') or integer")
                return False

        # Validate duration format
        if "duration" in config:
            duration = config["duration"]
            if not isinstance(duration, (str, int)):
                logging.error("duration must be a string (e.g., '30s') or integer")
                return False

        return True

    def _execute_distributed_load_test(
        self,
        config: Dict[str, Any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry
    ) -> int:
        """
        Execute distributed HTTP load test by deploying Vegeta pods.
        
        :param config: Scenario configuration
        :param lib_telemetry: Telemetry object for Kubernetes operations
        :param scenario_telemetry: Telemetry object for recording results
        :return: 0 on success, 1 on failure
        """
        pod_names = []
        namespace = config.get("namespace", "default")
        
        try:
            # Get number of pods to deploy
            number_of_pods = config.get("number-of-pods", 1)
            
            # Get container image
            image = config.get("image", "quay.io/krkn-chaos/krkn-http-load:latest")
            
            # Get endpoints
            endpoints = config.get("targets", {}).get("endpoints", [])
            if not endpoints:
                logging.error("No endpoints specified in targets")
                return 1
            
            # Build Vegeta JSON targets for all endpoints (round-robin)
            targets_json = self._build_vegeta_json_targets(endpoints)
            targets_json_base64 = base64.b64encode(targets_json.encode()).decode()
            
            target_urls = [ep["url"] for ep in endpoints]
            logging.info(f"Targeting {len(endpoints)} endpoint(s): {target_urls}")
            
            # Get node selectors for pod placement
            node_selectors = config.get("attacker-nodes")
            
            # Deploy multiple Vegeta pods
            logging.info(f"Deploying {number_of_pods} HTTP load testing pod(s)")
            
            for i in range(number_of_pods):
                pod_name = f"http-load-{get_random_string(10)}"
                
                logging.info(f"Deploying pod {i+1}/{number_of_pods}: {pod_name}")
                
                # Deploy pod using krkn-lib
                lib_telemetry.get_lib_kubernetes().deploy_http_load(
                    name=pod_name,
                    namespace=namespace,
                    image=image,
                    targets_json_base64=targets_json_base64,
                    duration=config.get("duration", "30s"),
                    rate=config.get("rate", "50/1s"),
                    workers=config.get("workers", 10),
                    max_workers=config.get("max_workers", 100),
                    connections=config.get("connections", 100),
                    timeout=config.get("timeout", "10s"),
                    keepalive=config.get("keepalive", True),
                    http2=config.get("http2", True),
                    insecure=config.get("insecure", False),
                    node_selectors=node_selectors,
                    timeout_sec=500
                )
                
                pod_names.append(pod_name)
                
                # Set rollback callable for pod cleanup
                rollback_data = base64.b64encode(json.dumps(pod_names).encode('utf-8')).decode('utf-8')
                self.rollback_handler.set_rollback_callable(
                    self.rollback_http_load_pods,
                    RollbackContent(
                        namespace=namespace,
                        resource_identifier=rollback_data,
                    ),
                )
            
            logging.info(f"Successfully deployed {len(pod_names)} HTTP load pod(s)")
            
            # Wait for all pods to complete
            logging.info("Waiting for all HTTP load pods to complete...")
            self._wait_for_pods_completion(pod_names, namespace, lib_telemetry, config)
            
            # Collect and aggregate results from all pods
            metrics = self._collect_and_aggregate_results(pod_names, namespace, lib_telemetry)
            
            if metrics:
                # Log metrics summary
                self._log_metrics_summary(metrics)
                
                # Store metrics in telemetry
                scenario_telemetry.additional_telemetry = metrics
            
            logging.info("HTTP load test completed successfully")
            return 0

        except Exception as e:
            logging.error(f"Error executing distributed load test: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return 1

    def _build_vegeta_json_targets(self, endpoints: List[Dict[str, Any]]) -> str:
        """
        Build newline-delimited Vegeta JSON targets from all endpoints.
        
        Vegeta round-robins across targets when multiple are provided.
        Each line is a JSON object: {"method":"GET","url":"...","header":{...},"body":"base64..."}
        
        :param endpoints: List of endpoint configurations
        :return: Newline-delimited JSON string
        """
        lines = []
        for ep in endpoints:
            target = {
                "method": ep.get("method", "GET"),
                "url": ep["url"],
            }
            
            # Add headers
            if "headers" in ep and ep["headers"]:
                target["header"] = {k: [v] for k, v in ep["headers"].items()}
            
            # Add body (base64 encoded as Vegeta JSON format expects)
            if "body" in ep and ep["body"]:
                target["body"] = base64.b64encode(ep["body"].encode()).decode()
            
            lines.append(json.dumps(target, separators=(",", ":")))
        
        return "\n".join(lines)
    
    def _wait_for_pods_completion(
        self,
        pod_names: List[str],
        namespace: str,
        lib_telemetry: KrknTelemetryOpenshift,
        config: Dict[str, Any]
    ):
        """
        Wait for all HTTP load pods to complete.
        
        :param pod_names: List of pod names to wait for
        :param namespace: Namespace where pods are running
        :param lib_telemetry: Telemetry object for Kubernetes operations
        :param config: Scenario configuration
        """
        lib_k8s = lib_telemetry.get_lib_kubernetes()
        finished_pods = []
        did_finish = False
        
        # Calculate max wait time (duration + buffer)
        duration_str = config.get("duration", "30s")
        max_wait = self._parse_duration_to_seconds(duration_str) + 60  # Add 60s buffer
        start_time = time.time()
        
        while not did_finish:
            for pod_name in pod_names:
                if pod_name not in finished_pods:
                    if not lib_k8s.is_pod_running(pod_name, namespace):
                        finished_pods.append(pod_name)
                        logging.info(f"Pod {pod_name} has completed")
            
            if set(pod_names) == set(finished_pods):
                did_finish = True
                break
            
            # Check timeout
            if time.time() - start_time > max_wait:
                logging.warning(f"Timeout waiting for pods to complete (waited {max_wait}s)")
                break
            
            time.sleep(5)
        
        logging.info(f"All {len(finished_pods)}/{len(pod_names)} pods have completed")
    
    def _collect_and_aggregate_results(
        self,
        pod_names: List[str],
        namespace: str,
        lib_telemetry: KrknTelemetryOpenshift
    ) -> Dict[str, Any]:
        """
        Collect results from all pods and aggregate metrics.
        
        :param pod_names: List of pod names
        :param namespace: Namespace where pods ran
        :param lib_telemetry: Telemetry object for Kubernetes operations
        :return: Aggregated metrics dictionary
        """
        lib_k8s = lib_telemetry.get_lib_kubernetes()
        all_metrics = []
        
        logging.info("Collecting results from HTTP load pods...")
        
        for pod_name in pod_names:
            try:
                # Read pod logs to get results
                log_response = lib_k8s.get_pod_log(pod_name, namespace)
                
                # Handle HTTPResponse object from kubernetes client
                if hasattr(log_response, 'data'):
                    logs = log_response.data.decode('utf-8') if isinstance(log_response.data, bytes) else str(log_response.data)
                elif hasattr(log_response, 'read'):
                    logs = log_response.read().decode('utf-8')
                else:
                    logs = str(log_response)
                
                # Parse JSON report from logs
                metrics = self._parse_metrics_from_logs(logs)
                
                if metrics:
                    all_metrics.append(metrics)
                    logging.info(f"Collected metrics from pod: {pod_name}")
                else:
                    logging.warning(f"No metrics found in logs for pod: {pod_name}")
            
            except Exception as e:
                logging.warning(f"Failed to collect results from pod {pod_name}: {e}")
        
        if not all_metrics:
            logging.warning("No metrics collected from any pods")
            return {}
        
        # Aggregate metrics from all pods
        aggregated = self._aggregate_metrics(all_metrics)
        logging.info(f"Aggregated metrics from {len(all_metrics)} pod(s)")
        
        return aggregated
    
    def _parse_metrics_from_logs(self, logs: str) -> Dict[str, Any]:
        """
        Parse Vegeta JSON metrics from pod logs.
        
        :param logs: Pod logs
        :return: Metrics dictionary or None
        """
        try:
            # Look for JSON report section in logs
            for line in logs.split('\n'):
                line = line.strip()
                if line.startswith('{') and '"latencies"' in line:
                    return json.loads(line)
            return None
        except Exception as e:
            logging.warning(f"Failed to parse metrics from logs: {e}")
            return None
    
    def _aggregate_metrics(self, metrics_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate metrics from multiple pods.
        
        :param metrics_list: List of metrics dictionaries from each pod
        :return: Aggregated metrics
        """
        if not metrics_list:
            return {}
        
        # Sum totals
        total_requests = sum(m.get("requests", 0) for m in metrics_list)
        total_rate = sum(m.get("rate", 0) for m in metrics_list)
        total_throughput = sum(m.get("throughput", 0) for m in metrics_list)
        
        # Average latencies (weighted by request count)
        latencies = {}
        if total_requests > 0:
            for percentile in ["mean", "50th", "95th", "99th", "max", "min"]:
                weighted_sum = sum(
                    m.get("latencies", {}).get(percentile, 0) * m.get("requests", 0)
                    for m in metrics_list
                )
                latencies[percentile] = weighted_sum / total_requests if total_requests > 0 else 0
        
        # Average success rate (weighted by request count)
        total_success = sum(
            m.get("success", 0) * m.get("requests", 0)
            for m in metrics_list
        )
        success_rate = total_success / total_requests if total_requests > 0 else 0
        
        # Aggregate status codes
        status_codes = {}
        for metrics in metrics_list:
            for code, count in metrics.get("status_codes", {}).items():
                status_codes[code] = status_codes.get(code, 0) + count
        
        # Aggregate bytes
        bytes_in_total = sum(m.get("bytes_in", {}).get("total", 0) for m in metrics_list)
        bytes_out_total = sum(m.get("bytes_out", {}).get("total", 0) for m in metrics_list)
        
        # Aggregate errors
        all_errors = []
        for metrics in metrics_list:
            all_errors.extend(metrics.get("errors", []))
        
        return {
            "requests": total_requests,
            "rate": total_rate,
            "throughput": total_throughput,
            "latencies": latencies,
            "success": success_rate,
            "status_codes": status_codes,
            "bytes_in": {"total": bytes_in_total},
            "bytes_out": {"total": bytes_out_total},
            "errors": all_errors[:10],  # First 10 errors only
            "pod_count": len(metrics_list)
        }
    
    def _parse_duration_to_seconds(self, duration: str) -> int:
        """
        Parse duration string to seconds.
        
        :param duration: Duration string like "30s", "5m", "1h"
        :return: Duration in seconds
        """
        import re
        
        match = re.match(r'^(\d+)(s|m|h)$', str(duration))
        if not match:
            logging.warning(f"Invalid duration format: {duration}, defaulting to 30s")
            return 30
        
        value = int(match.group(1))
        unit = match.group(2)
        
        multipliers = {
            "s": 1,
            "m": 60,
            "h": 3600,
        }
        
        return value * multipliers.get(unit, 1)
    
    @staticmethod
    def rollback_http_load_pods(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift
    ):
        """
        Rollback function to delete HTTP load pods.
        
        :param rollback_content: Rollback content containing namespace and pod names
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations
        """
        try:
            namespace = rollback_content.namespace
            pod_names = json.loads(
                base64.b64decode(rollback_content.resource_identifier.encode('utf-8')).decode('utf-8')
            )
            
            logging.info(f"Rolling back HTTP load pods: {pod_names} in namespace: {namespace}")
            
            for pod_name in pod_names:
                try:
                    lib_telemetry.get_lib_kubernetes().delete_pod(pod_name, namespace)
                    logging.info(f"Deleted pod: {pod_name}")
                except Exception as e:
                    logging.warning(f"Failed to delete pod {pod_name}: {e}")
            
            logging.info("Rollback of HTTP load pods completed")
        except Exception as e:
            logging.error(f"Failed to rollback HTTP load pods: {e}")

    def _log_metrics_summary(self, metrics: Dict[str, Any]):
        """Log summary of test metrics."""
        logging.info("=" * 60)
        logging.info("HTTP Load Test Results Summary (Aggregated)")
        logging.info("=" * 60)
        
        # Pod count
        pod_count = metrics.get("pod_count", 1)
        logging.info(f"Load Generator Pods: {pod_count}")
        
        # Request statistics
        requests = metrics.get("requests", 0)
        logging.info(f"Total Requests: {requests}")
        
        # Success rate
        success = metrics.get("success", 0.0)
        logging.info(f"Success Rate: {success * 100:.2f}%")
        
        # Latency statistics
        latencies = metrics.get("latencies", {})
        if latencies:
            logging.info(f"Latency Mean: {latencies.get('mean', 0) / 1e6:.2f} ms")
            logging.info(f"Latency P50: {latencies.get('50th', 0) / 1e6:.2f} ms")
            logging.info(f"Latency P95: {latencies.get('95th', 0) / 1e6:.2f} ms")
            logging.info(f"Latency P99: {latencies.get('99th', 0) / 1e6:.2f} ms")
            logging.info(f"Latency Max: {latencies.get('max', 0) / 1e6:.2f} ms")
        
        # Throughput
        throughput = metrics.get("throughput", 0.0)
        logging.info(f"Total Throughput: {throughput:.2f} req/s")
        
        # Bytes
        bytes_in = metrics.get("bytes_in", {})
        bytes_out = metrics.get("bytes_out", {})
        if bytes_in:
            logging.info(f"Bytes In (total): {bytes_in.get('total', 0) / 1024 / 1024:.2f} MB")
        if bytes_out:
            logging.info(f"Bytes Out (total): {bytes_out.get('total', 0) / 1024 / 1024:.2f} MB")
        
        # Status codes
        status_codes = metrics.get("status_codes", {})
        if status_codes:
            logging.info("Status Code Distribution:")
            for code, count in sorted(status_codes.items()):
                logging.info(f"  {code}: {count}")
        
        # Errors
        errors = metrics.get("errors", [])
        if errors:
            logging.warning(f"Errors encountered: {len(errors)}")
            for error in errors[:5]:  # Show first 5 errors
                logging.warning(f"  - {error}")
        
        logging.info("=" * 60)

