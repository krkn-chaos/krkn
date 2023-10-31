import time
import random
import logging
import kraken.cerberus.setup as cerberus
import kraken.post_actions.actions as post_actions
import yaml
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.utils.functions import get_yaml_item_value, log_exception


def delete_objects(kubecli, namespace):

    services = delete_all_services_namespace(kubecli, namespace)
    daemonsets = delete_all_daemonset_namespace(kubecli, namespace)
    statefulsets = delete_all_statefulsets_namespace(kubecli, namespace)
    replicasets = delete_all_replicaset_namespace(kubecli, namespace)
    deployments = delete_all_deployment_namespace(kubecli, namespace)

    objects = { "daemonsets": daemonsets,
                "deployments": deployments,
                "replicasets": replicasets,
                "statefulsets": statefulsets,
                "services": services
                }

    return objects


def get_list_running_pods(kubecli: KrknKubernetes, namespace: str):
    running_pods = []
    pods = kubecli.list_pods(namespace)
    for pod in pods:
        pod_status = kubecli.get_pod_info(pod, namespace)
        if pod_status and pod_status.status == "Running":
            running_pods.append(pod)
    logging.info('all running pods ' + str(running_pods))
    return running_pods


def delete_all_deployment_namespace(kubecli: KrknKubernetes, namespace: str):
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


def delete_all_daemonset_namespace(kubecli: KrknKubernetes, namespace: str):
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


def delete_all_statefulsets_namespace(kubecli: KrknKubernetes, namespace: str):
    """
    Delete all the statefulsets in the specified namespace


    :param kubecli: krkn kubernetes python package
    :param namespace: namespace
    """
    try:
        statefulsets = kubecli.get_all_statefulset(namespace)
        for statefulset in statefulsets:
            logging.info("Deleting statefulsets" + statefulsets)
            kubecli.delete_statefulset(statefulset, namespace)
    except Exception as e:
        logging.error(
            "Exception when calling delete_all_statefulsets_namespace: %s\n",
            str(e),
        )
        raise e

    return statefulsets


def delete_all_replicaset_namespace(kubecli: KrknKubernetes, namespace: str):
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

def delete_all_services_namespace(kubecli: KrknKubernetes, namespace: str):
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


# krkn_lib
def run(
        scenarios_list,
        config,
        wait_duration,
        failed_post_scenarios,
        kubeconfig_path,
        kubecli: KrknKubernetes,
        telemetry: KrknTelemetryKubernetes
) -> (list[str], list[ScenarioTelemetry]):
    scenario_telemetries: list[ScenarioTelemetry] = []
    failed_scenarios = []
    for scenario_config in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = scenario_config[0]
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, scenario_config[0])
        try:
            if len(scenario_config) > 1:
                pre_action_output = post_actions.run(kubeconfig_path, scenario_config[1])
            else:
                pre_action_output = ""
            with open(scenario_config[0], "r") as f:
                scenario_config_yaml = yaml.full_load(f)
                for scenario in scenario_config_yaml["scenarios"]:
                    scenario_namespace = get_yaml_item_value(
                        scenario, "namespace", ""
                    )
                    scenario_label = get_yaml_item_value(
                        scenario, "label_selector", ""
                    )
                    if scenario_namespace is not None and scenario_namespace.strip() != "":
                        if scenario_label is not None and scenario_label.strip() != "":
                            logging.error("You can only have namespace or label set in your namespace scenario")
                            logging.error(
                                "Current scenario config has namespace '%s' and label selector '%s'"
                                % (scenario_namespace, scenario_label)
                            )
                            logging.error(
                                "Please set either namespace to blank ('') or label_selector to blank ('') to continue"
                            )
                            # removed_exit
                            # sys.exit(1)
                            raise RuntimeError()
                    delete_count = get_yaml_item_value(
                        scenario, "delete_count", 1
                    )
                    run_count = get_yaml_item_value(scenario, "runs", 1)
                    run_sleep = get_yaml_item_value(scenario, "sleep", 10)
                    wait_time = get_yaml_item_value(scenario, "wait_time", 30)

                    logging.info(str(scenario_namespace) + str(scenario_label) + str(delete_count) + str(run_count) + str(run_sleep) + str(wait_time))
                    logging.info("done")
                    start_time = int(time.time())
                    for i in range(run_count):
                        killed_namespaces = {}
                        namespaces = kubecli.check_namespaces([scenario_namespace], scenario_label)
                        for j in range(delete_count):
                            if len(namespaces) == 0:
                                logging.error(
                                    "Couldn't delete %s namespaces, not enough namespaces matching %s with label %s"
                                    % (str(run_count), scenario_namespace, str(scenario_label))
                                )
                                # removed_exit
                                # sys.exit(1)
                                raise RuntimeError()
                            selected_namespace = namespaces[random.randint(0, len(namespaces) - 1)]
                            logging.info('Delete objects in selected namespace: ' + selected_namespace )
                            try:
                                # delete all pods in namespace
                                objects = delete_objects(kubecli,selected_namespace)
                                killed_namespaces[selected_namespace] = objects
                                logging.info("Deleted all objects in namespace %s was successful" % str(selected_namespace))
                            except Exception as e:
                                logging.info("Delete all objects in namespace %s was unsuccessful" % str(selected_namespace))
                                logging.info("Namespace action error: " + str(e))
                                raise RuntimeError()
                            namespaces.remove(selected_namespace)
                            logging.info("Waiting %s seconds between namespace deletions" % str(run_sleep))
                            time.sleep(run_sleep)

                        logging.info("Waiting for the specified duration: %s" % wait_duration)
                        time.sleep(wait_duration)
                        if len(scenario_config) > 1:
                            try:
                                failed_post_scenarios = post_actions.check_recovery(
                                    kubeconfig_path, scenario_config, failed_post_scenarios, pre_action_output
                                )
                            except Exception as e:
                                logging.error("Failed to run post action checks: %s" % e)
                                # removed_exit
                                # sys.exit(1)
                                raise RuntimeError()
                        else:
                            failed_post_scenarios = check_all_running_deployment(killed_namespaces, wait_time, kubecli)

                    end_time = int(time.time())
                    cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)
        except (Exception, RuntimeError):
            scenario_telemetry.exitStatus = 1
            failed_scenarios.append(scenario_config[0])
            log_exception(scenario_config[0])
        else:
            scenario_telemetry.exitStatus = 0
        scenario_telemetry.endTimeStamp = time.time()
        scenario_telemetries.append(scenario_telemetry)
    return failed_scenarios, scenario_telemetries


def check_all_running_pods(kubecli: KrknKubernetes, namespace_name, wait_time):

    timer = 0
    while timer < wait_time:
        pod_list = kubecli.list_pods(namespace_name)
        pods_running = 0
        for pod in pod_list:
            pod_info = kubecli.get_pod_info(pod, namespace_name)
            if pod_info.status != "Running" and pod_info.status != "Succeeded":
                logging.info("Pods %s still not running or completed" % pod_info.name)
                break
            pods_running += 1
        if len(pod_list) == pods_running:
            break
        timer += 5
        time.sleep(5)
        logging.info("Waiting 5 seconds for pods to become active")

# krkn_lib
def check_all_running_deployment(killed_namespaces, wait_time, kubecli: KrknKubernetes):

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
                logging.info("Wait for pods to become running for namespace: " + namespace_name)
                check_all_running_pods(kubecli, namespace_name, wait_time)
                still_missing_ns.pop(namespace_name)
        killed_namespaces = still_missing_ns
        if len(killed_namespaces.keys()) == 0:
            return []

        timer += 10
        time.sleep(10)
        logging.info("Waiting 10 seconds for objects in namespaces to become active")

    logging.error("Objects are still not ready after waiting " + str(wait_time) + "seconds")
    logging.error("Non active namespaces " + str(killed_namespaces))
    return killed_namespaces
