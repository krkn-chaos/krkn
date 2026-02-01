import logging
import os
import time

import yaml
from jinja2 import Environment, FileSystemLoader
from kubernetes import client
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.cerberus import setup as cerberus
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class HttpLoadScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as file:
                config = yaml.safe_load(file)
                http_load_config = config["http_load"]

                target_url = get_yaml_item_value(http_load_config, "target_url", "")
                target_service = get_yaml_item_value(http_load_config, "target_service", "")
                target_ingress = get_yaml_item_value(http_load_config, "target_ingress", "")
                target_route = get_yaml_item_value(http_load_config, "target_route", "")
                target_port = get_yaml_item_value(http_load_config, "target_port", 80)
                target_path = get_yaml_item_value(http_load_config, "target_path", "")
                namespace = get_yaml_item_value(http_load_config, "namespace", "default")

                duration = int(get_yaml_item_value(http_load_config, "duration", 30))
                concurrency = int(get_yaml_item_value(http_load_config, "concurrency", 10))
                requests_per_second = int(get_yaml_item_value(http_load_config, "requests_per_second", 0))
                http_method = get_yaml_item_value(http_load_config, "http_method", "GET")
                number_of_pods = int(get_yaml_item_value(http_load_config, "number_of_pods", 1))
                image = get_yaml_item_value(
                    http_load_config, "image", "williamyeh/hey:latest"
                )

                if duration <= 0:
                    logging.error("HttpLoadScenarioPlugin: duration must be positive")
                    return 1
                if concurrency <= 0:
                    logging.error("HttpLoadScenarioPlugin: concurrency must be positive")
                    return 1
                if requests_per_second < 0:
                    logging.error("HttpLoadScenarioPlugin: requests_per_second cannot be negative")
                    return 1
                if number_of_pods <= 0:
                    logging.error("HttpLoadScenarioPlugin: number_of_pods must be positive")
                    return 1

                request_body = get_yaml_item_value(http_load_config, "request_body", "")
                headers = get_yaml_item_value(http_load_config, "headers", {})
                content_type = get_yaml_item_value(http_load_config, "content_type", "")

                kubecli = lib_telemetry.get_lib_kubernetes()

                resolved_url = self.resolve_target_url(
                    kubecli, target_url, target_service, target_ingress,
                    target_route, target_port, target_path, namespace
                )

                if not resolved_url:
                    logging.error(
                        "HttpLoadScenarioPlugin: Could not resolve target URL. "
                        "Specify one of: target_url, target_service, target_ingress, or target_route"
                    )
                    return 1

                logging.info(f"HttpLoadScenarioPlugin: Target URL: {resolved_url}")
                logging.info(
                    f"HttpLoadScenarioPlugin: Duration: {duration}s, Concurrency: {concurrency}, "
                    f"Pods: {number_of_pods}, Method: {http_method}"
                )

                file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
                env = Environment(loader=file_loader, autoescape=True)
                job_template = env.get_template("job.j2")

                cmd = self.build_load_command(
                    resolved_url, duration, concurrency, requests_per_second,
                    http_method, request_body, headers, content_type
                )

                job_list = []
                start_time = int(time.time())
                try:
                    for i in range(number_of_pods):
                        jobname = f"{run_uuid[:8]}-{i}"
                        job_body = yaml.safe_load(
                            job_template.render(
                                jobname=jobname,
                                namespace=namespace,
                                image=image,
                                cmd=cmd,
                            )
                        )
                        job_list.append(job_body["metadata"]["name"])
                        api_response = kubecli.create_job(job_body, namespace=namespace)
                        if api_response is None:
                            logging.error("HttpLoadScenarioPlugin: Error creating job")
                            return 1
                        logging.info(f"HttpLoadScenarioPlugin: Created job {job_body['metadata']['name']}")

                    logging.info("HttpLoadScenarioPlugin: Waiting for jobs to complete")
                    self.wait_for_jobs(job_list[:], kubecli, namespace, duration + 300)
                    self.collect_job_metrics(job_list[:], kubecli, namespace)

                except Exception as e:
                    logging.error(f"HttpLoadScenarioPlugin: Exception during execution: {e}")
                    return 1
                finally:
                    end_time = int(time.time())
                    cerberus.publish_kraken_status(krkn_config, [], start_time, end_time)
                    logging.info("HttpLoadScenarioPlugin: Cleaning up jobs")
                    self.delete_jobs(job_list[:], kubecli, namespace)

        except Exception as e:
            logging.error(f"HttpLoadScenarioPlugin: Exception: {e}")
            return 1
        else:
            return 0

    def resolve_target_url(
        self, kubecli, target_url, target_service, target_ingress,
        target_route, target_port, target_path, namespace
    ):
        if target_url:
            return target_url

        if target_service:
            if not kubecli.service_exists(target_service, namespace):
                logging.error(
                    f"HttpLoadScenarioPlugin: Service {target_service} not found in namespace {namespace}"
                )
                return None
            url = f"http://{target_service}.{namespace}.svc.cluster.local:{target_port}"
            if target_path:
                url += f"/{target_path.lstrip('/')}"
            return url

        if target_ingress:
            return self.resolve_ingress_url(kubecli, target_ingress, namespace, target_path)

        if target_route:
            return self.resolve_route_url(kubecli, target_route, namespace, target_path)

        return None

    def resolve_ingress_url(self, kubecli, ingress_name, namespace, target_path):
        try:
            networking_v1 = client.NetworkingV1Api(kubecli.api_client)
            ingress = networking_v1.read_namespaced_ingress(name=ingress_name, namespace=namespace)

            if not ingress.spec.rules or len(ingress.spec.rules) == 0:
                logging.error(f"HttpLoadScenarioPlugin: Ingress {ingress_name} has no rules defined")
                return None

            rule = ingress.spec.rules[0]
            host = rule.host if rule.host else "localhost"

            protocol = "http"
            if ingress.spec.tls:
                for tls in ingress.spec.tls:
                    if tls.hosts and host in tls.hosts:
                        protocol = "https"
                        break

            path = target_path
            if not path and rule.http and rule.http.paths:
                path = rule.http.paths[0].path or ""

            url = f"{protocol}://{host}"
            if path:
                url += f"/{path.lstrip('/')}"

            logging.info(f"HttpLoadScenarioPlugin: Resolved Ingress {ingress_name} to {url}")
            return url

        except client.ApiException as e:
            if e.status == 404:
                logging.error(f"HttpLoadScenarioPlugin: Ingress {ingress_name} not found in namespace {namespace}")
            else:
                logging.error(f"HttpLoadScenarioPlugin: Error reading Ingress {ingress_name}: {e}")
            return None

    def resolve_route_url(self, kubecli, route_name, namespace, target_path):
        try:
            custom_api = client.CustomObjectsApi(kubecli.api_client)
            route = custom_api.get_namespaced_custom_object(
                group="route.openshift.io",
                version="v1",
                namespace=namespace,
                plural="routes",
                name=route_name,
            )

            spec = route.get("spec", {})
            host = spec.get("host", "")

            if not host:
                logging.error(f"HttpLoadScenarioPlugin: Route {route_name} has no host defined")
                return None

            tls = spec.get("tls")
            protocol = "https" if tls else "http"

            path = target_path or spec.get("path", "")

            url = f"{protocol}://{host}"
            if path:
                url += f"/{path.lstrip('/')}"

            logging.info(f"HttpLoadScenarioPlugin: Resolved Route {route_name} to {url}")
            return url

        except client.ApiException as e:
            if e.status == 404:
                logging.error(
                    f"HttpLoadScenarioPlugin: Route {route_name} not found in namespace {namespace}. "
                    "Note: Routes are only available on OpenShift clusters."
                )
            else:
                logging.error(f"HttpLoadScenarioPlugin: Error reading Route {route_name}: {e}")
            return None

    def build_load_command(
        self, target_url, duration, concurrency, requests_per_second,
        http_method, request_body="", headers=None, content_type=""
    ):
        cmd = f"hey -c {concurrency} -z {duration}s -m {http_method}"

        if requests_per_second > 0:
            cmd += f" -q {requests_per_second}"

        if content_type:
            escaped_content_type = content_type.replace("'", "'\"'\"'")
            cmd += f" -T '{escaped_content_type}'"

        if headers:
            for key, value in headers.items():
                escaped_value = str(value).replace("'", "'\"'\"'")
                cmd += f" -H '{key}: {escaped_value}'"

        if request_body:
            escaped_body = request_body.replace("'", "'\"'\"'")
            cmd += f" -d '{escaped_body}'"

        escaped_url = target_url.replace("'", "'\"'\"'")
        cmd += f" '{escaped_url}'"
        return cmd

    def wait_for_jobs(self, job_list, kubecli, namespace, timeout=300):
        wait_time = time.time() + timeout
        completed_count = 0
        total_jobs = len(job_list)
        pending_jobs = job_list[:]

        while completed_count != total_jobs:
            for jobname in pending_jobs[:]:
                try:
                    api_response = kubecli.get_job_status(jobname, namespace=namespace)
                    if api_response.status.succeeded is not None or api_response.status.failed is not None:
                        completed_count += 1
                        pending_jobs.remove(jobname)
                        status = "succeeded" if api_response.status.succeeded else "failed"
                        logging.info(f"HttpLoadScenarioPlugin: Job {jobname} {status}")
                except Exception as e:
                    logging.warning(f"HttpLoadScenarioPlugin: Exception getting job status for {jobname}: {e}")

                if time.time() > wait_time:
                    raise Exception("HttpLoadScenarioPlugin: Timeout waiting for jobs to complete")

            time.sleep(5)

    def collect_job_metrics(self, job_list, kubecli, namespace):
        for jobname in job_list:
            try:
                api_response = kubecli.get_job_status(jobname, namespace=namespace)
                pod_name = self.get_job_pod(api_response, kubecli, namespace)

                if pod_name:
                    pod_log_response = kubecli.get_pod_log(name=pod_name, namespace=namespace)
                    if pod_log_response:
                        pod_log = pod_log_response.data.decode("utf-8")

                        if api_response.status.succeeded:
                            logging.info(f"HttpLoadScenarioPlugin: Metrics from job {jobname}:")
                            for line in pod_log.strip().split("\n"):
                                logging.info(f"  {line}")
                        else:
                            logging.error(f"HttpLoadScenarioPlugin: Job {jobname} failed. Output:")
                            logging.error(pod_log)

            except Exception as e:
                logging.warning(f"HttpLoadScenarioPlugin: Could not collect metrics for job {jobname}: {e}")

    def get_job_pod(self, api_response, kubecli, namespace):
        try:
            controller_uid = api_response.metadata.labels.get("controller-uid")
            if not controller_uid:
                return None

            pod_label_selector = f"controller-uid={controller_uid}"
            pods_list = kubecli.list_pods(
                label_selector=pod_label_selector, namespace=namespace
            )
            return pods_list[0] if pods_list else None
        except Exception:
            return None

    def delete_jobs(self, job_list, kubecli, namespace):
        for jobname in job_list:
            try:
                api_response = kubecli.get_job_status(jobname, namespace=namespace)
                if api_response.status.failed is not None:
                    pod_name = self.get_job_pod(api_response, kubecli, namespace)
                    if pod_name:
                        pod_stat = kubecli.read_pod(name=pod_name, namespace=namespace)
                        logging.error(
                            f"HttpLoadScenarioPlugin: Job {jobname} failed. "
                            f"Container status: {pod_stat.status.container_statuses}"
                        )
                        pod_log_response = kubecli.get_pod_log(name=pod_name, namespace=namespace)
                        if pod_log_response:
                            pod_log = pod_log_response.data.decode("utf-8")
                            logging.error(f"HttpLoadScenarioPlugin: Pod logs:\n{pod_log}")
            except Exception:
                logging.warning(f"HttpLoadScenarioPlugin: Exception getting job status for {jobname}")

            try:
                kubecli.delete_job(name=jobname, namespace=namespace)
            except Exception as e:
                logging.warning(f"HttpLoadScenarioPlugin: Failed to delete job {jobname}: {e}")

    def get_scenario_types(self) -> list[str]:
        return ["http_load_scenarios"]
