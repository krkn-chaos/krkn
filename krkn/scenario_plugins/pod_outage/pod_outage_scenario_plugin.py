import logging
import os
from datetime import time
from random import random

from jinja2 import FileSystemLoader, Environment
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from kubernetes import client

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.pod_outage.models.models import InputParams,EgressParams,IngressParams
from krkn.scenario_plugins.pod_outage.utils import get_bridge_name, get_test_pods, check_bridge_interface, \
    apply_outage_policy, wait_for_job, delete_jobs, apply_net_policy, apply_ingress_policy, delete_virtual_interfaces


class PodOutageScenarioPlugin(AbstractScenarioPlugin):
    def run(self, run_uuid: str, scenario: str, krkn_config: dict[str, any], lib_telemetry: KrknTelemetryOpenshift,
            scenario_telemetry: ScenarioTelemetry) -> int:
        pass

    def get_scenario_types(self) -> list[str]:
        return [
            "pod_network_scenarios",
        ]

def pod_outage(
    params: InputParams,
    kubecli: KrknKubernetes
):
    """
    Function that performs pod outage chaos scenario based
    on the provided confiapply_net_policyguration

    Args:
        params (InputParams, KrknKubernetes)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """

    file_loader = FileSystemLoader(os.path.join(os.path.abspath(os.path.dirname(__file__)),"templates"))
    env = Environment(loader=file_loader)
    job_template = env.get_template("job.j2")
    pod_module_template = env.get_template("pod_module.j2")
    test_namespace = params.namespace
    test_label_selector = params.label_selector
    test_pod_name = params.pod_name
    filter_dict = {}
    job_list = []

    for i in params.direction:
        filter_dict[i] = eval(f"params.{i}_ports")

    try:
        ip_set = set()
        node_dict = {}
        label_set = set()

        api_ext = client.ApiextensionsV1Api(kubecli.api_client)
        custom_obj = client.CustomObjectsApi(kubecli.api_client)

        br_name = get_bridge_name(api_ext, custom_obj)
        pods_list = get_test_pods(
            test_pod_name, test_label_selector, test_namespace, kubecli
        )

        while not len(pods_list) <= params.instance_count:
            pods_list.pop(random.randint(0, len(pods_list) - 1))

        for pod_name in pods_list:
            pod_stat = kubecli.read_pod(pod_name, test_namespace)
            ip_set.add(pod_stat.status.pod_ip)
            node_dict.setdefault(pod_stat.spec.node_name, [])
            node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
            for key, value in pod_stat.metadata.labels.items():
                label_set.add("%s=%s" % (key, value))

        check_bridge_interface(
            list(node_dict.keys())[0], pod_module_template, br_name, kubecli
        )

        for direction, ports in filter_dict.items():
            pass
            job_list.extend(
                apply_outage_policy(
                    node_dict,
                    ports,
                    job_template,
                    pod_module_template,
                    direction,
                    params.test_duration,
                    br_name,
                    kubecli,
                )
            )

        logging.info("Waiting for job to finish")
        wait_for_job(job_list[:], kubecli, params.test_duration + 300)
        logging.info("Pod outage successfully executed")
    except Exception as e:
        raise Exception("Pod outage scenario exiting due to Exception - %s" % e)
    finally:
        logging.info("Deleting jobs(if any)")
        delete_jobs(kubecli, job_list[:])





def pod_egress_shaping(
    params: EgressParams,
    kubecli: KrknKubernetes
):
    """
    Function that performs egress pod traffic shaping based
    on the provided configuration

    Args:
        params (EgressParams,)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """

    file_loader = FileSystemLoader(os.path.join(os.path.abspath(os.path.dirname(__file__),"templates")))
    env = Environment(loader=file_loader)
    job_template = env.get_template("job.j2")
    pod_module_template = env.get_template("pod_module.j2")
    test_namespace = params.namespace
    test_label_selector = params.label_selector
    test_pod_name = params.pod_name
    job_list = []
    try:
        ip_set = set()
        node_dict = {}
        label_set = set()
        param_lst = ["latency", "loss", "bandwidth"]
        mod_lst = [i for i in param_lst if i in params.network_params]

        api_ext = client.ApiextensionsV1Api(kubecli.api_client)
        custom_obj = client.CustomObjectsApi(kubecli.api_client)

        br_name = get_bridge_name(api_ext, custom_obj)
        pods_list = get_test_pods(
            test_pod_name, test_label_selector, test_namespace, kubecli
        )

        while not len(pods_list) <= params.instance_count:
            pods_list.pop(random.randint(0, len(pods_list) - 1))
        for pod_name in pods_list:
            pod_stat = kubecli.read_pod(pod_name, test_namespace)
            ip_set.add(pod_stat.status.pod_ip)
            node_dict.setdefault(pod_stat.spec.node_name, [])
            node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
            for key, value in pod_stat.metadata.labels.items():
                label_set.add("%s=%s" % (key, value))

        check_bridge_interface(
            list(node_dict.keys())[0], pod_module_template, br_name, kubecli
        )

        for mod in mod_lst:
            for node, ips in node_dict.items():
                job_list.extend(
                    apply_net_policy(
                        mod,
                        node,
                        ips,
                        job_template,
                        pod_module_template,
                        params.network_params,
                        params.test_duration,
                        br_name,
                        kubecli,
                        params.execution_type,
                    )
                )
            if params.execution_type == "serial":
                logging.info("Waiting for serial job to finish")
                wait_for_job(job_list[:], kubecli, params.test_duration + 20)
                logging.info("Waiting for wait_duration %s" % params.test_duration)
                time.sleep(params.test_duration)

            if params.execution_type == "parallel":
                break
        if params.execution_type == "parallel":
            logging.info("Waiting for parallel job to finish")
            wait_for_job(job_list[:], kubecli, params.test_duration + 300)
            logging.info("Waiting for wait_duration %s" % params.test_duration)
            time.sleep(params.test_duration)
        logging.info("Pod egress shaping successfully executed")
    except Exception as e:
        raise Exception("Pod egress shaping scenario exiting due to Exception - %s" % e)
    finally:
        logging.info("Deleting jobs(if any)")
        delete_jobs(kubecli, job_list[:])


def pod_ingress_shaping(
    params: IngressParams,
    kubecli: KrknKubernetes
):
    """
    Function that performs ingress pod traffic shaping based
    on the provided configuration

    Args:
        params (IngressParams,)
            - The object containing the configuration for the scenario

    Returns
        A 'success' or 'error' message along with their details
    """

    file_loader = FileSystemLoader(os.path.join(os.path.abspath(os.path.dirname(__file__),"templates")))
    env = Environment(loader=file_loader)
    job_template = env.get_template("job.j2")
    pod_module_template = env.get_template("pod_module.j2")
    test_namespace = params.namespace
    test_label_selector = params.label_selector
    test_pod_name = params.pod_name
    job_list = []

    try:
        ip_set = set()
        node_dict = {}
        label_set = set()
        param_lst = ["latency", "loss", "bandwidth"]
        mod_lst = [i for i in param_lst if i in params.network_params]

        api_ext = client.ApiextensionsV1Api(kubecli.api_client)
        custom_obj = client.CustomObjectsApi(kubecli.api_client)

        br_name = get_bridge_name(api_ext, custom_obj)
        pods_list = get_test_pods(
            test_pod_name, test_label_selector, test_namespace, kubecli
        )

        while not len(pods_list) <= params.instance_count:
            pods_list.pop(random.randint(0, len(pods_list) - 1))
        for pod_name in pods_list:
            pod_stat = kubecli.read_pod(pod_name, test_namespace)
            ip_set.add(pod_stat.status.pod_ip)
            node_dict.setdefault(pod_stat.spec.node_name, [])
            node_dict[pod_stat.spec.node_name].append(pod_stat.status.pod_ip)
            for key, value in pod_stat.metadata.labels.items():
                label_set.add("%s=%s" % (key, value))

        check_bridge_interface(
            list(node_dict.keys())[0], pod_module_template, br_name, kubecli
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
                        params.network_params,
                        params.test_duration,
                        br_name,
                        kubecli,
                        params.execution_type,
                    )
                )
            if params.execution_type == "serial":
                logging.info("Waiting for serial job to finish")
                wait_for_job(job_list[:], kubecli, params.test_duration + 20)
                logging.info("Waiting for wait_duration %s" % params.test_duration)
                time.sleep(params.test_duration)
            if params.execution_type == "parallel":
                break
        if params.execution_type == "parallel":
            logging.info("Waiting for parallel job to finish")
            wait_for_job(job_list[:], kubecli, params.test_duration + 300)
            logging.info("Waiting for wait_duration %s" % params.test_duration)
            time.sleep(params.test_duration)
        logging.info("Pod ingress shaping successfully executed")

    except Exception as e:
        raise Exception("Pod ingress shaping scenario exiting due to Exception - %s" % e)

    finally:
        delete_virtual_interfaces(kubecli, node_dict.keys(), pod_module_template)
        logging.info("Deleting jobs(if any)")
        delete_jobs(kubecli, job_list[:])