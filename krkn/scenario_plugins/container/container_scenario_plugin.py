import logging
import random
import time
import traceback
from asyncio import Future
import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.k8s.pod_monitor import select_and_monitor_by_namespace_pattern_and_label
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value


from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class ContainerScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario, "r") as f:
                cont_scenario_config = yaml.full_load(f)
                
                for kill_scenario in cont_scenario_config["scenarios"]:
                    future_snapshot = self.start_monitoring(
                        kill_scenario,
                        lib_telemetry
                    )
                    self.container_killing_in_pod(
                        kill_scenario, lib_telemetry.get_lib_kubernetes()
                    )
                    snapshot = future_snapshot.result()
                    result = snapshot.get_pods_status()
                    scenario_telemetry.affected_pods = result
                    if len(result.unrecovered) > 0:
                        logging.info("ContainerScenarioPlugin failed with unrecovered containers")
                        return 1
        except (RuntimeError, Exception) as e:
            logging.error("Stack trace:\n%s", traceback.format_exc())
            logging.error("ContainerScenarioPlugin exiting due to Exception %s" % e)
            return 1
        else:
            return 0

    def get_scenario_types(self) -> list[str]:
        return ["container_scenarios"]

    def start_monitoring(self, kill_scenario: dict, lib_telemetry: KrknTelemetryOpenshift) -> Future:
        namespace_pattern = f"^{kill_scenario['namespace']}$"
        label_selector = kill_scenario["label_selector"]
        recovery_time = kill_scenario["expected_recovery_time"]
        future_snapshot = select_and_monitor_by_namespace_pattern_and_label(
            namespace_pattern=namespace_pattern,
            label_selector=label_selector,
            max_timeout=recovery_time,
            v1_client=lib_telemetry.get_lib_kubernetes().cli
        )
        return future_snapshot

    def container_killing_in_pod(self, cont_scenario, kubecli: KrknKubernetes):
        scenario_name = get_yaml_item_value(cont_scenario, "name", "")
        namespace = get_yaml_item_value(cont_scenario, "namespace", "*")
        label_selector = get_yaml_item_value(cont_scenario, "label_selector", None)
        pod_names = get_yaml_item_value(cont_scenario, "pod_names", [])
        container_name = get_yaml_item_value(cont_scenario, "container_name", "")
        kill_action = get_yaml_item_value(cont_scenario, "action", 1)
        kill_count = get_yaml_item_value(cont_scenario, "count", 1)
        exclude_label = get_yaml_item_value(cont_scenario, "exclude_label", "")
        if not isinstance(kill_action, int):
            logging.error(
                "Please make sure the action parameter defined in the "
                "config is an integer"
            )
            raise RuntimeError()
        if (kill_action < 1) or (kill_action > 15):
            logging.error("Only 1-15 kill signals are supported.")
            raise RuntimeError()
        kill_action = "kill " + str(kill_action)
        if type(pod_names) != list:
            logging.error("Please make sure your pod_names are in a list format")
            # removed_exit
            # sys.exit(1)
            raise RuntimeError()
        if len(pod_names) == 0:
            if namespace == "*":
                # returns double array of pod name and namespace
                pods = kubecli.get_all_pods(label_selector)
            else:
                # Only returns pod names
                # Use list_pods with exclude_label parameter to exclude pods
                if exclude_label:
                    logging.info(
                        "Using exclude_label '%s' to exclude pods from container scenario %s in namespace %s",
                        exclude_label,
                        scenario_name,
                        namespace,
                    )
                pods = kubecli.list_pods(
                    namespace=namespace,
                    label_selector=label_selector,
                    exclude_label=exclude_label if exclude_label else None
                )
        else:
            if namespace == "*":
                logging.error(
                    "You must specify the namespace to kill a container in a specific pod"
                )
                logging.error("Scenario " + scenario_name + " failed")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()
            pods = pod_names

        # get container and pod name
        container_pod_list = []
        for pod in pods:
            if type(pod) == list:
                pod_output = kubecli.get_pod_info(pod[0], pod[1])
                container_names = [
                    container.name for container in pod_output.containers
                ]

                container_pod_list.append([pod[0], pod[1], container_names])
            else:
                pod_output = kubecli.get_pod_info(pod, namespace)
                container_names = [
                    container.name for container in pod_output.containers
                ]
                container_pod_list.append([pod, namespace, container_names])
        killed_count = 0
        killed_container_list = []
        while killed_count < kill_count:
            if len(container_pod_list) == 0:
                logging.error(
                    "Trying to kill more containers than were found, try lowering kill count"
                )
                logging.error("Scenario " + scenario_name + " failed")
                # removed_exit
                # sys.exit(1)
                raise RuntimeError()
            selected_container_pod = container_pod_list[
                random.randint(0, len(container_pod_list) - 1)
            ]
            for c_name in selected_container_pod[2]:
                if container_name != "":
                    if c_name == container_name:
                        killed_container_list.append(
                            [
                                selected_container_pod[0],
                                selected_container_pod[1],
                                c_name,
                            ]
                        )
                        self.retry_container_killing(
                            kill_action,
                            selected_container_pod[0],
                            selected_container_pod[1],
                            c_name,
                            kubecli,
                        )
                        break
                else:
                    killed_container_list.append(
                        [selected_container_pod[0], selected_container_pod[1], c_name]
                    )
                    self.retry_container_killing(
                        kill_action,
                        selected_container_pod[0],
                        selected_container_pod[1],
                        c_name,
                        kubecli,
                    )
                    break
            container_pod_list.remove(selected_container_pod)
            killed_count += 1
        logging.info("Scenario " + scenario_name + " successfully injected")
        return killed_container_list

    def retry_container_killing(
        self, kill_action, podname, namespace, container_name, kubecli: KrknKubernetes
    ):
        i = 0
        while i < 5:
            logging.info(
                "Killing container %s in pod %s (ns %s)"
                % (str(container_name), str(podname), str(namespace))
            )
            response = kubecli.exec_cmd_in_pod(
                kill_action, podname, namespace, container_name
            )
            i += 1
            # Blank response means it is done
            if not response:
                break
            elif (
                "unauthorized" in response.lower()
                or "authorization" in response.lower()
            ):
                time.sleep(2)
                continue
            else:
                logging.warning(response)
                continue

    def check_failed_containers(
        self, killed_container_list, wait_time, kubecli: KrknKubernetes
    ):

        container_ready = []
        timer = 0
        while timer <= wait_time:
            for killed_container in killed_container_list:
                # pod namespace contain name
                pod_output = kubecli.get_pod_info(
                    killed_container[0], killed_container[1]
                )

                for container in pod_output.containers:
                    if container.name == killed_container[2]:
                        if container.ready:
                            container_ready.append(killed_container)
            if len(container_ready) != 0:
                for item in container_ready:
                    killed_container_list = killed_container_list.remove(item)
            if killed_container_list is None or len(killed_container_list) == 0:
                return []
            timer += 5
            logging.info("Waiting 5 seconds for containers to become ready")
            time.sleep(5)

        return killed_container_list
