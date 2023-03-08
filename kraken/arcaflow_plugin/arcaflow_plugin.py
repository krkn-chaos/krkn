import arcaflow
import os
import yaml
import base64
from pathlib import Path
from typing import List


def run(scenarios_list: List[str], kubeconfig_path: str):
    for scenario in scenarios_list:
        engineArgs = buildArgs(scenario)
        runWorkflow(engineArgs, kubeconfig_path)


def runWorkflow(engineArgs: arcaflow.EngineArgs, kubeconfig_path: str):
    setArcaKubeConfig(engineArgs, kubeconfig_path)
    arcaflow.run(engineArgs)


def buildArgs(input: str) -> arcaflow.EngineArgs:
    """sets the kubeconfig parsed by setArcaKubeConfig as an input to the arcaflow workflow"""
    context = Path(input).parent
    workflow = "{}/workflow.yaml".format(context)
    config = "{}/config.yaml".format(context)
    if os.path.exists(context) == False:
        raise Exception(
            "context folder for arcaflow workflow not found: {}".format(
                context)
        )
    if os.path.exists(input) == False:
        raise Exception(
            "input file for arcaflow workflow not found: {}".format(input))
    if os.path.exists(workflow) == False:
        raise Exception(
            "workflow file for arcaflow workflow not found: {}".format(
                workflow)
        )
    if os.path.exists(config) == False:
        raise Exception(
            "configuration file for arcaflow workflow not found: {}".format(
                config)
        )

    engineArgs = arcaflow.EngineArgs()
    engineArgs.context = context
    engineArgs.config = config
    engineArgs.input = input
    return engineArgs


def setArcaKubeConfig(engineArgs: arcaflow.EngineArgs, kubeconfig_path: str):
    kubeconfig_str = buildArcaKubeConfig(kubeconfig_path)
    with open(engineArgs.input, "r") as stream:
        input = yaml.safe_load(stream)
        input["kubeconfig"] = kubeconfig_str
        stream.close()
    with open(engineArgs.input, "w") as stream:
        yaml.safe_dump(input, stream)


def buildArcaKubeConfig(kubeconfig_path: str) -> str:
    """
    Builds an arcaflow-compatible kubeconfig representation and returns it as a string.
    In order to run arcaflow plugins in kubernetes/openshift the kubeconfig must contain client certificate/key
    and server certificate base64 encoded within the kubeconfig file itself in *-data fields. That is not always the
    case, infact kubeconfig may contain filesystem paths to those files, this function builds an arcaflow-compatible
    kubeconfig file and returns it as a string that can be safely included in input.yaml 
    """
    if os.path.exists(kubeconfig_path) == False:
        raise Exception("kubeconfig not found in {}".format(kubeconfig_path))

    with open(kubeconfig_path, "r") as stream:
        try:
            kubeconfig = yaml.safe_load(stream)
        except:
            raise Exception(
                "impossible to read kubeconfig file in: {}".format(
                    kubeconfig_path)
            )

    if "current-context" not in kubeconfig.keys():
        raise Exception(
            "invalid kubeconfig file, impossible to determine current-context"
        )
    userId = None
    clusterId = None
    userName = None
    clusterName = None
    currentContext = kubeconfig["current-context"]
    for context in kubeconfig["contexts"]:
        if context["name"] == currentContext:
            userName = context["context"]["user"]
            clusterName = context["context"]["cluster"]
    if userName is None:
        raise Exception(
            "user not set for context {} in kubeconfig file".format(context)
        )
    if clusterName is None:
        raise Exception(
            "cluster not set for context {} in kubeconfig file".format(context)
        )

    for index, user in enumerate(kubeconfig["users"]):
        if user["name"] == userName:
            userId = index
    for index, cluster in enumerate(kubeconfig["clusters"]):
        if cluster["name"] == clusterName:
            clusterId = index

    if userId is None:
        raise Exception(
            "no user {} found in kubeconfig users".format(userName)
        )
    if clusterId is None:
        raise Exception(
            "no cluster {} found in kubeconfig users".format(cluster)
        )
    if "client-certificate" in kubeconfig["users"][userId]["user"]:
        file = kubeconfig["users"][userId]["user"]["client-certificate"]
        if (os.path.exists(file) == False):
            raise Exception("user certificate not found {} ".format(file))
        with open(file, "rb") as file_stream:
            encoded_file = base64.b64encode(file_stream.read()).decode("utf-8")
        kubeconfig["users"][userId]["user"]["client-certificate-data"] = encoded_file
        del kubeconfig["users"][userId]["user"]["client-certificate"]

    if "client-key" in kubeconfig["users"][userId]["user"]:
        file = kubeconfig["users"][userId]["user"]["client-key"]
        if (os.path.exists(file) == False):
            raise Exception("user key not found: {} ".format(file))
        with open(file, "rb") as file_stream:
            encoded_file = base64.b64encode(file_stream.read()).decode("utf-8")
        kubeconfig["users"][userId]["user"]["client-key-data"] = encoded_file
        del kubeconfig["users"][userId]["user"]["client-key"]

    if "certificate-authority" in kubeconfig["clusters"][clusterId]["cluster"]:
        file = kubeconfig["clusters"][clusterId]["cluster"]["certificate-authority"]
        if (os.path.exists(file) == False):
            raise Exception("cluster certificate not found: {}".format(file))
        with open(file, "rb") as file_stream:
            encoded_file = base64.b64encode(file_stream.read()).decode("utf-8")
        kubeconfig["clusters"][clusterId]["cluster"]["certificate-authority-data"] = encoded_file
        del kubeconfig["clusters"][clusterId]["cluster"]["certificate-authority"]
    kubeconfig_str = yaml.dump(kubeconfig)
    return kubeconfig_str
