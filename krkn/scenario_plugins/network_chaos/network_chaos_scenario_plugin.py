import logging
import os
import random
import time

import yaml
from jinja2 import Environment, FileSystemLoader
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, log_exception

from krkn import cerberus, utils
from krkn.scenario_plugins.node_actions import common_node_functions
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class NetworkChaosScenarioPlugin(AbstractScenarioPlugin):
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
                param_lst = ["latency", "loss", "bandwidth"]
                test_config = yaml.safe_load(file)
                test_dict = test_config["network_chaos"]
                test_duration = int(get_yaml_item_value(test_dict, "duration", 300))
                test_interface = get_yaml_item_value(test_dict, "interfaces", [])
                test_node = get_yaml_item_value(test_dict, "node_name", "")
                test_node_label = get_yaml_item_value(
                    test_dict, "label_selector", "node-role.kubernetes.io/master"
                )
                test_execution = get_yaml_item_value(test_dict, "execution", "serial")
                test_instance_count = get_yaml_item_value(
                    test_dict, "instance_count", 1
                )
                test_egress = get_yaml_item_value(
                    test_dict, "egress", {"bandwidth": "100mbit"}
                )

                if test_node:
                    node_name_list = test_node.split(",")
                    nodelst = common_node_functions.get_node_by_name(node_name_list, lib_telemetry.get_lib_kubernetes())
                else:
                    nodelst = common_node_functions.get_node(
                        test_node_label, test_instance_count, lib_telemetry.get_lib_kubernetes()
                    )
                file_loader = FileSystemLoader(
                    os.path.abspath(os.path.dirname(__file__))
                )
                env = Environment(loader=file_loader, autoescape=True)
                pod_template = env.get_template("pod.j2")
                test_interface = self.verify_interface(
                    test_interface,
                    nodelst,
                    pod_template,
                    lib_telemetry.get_lib_kubernetes(),
                )
                joblst = []
                egress_lst = [i for i in param_lst if i in test_egress]
                chaos_config = {
                    "network_chaos": {
                        "duration": test_duration,
                        "interfaces": test_interface,
                        "node_name": ",".join(nodelst),
                        "execution": test_execution,
                        "instance_count": test_instance_count,
                        "egress": test_egress,
                    }
                }
                logging.info(
                    "Executing network chaos with config \n %s"
                    % yaml.dump(chaos_config)
                )
                job_template = env.get_template("job.j2")
                try:
                    for i in egress_lst:
                        for node in nodelst:
                            exec_cmd = self.get_egress_cmd(
                                test_execution,
                                test_interface,
                                i,
                                test_dict["egress"],
                                duration=test_duration,
                            )
                            logging.info("Executing %s on node %s" % (exec_cmd, node))
                            job_body = yaml.safe_load(
                                job_template.render(
                                    jobname=i + str(hash(node))[:5],
                                    nodename=node,
                                    cmd=exec_cmd,
                                )
                            )
                            joblst.append(job_body["metadata"]["name"])
                            api_response = (
                                lib_telemetry.get_lib_kubernetes().create_job(job_body)
                            )
                            if api_response is None:
                                logging.error(
                                    "NetworkChaosScenarioPlugin Error creating job"
                                )
                                return 1
                        if test_execution == "serial":
                            logging.info("Waiting for serial job to finish")
                            start_time = int(time.time())
                            self.wait_for_job(
                                joblst[:],
                                lib_telemetry.get_lib_kubernetes(),
                                test_duration + 300,
                            )

                            end_time = int(time.time())
                            cerberus.publish_kraken_status(
                                krkn_config,
                                None,
                                start_time,
                                end_time,
                            )
                        if test_execution == "parallel":
                            break
                    if test_execution == "parallel":
                        logging.info("Waiting for parallel job to finish")
                        start_time = int(time.time())
                        self.wait_for_job(
                            joblst[:],
                            lib_telemetry.get_lib_kubernetes(),
                            test_duration + 300,
                        )
                        end_time = int(time.time())
                        cerberus.publish_kraken_status(
                            krkn_config, [], start_time, end_time
                        )
                except Exception as e:
                    logging.error(
                        "NetworkChaosScenarioPlugin exiting due to Exception %s" % e
                    )
                    return 1
                finally:
                    logging.info("Deleting jobs")
                    self.delete_job(joblst[:], lib_telemetry.get_lib_kubernetes())
        except (RuntimeError, Exception) as e:
            logging.error(
                "NetworkChaosScenarioPlugin exiting due to Exception %s" % e
            )
            scenario_telemetry.exit_status = 1
            return 1
        else:
            return 0

    def verify_interface(
        self, test_interface, nodelst, template, kubecli: KrknKubernetes
    ):
        pod_index = random.randint(0, len(nodelst) - 1)
        pod_body = yaml.safe_load(template.render(nodename=nodelst[pod_index]))
        logging.info("Creating pod to query interface on node %s" % nodelst[pod_index])
        kubecli.create_pod(pod_body, "default", 300)
        try:
            if test_interface == []:
                cmd = "ip r | grep default | awk '/default/ {print $5}'"
                output = kubecli.exec_cmd_in_pod(cmd, "fedtools", "default")
                test_interface = [output.replace("\n", "")]
            else:
                cmd = "ip -br addr show|awk -v ORS=',' '{print $1}'"
                output = kubecli.exec_cmd_in_pod(cmd, "fedtools", "default")
                interface_lst = output[:-1].split(",")
                for interface in test_interface:
                    if interface not in interface_lst:
                        logging.error(
                            "NetworkChaosScenarioPlugin Interface %s not found in node %s interface list %s"
                            % (interface, nodelst[pod_index], interface_lst)
                        )
                        raise RuntimeError()
            return test_interface
        finally:
            logging.info("Deleteing pod to query interface on node")
            kubecli.delete_pod("fedtools", "default")

    # krkn_lib
    def get_job_pods(self, api_response, kubecli: KrknKubernetes):
        controllerUid = api_response.metadata.labels["controller-uid"]
        pod_label_selector = "controller-uid=" + controllerUid
        pods_list = kubecli.list_pods(
            label_selector=pod_label_selector, namespace="default"
        )
        return pods_list[0]

    # krkn_lib
    def wait_for_job(self, joblst, kubecli: KrknKubernetes, timeout=300):
        waittime = time.time() + timeout
        count = 0
        joblen = len(joblst)
        while count != joblen:
            for jobname in joblst:
                try:
                    api_response = kubecli.get_job_status(jobname, namespace="default")
                    if (
                        api_response.status.succeeded is not None
                        or api_response.status.failed is not None
                    ):
                        count += 1
                        joblst.remove(jobname)
                except Exception:
                    logging.warning("Exception in getting job status")
                if time.time() > waittime:
                    raise Exception("Starting pod failed")
                time.sleep(5)

    # krkn_lib
    def delete_job(self, joblst, kubecli: KrknKubernetes):
        for jobname in joblst:
            try:
                api_response = kubecli.get_job_status(jobname, namespace="default")
                if api_response.status.failed is not None:
                    pod_name = self.get_job_pods(api_response, kubecli)
                    pod_stat = kubecli.read_pod(name=pod_name, namespace="default")
                    logging.error(
                        f"NetworkChaosScenarioPlugin {pod_stat.status.container_statuses}"
                    )
                    pod_log_response = kubecli.get_pod_log(
                        name=pod_name, namespace="default"
                    )
                    pod_log = pod_log_response.data.decode("utf-8")
                    logging.error(pod_log)
            except Exception:
                logging.warning("Exception in getting job status")
            kubecli.delete_job(name=jobname, namespace="default")

    def get_egress_cmd(self, execution, test_interface, mod, vallst, duration=30):
        tc_set = tc_unset = tc_ls = ""
        param_map = {"latency": "delay", "loss": "loss", "bandwidth": "rate"}
        for i in test_interface:
            tc_set = "{0} tc qdisc add dev {1} root netem".format(tc_set, i)
            tc_unset = "{0} tc qdisc del dev {1} root ;".format(tc_unset, i)
            tc_ls = "{0} tc qdisc ls dev {1} ;".format(tc_ls, i)
            if execution == "parallel":
                for val in vallst.keys():
                    tc_set += " {0} {1} ".format(param_map[val], vallst[val])
                tc_set += ";"
            else:
                tc_set += " {0} {1} ;".format(param_map[mod], vallst[mod])
        exec_cmd = "{0} {1} sleep {2};{3} sleep 20;{4}".format(
            tc_set, tc_ls, duration, tc_unset, tc_ls
        )
        return exec_cmd

    def get_scenario_types(self) -> list[str]:
        return ["network_chaos_scenarios"]
