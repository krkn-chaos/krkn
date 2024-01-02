import time
import arcaflow
import os
import yaml
import logging
from pathlib import Path
from typing import List
from .context_auth import ContextAuth
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry


def run(scenarios_list: List[str], kubeconfig_path: str, telemetry: KrknTelemetryKubernetes) -> (list[str], list[ScenarioTelemetry]):
    scenario_telemetries: list[ScenarioTelemetry] = []
    failed_post_scenarios = []
    for scenario in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = scenario
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry,scenario)
        engine_args = build_args(scenario)
        status_code = run_workflow(engine_args, kubeconfig_path)
        scenario_telemetry.endTimeStamp = time.time()
        scenario_telemetry.exitStatus = status_code
        scenario_telemetries.append(scenario_telemetry)
        if status_code != 0:
            failed_post_scenarios.append(scenario)
    return failed_post_scenarios, scenario_telemetries


def run_workflow(engine_args: arcaflow.EngineArgs, kubeconfig_path: str) -> int:
    set_arca_kubeconfig(engine_args, kubeconfig_path)
    exit_status = arcaflow.run(engine_args)
    return exit_status


def build_args(input_file: str) -> arcaflow.EngineArgs:
    """sets the kubeconfig parsed by setArcaKubeConfig as an input to the arcaflow workflow"""
    context = Path(input_file).parent
    workflow = "{}/workflow.yaml".format(context)
    config = "{}/config.yaml".format(context)
    if not os.path.exists(context):
        raise Exception(
            "context folder for arcaflow workflow not found: {}".format(
                context)
        )
    if not os.path.exists(input_file):
        raise Exception(
            "input file for arcaflow workflow not found: {}".format(input_file))
    if not os.path.exists(workflow):
        raise Exception(
            "workflow file for arcaflow workflow not found: {}".format(
                workflow)
        )
    if not os.path.exists(config):
        raise Exception(
            "configuration file for arcaflow workflow not found: {}".format(
                config)
        )

    engine_args = arcaflow.EngineArgs()
    engine_args.context = context
    engine_args.config = config
    engine_args.input = input_file
    return engine_args


def set_arca_kubeconfig(engine_args: arcaflow.EngineArgs, kubeconfig_path: str):

    context_auth = ContextAuth()
    if not os.path.exists(kubeconfig_path):
        raise Exception("kubeconfig not found in {}".format(kubeconfig_path))

    with open(kubeconfig_path, "r") as stream:
        try:
            kubeconfig = yaml.safe_load(stream)
            context_auth.fetch_auth_data(kubeconfig)
        except Exception as e:
            logging.error("impossible to read kubeconfig file in: {}".format(
                    kubeconfig_path))
            raise e

    kubeconfig_str = set_kubeconfig_auth(kubeconfig, context_auth)

    with open(engine_args.input, "r") as stream:
        input_file = yaml.safe_load(stream)
        if "input_list" in input_file and isinstance(input_file["input_list"],list):
            for index, _ in enumerate(input_file["input_list"]):
                if isinstance(input_file["input_list"][index], dict):
                    input_file["input_list"][index]["kubeconfig"] = kubeconfig_str
        else:
            input_file["kubeconfig"] = kubeconfig_str
        stream.close()
    with open(engine_args.input, "w") as stream:
        yaml.safe_dump(input_file, stream)

    with open(engine_args.config, "r") as stream:
        config_file = yaml.safe_load(stream)
    if config_file["deployers"]["image"]["deployer_name"] == "kubernetes":
        kube_connection = set_kubernetes_deployer_auth(config_file["deployers"]["image"]["connection"], context_auth)
        config_file["deployers"]["image"]["connection"]=kube_connection
        with open(engine_args.config, "w") as stream:
            yaml.safe_dump(config_file, stream,explicit_start=True, width=4096)


def set_kubernetes_deployer_auth(deployer: any, context_auth: ContextAuth) -> any:
    if context_auth.clusterHost is not None :
        deployer["host"] = context_auth.clusterHost
    if context_auth.clientCertificateData is not None :
        deployer["cert"] = context_auth.clientCertificateData
    if context_auth.clientKeyData is not None:
        deployer["key"] = context_auth.clientKeyData
    if context_auth.clusterCertificateData is not None:
        deployer["cacert"] = context_auth.clusterCertificateData
    if context_auth.username is not None:
        deployer["username"] = context_auth.username
    if context_auth.password is not None:
        deployer["password"] = context_auth.password
    if context_auth.bearerToken is not None:
        deployer["bearerToken"] = context_auth.bearerToken
    return deployer


def set_kubeconfig_auth(kubeconfig: any, context_auth: ContextAuth) -> str:
    """
    Builds an arcaflow-compatible kubeconfig representation and returns it as a string.
    In order to run arcaflow plugins in kubernetes/openshift the kubeconfig must contain client certificate/key
    and server certificate base64 encoded within the kubeconfig file itself in *-data fields. That is not always the
    case, infact kubeconfig may contain filesystem paths to those files, this function builds an arcaflow-compatible
    kubeconfig file and returns it as a string that can be safely included in input.yaml 
    """

    if "current-context" not in kubeconfig.keys():
        raise Exception(
            "invalid kubeconfig file, impossible to determine current-context"
        )
    user_id = None
    cluster_id = None
    user_name = None
    cluster_name = None
    current_context = kubeconfig["current-context"]
    for context in kubeconfig["contexts"]:
        if context["name"] == current_context:
            user_name = context["context"]["user"]
            cluster_name = context["context"]["cluster"]
    if user_name is None:
        raise Exception(
            "user not set for context {} in kubeconfig file".format(current_context)
        )
    if cluster_name is None:
        raise Exception(
            "cluster not set for context {} in kubeconfig file".format(current_context)
        )

    for index, user in enumerate(kubeconfig["users"]):
        if user["name"] == user_name:
            user_id = index
    for index, cluster in enumerate(kubeconfig["clusters"]):
        if cluster["name"] == cluster_name:
            cluster_id = index

    if cluster_id is None:
        raise Exception(
            "no cluster {} found in kubeconfig users".format(cluster_name)
        )
    if "client-certificate" in kubeconfig["users"][user_id]["user"]:
        kubeconfig["users"][user_id]["user"]["client-certificate-data"] = context_auth.clientCertificateDataBase64
        del kubeconfig["users"][user_id]["user"]["client-certificate"]

    if "client-key" in kubeconfig["users"][user_id]["user"]:
        kubeconfig["users"][user_id]["user"]["client-key-data"] = context_auth.clientKeyDataBase64
        del kubeconfig["users"][user_id]["user"]["client-key"]

    if "certificate-authority" in kubeconfig["clusters"][cluster_id]["cluster"]:
        kubeconfig["clusters"][cluster_id]["cluster"]["certificate-authority-data"] = context_auth.clusterCertificateDataBase64
        del kubeconfig["clusters"][cluster_id]["cluster"]["certificate-authority"]
    kubeconfig_str = yaml.dump(kubeconfig)
    return kubeconfig_str
