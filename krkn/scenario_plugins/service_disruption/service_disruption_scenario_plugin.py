import logging
import random
import time

import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class ServiceDisruptionScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as f:
                scenario_config_yaml = yaml.full_load(f)
                for scenario in scenario_config_yaml["scenarios"]:
                    scenario_namespace = get_yaml_item_value(scenario, "namespace", "")
                    scenario_label = get_yaml_item_value(scenario, "label_selector", "")
                    if (
                        scenario_namespace is not None
                        and scenario_namespace.strip() != ""
                    ):
                        if scenario_label is not None and scenario_label.strip() != "":
                            logging.error(
                                "ServiceDisruptionScenarioPlugin You can only have namespace or "
                                "label set in your namespace scenario"
                            )
                            logging.error(
                                "ServiceDisruptionScenarioPlugin Current scenario config has "
                                "namespace '%s' and label selector '%s'"
                                % (scenario_namespace, scenario_label)
                            )
                            logging.error(
                                "ServiceDisruptionScenarioPlugin Please set either namespace "
                                "to blank ('') or label_selector to blank ('') to continue"
                            )
                            return 1
                    delete_count = get_yaml_item_value(scenario, "delete_count", 1)
                    run_count = get_yaml_item_value(scenario, "runs", 1)
                    run_sleep = get_yaml_item_value(scenario, "sleep", 10)
                    wait_time = get_yaml_item_value(scenario, "wait_time", 30)

                    logging.info(
                        str(scenario_namespace)
                        + str(scenario_label)
                        + str(delete_count)
                        + str(run_count)
                        + str(run_sleep)
                        + str(wait_time)
                    )
                    for i in range(run_count):
                        killed_namespaces = {}
                        namespaces = (
                            lib_telemetry.get_lib_kubernetes().check_namespaces(
                                [scenario_namespace], scenario_label
                            )
                        )
                        for j in range(delete_count):
                            if len(namespaces) == 0:
                                logging.error(
                                    "ServiceDisruptionScenarioPlugin Couldn't delete %s namespaces, ù"
                                    "not enough namespaces matching %s with label %s"
                                    % (
                                        str(run_count),
                                        scenario_namespace,
                                        str(scenario_label),
                                    )
                                )
                                return 1

                            selected_namespace = namespaces[
                                random.randint(0, len(namespaces) - 1)
                            ]
                            logging.info(
                                "Delete objects in selected namespace: "
                                + selected_namespace
                            )
                            try:
                                # delete all pods in namespace
                                objects = self.delete_objects(
                                    lib_telemetry.get_lib_kubernetes(),
                                    selected_namespace,
                                )
                                killed_namespaces[selected_namespace] = objects
                                logging.info(
                                    "Deleted all objects in namespace %s was successful"
                                    % str(selected_namespace)
                                )
                            except Exception as e:
                                logging.info(
                                    "ServiceDisruptionScenarioPlugin Delete all "
                                    "objects in namespace %s was unsuccessful"
                                    % str(selected_namespace)
                                )
                                logging.info("Namespace action error: " + str(e))
                                return 1
                            namespaces.remove(selected_namespace)
                            logging.info(
                                "Waiting %s seconds between namespace deletions"
                                % str(run_sleep)
                            )
                            time.sleep(run_sleep)

        except (Exception, RuntimeError) as e:
            logging.error(
                "ServiceDisruptionScenarioPlugin exiting due to Exception %s" % e
            )
            return 1
        else:
            return 0

    def delete_objects(self, kubecli, namespace):

        services = self.delete_all_services_namespace(kubecli, namespace)
        daemonsets = self.delete_all_daemonset_namespace(kubecli, namespace)
        statefulsets = self.delete_all_statefulsets_namespace(kubecli, namespace)
        replicasets = self.delete_all_replicaset_namespace(kubecli, namespace)
        deployments = self.delete_all_deployment_namespace(kubecli, namespace)

        objects = {
            "daemonsets": daemonsets,
            "deployments": deployments,
            "replicasets": replicasets,
            "statefulsets": statefulsets,
            "services": services,
        }

        return objects

    def get_list_running_pods(self, kubecli: KrknKubernetes, namespace: str):
        running_pods = []
        pods = kubecli.list_pods(namespace)
        for pod in pods:
            pod_status = kubecli.get_pod_info(pod, namespace)
            if pod_status and pod_status.status == "Running":
                running_pods.append(pod)
        logging.info("all running pods " + str(running_pods))
        return running_pods

    def delete_all_deployment_namespace(self, kubecli: KrknKubernetes, namespace: str):
        """
        Delete all the deployments in the specified namespace

        :param kubecli: krkn kubernetes python package
        :param namespace: namespace
        """
        try:
            deployments = kubecli.get_deployment_ns(namespace)
            for deployment in deployments:
                logging.info("Deleting deployment" + deployment)
                kubecli.delete_deployment(deployment, namespace)
        except Exception as e:
            logging.error(
                "Exception when calling delete_all_deployment_namespace: %s\n",
                str(e),
            )
            raise e

        return deployments

    def delete_all_daemonset_namespace(self, kubecli: KrknKubernetes, namespace: str):
        """
        Delete all the daemonset in the specified namespace

        :param kubecli: krkn kubernetes python package
        :param namespace: namespace
        """
        try:
            daemonsets = kubecli.get_daemonset(namespace)
            for daemonset in daemonsets:
                logging.info("Deleting daemonset" + daemonset)
                kubecli.delete_daemonset(daemonset, namespace)
        except Exception as e:
            logging.error(
                "Exception when calling delete_all_daemonset_namespace: %s\n",
                str(e),
            )
            raise e

        return daemonsets

    def delete_all_statefulsets_namespace(
        self, kubecli: KrknKubernetes, namespace: str
    ):
        """
        Delete all the statefulsets in the specified namespace


        :param kubecli: krkn kubernetes python package
        :param namespace: namespace
        """
        try:
            statefulsets = kubecli.get_all_statefulset(namespace)
            for statefulset in statefulsets:
                logging.info("Deleting statefulset" + statefulset)
                kubecli.delete_statefulset(statefulset, namespace)
        except Exception as e:
            logging.error(
                "Exception when calling delete_all_statefulsets_namespace: %s\n",
                str(e),
            )
            raise e

        return statefulsets

    def delete_all_replicaset_namespace(self, kubecli: KrknKubernetes, namespace: str):
        """
        Delete all the replicasets in the specified namespace

        :param kubecli: krkn kubernetes python package
        :param namespace: namespace
        """
        try:
            replicasets = kubecli.get_all_replicasets(namespace)
            for replicaset in replicasets:
                logging.info("Deleting replicaset" + replicaset)
                kubecli.delete_replicaset(replicaset, namespace)
        except Exception as e:
            logging.error(
                "Exception when calling delete_all_replicaset_namespace: %s\n",
                str(e),
            )
            raise e

        return replicasets

    def delete_all_services_namespace(self, kubecli: KrknKubernetes, namespace: str):
        """
        Delete all the services in the specified namespace


        :param kubecli: krkn kubernetes python package
        :param namespace: namespace
        """
        try:
            services = kubecli.get_all_services(namespace)
            for service in services:
                logging.info("Deleting services" + service)
                kubecli.delete_services(service, namespace)
        except Exception as e:
            logging.error(
                "Exception when calling delete_all_services_namespace: %s\n",
                str(e),
            )
            raise e

        return services

    def check_all_running_pods(
        self, kubecli: KrknKubernetes, namespace_name, wait_time
    ):

        timer = 0
        while timer < wait_time:
            pod_list = kubecli.list_pods(namespace_name)
            pods_running = 0
            for pod in pod_list:
                pod_info = kubecli.get_pod_info(pod, namespace_name)
                if pod_info.status != "Running" and pod_info.status != "Succeeded":
                    logging.info(
                        "Pods %s still not running or completed" % pod_info.name
                    )
                    break
                pods_running += 1
            if len(pod_list) == pods_running:
                break
            timer += 5
            time.sleep(5)
            logging.info("Waiting 5 seconds for pods to become active")

    # krkn_lib
    def check_all_running_deployment(
        self, killed_namespaces, wait_time, kubecli: KrknKubernetes
    ):

        timer = 0
        while timer < wait_time and killed_namespaces:
            still_missing_ns = killed_namespaces.copy()
            for namespace_name, objects in killed_namespaces.items():
                still_missing_obj = objects.copy()
                for obj_name, obj_list in objects.items():
                    if "deployments" == obj_name:
                        deployments = kubecli.get_deployment_ns(namespace_name)
                        if len(obj_list) == len(deployments):
                            still_missing_obj.pop(obj_name)
                    elif "replicasets" == obj_name:
                        replicasets = kubecli.get_all_replicasets(namespace_name)
                        if len(obj_list) == len(replicasets):
                            still_missing_obj.pop(obj_name)
                    elif "statefulsets" == obj_name:
                        statefulsets = kubecli.get_all_statefulset(namespace_name)
                        if len(obj_list) == len(statefulsets):
                            still_missing_obj.pop(obj_name)
                    elif "services" == obj_name:
                        services = kubecli.get_all_services(namespace_name)
                        if len(obj_list) == len(services):
                            still_missing_obj.pop(obj_name)
                    elif "daemonsets" == obj_name:
                        daemonsets = kubecli.get_daemonset(namespace_name)
                        if len(obj_list) == len(daemonsets):
                            still_missing_obj.pop(obj_name)
                logging.info("Still missing objects " + str(still_missing_obj))
                killed_namespaces[namespace_name] = still_missing_obj.copy()
                if len(killed_namespaces[namespace_name].keys()) == 0:
                    logging.info(
                        "Wait for pods to become running for namespace: "
                        + namespace_name
                    )
                    self.check_all_running_pods(kubecli, namespace_name, wait_time)
                    still_missing_ns.pop(namespace_name)
            killed_namespaces = still_missing_ns
            if len(killed_namespaces.keys()) == 0:
                return []

            timer += 10
            time.sleep(10)
            logging.info(
                "Waiting 10 seconds for objects in namespaces to become active"
            )

        logging.error(
            "Objects are still not ready after waiting " + str(wait_time) + "seconds"
        )
        logging.error("Non active namespaces " + str(killed_namespaces))
        return killed_namespaces

    def get_scenario_types(self) -> list[str]:
        return ["service_disruption_scenarios"]
