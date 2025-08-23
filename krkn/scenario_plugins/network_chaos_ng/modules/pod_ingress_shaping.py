import os
import queue
import random
import time

from kubernetes import client
from jinja2 import FileSystemLoader, Environment
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.scenario_plugins.network_chaos_ng.models import (
    NetworkChaosScenarioType,
    BaseNetworkChaosConfig,
    PodNetworkShaping,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils import log_info
from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_shaping import (
    get_bridge_name,
    get_test_pods,
    check_bridge_interface,
    wait_for_job,
    delete_jobs,
    apply_ingress_policy,
    delete_virtual_interfaces,
)


class PodIngressShapingModule(AbstractNetworkChaosModule):

    config: PodNetworkShaping

    def __init__(self, config: PodNetworkShaping, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def run(self, target: str, error_queue: queue.Queue = None):
        file_loader = FileSystemLoader(
            os.path.join(os.path.abspath(os.path.dirname(__file__)), "templates")
        )
        env = Environment(loader=file_loader)
        job_template = env.get_template("job.j2")
        pod_module_template = env.get_template("pod_module.j2")
        test_namespace = self.config.namespace
        test_label_selector = self.config.label_selector
        test_pod_name = self.config.target
        job_list = []
        ip_set = set()
        node_dict = {}
        label_set = set()
        param_lst = ["latency", "loss", "bandwidth"]
        try:
            mod_lst = [i for i in param_lst if i in self.config]
            api_ext = client.ApiextensionsV1Api(
                self.kubecli.get_lib_kubernetes().api_client
            )
            custom_obj = client.CustomObjectsApi(
                self.kubecli.get_lib_kubernetes().api_client
            )
            br_name = get_bridge_name(api_ext, custom_obj)
            pods_list = get_test_pods(
                test_pod_name,
                test_label_selector,
                test_namespace,
                self.kubecli.get_lib_kubernetes(),
            )

            while not len(pods_list) <= self.config.instance_count:
                pods_list.pop(random.randint(0, len(pods_list) - 1))
            for pod_name in pods_list:
                pod_stat = self.kubecli.get_lib_kubernetes().read_pod(
                    pod_name, test_namespace
                )
                ip_set.add(pod_stat.status.pod_ip)
                node_dict.setdefault(pod_stat.spec.node_name, [])
                node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
                for key, value in pod_stat.metadata.labels.items():
                    label_set.add(f"{key}={value}")

            check_bridge_interface(
                list(node_dict.keys())[0],
                pod_module_template,
                br_name,
                self.kubecli.get_lib_kubernetes(),
                self.config.image,
                self.config.taints,
                self.config.service_account,
            )

            for mod in mod_lst:
                for node, ips in node_dict.items():
                    job_list.extend(
                        apply_ingress_policy(
                            mod,
                            node,
                            ips,
                            job_template,
                            pod_module_template,
                            {
                                "latency": self.config.latency,
                                "bandwidth": self.config.bandwidth,
                                "loss": self.config.loss,
                            },
                            self.config.test_duration,
                            br_name,
                            self.kubecli.get_lib_kubernetes(),
                            self.config.execution,
                            self.config.image,
                            self.config.taints,
                            self.config.service_account,
                        )
                    )
                if self.config.network_shaping_execution == "serial":
                    log_info("Waiting for serial job to finish")
                    wait_for_job(
                        job_list[:],
                        self.kubecli.get_lib_kubernetes(),
                        self.config.test_duration + 300,
                    )
                    log_info(f"Waiting for wait_duration {self.config.test_duration}")
                    log_info(f"Time out set after {self.config.test_duration + 300}")
                    time.sleep(self.config.wait_duration)
                if self.config.network_shaping_execution == "parallel":
                    break
            if self.config.network_shaping_execution == "parallel":
                log_info("Waiting for parallel job to finish")
                wait_for_job(
                    job_list[:],
                    self.kubecli.get_lib_kubernetes(),
                    self.config.test_duration + 300,
                )
                log_info(f"Waiting for wait_duration {self.config.test_duration}")
                log_info(f"Time out set after {self.config.test_duration + 300}")
                time.sleep(self.config.wait_duration)
            log_info("Pod ingress shaping successfully executed")

        except Exception as e:
            if error_queue is None:
                raise e
            else:
                error_queue.put(
                    f"Pod egress shaping scenario exiting due to Exception - {e}"
                )

        finally:
            node_keys = list[str](node_dict.keys())
            delete_virtual_interfaces(
                self.kubecli.get_lib_kubernetes(),
                node_keys,
                pod_module_template,
                self.config.image,
                self.config.taints,
                self.config.service_account,
            )
            log_info("Deleting jobs(if any)")
            delete_jobs(self.kubecli.get_lib_kubernetes(), job_list[:])

    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        return NetworkChaosScenarioType.Pod, self.config

    def get_targets(self) -> list[str]:
        return self.get_pod_targets()
