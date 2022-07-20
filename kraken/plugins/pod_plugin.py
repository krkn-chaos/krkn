#!/usr/bin/env python
import re
import sys
import time
import typing
from dataclasses import dataclass, field
import random
from datetime import datetime
from traceback import format_exc

from kubernetes import config, client
from kubernetes.client import V1PodList, V1Pod, ApiException, V1DeleteOptions
from arcaflow_plugin_sdk import validation, plugin, schema


def setup_kubernetes(kubeconfig_path):
    if kubeconfig_path is None:
        kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
    kubeconfig = config.kube_config.KubeConfigMerger(kubeconfig_path)

    if kubeconfig.config is None:
        raise Exception(
            'Invalid kube-config file: %s. '
            'No configuration found.' % kubeconfig_path
        )
    loader = config.kube_config.KubeConfigLoader(
        config_dict=kubeconfig.config,
    )
    client_config = client.Configuration()
    loader.load_and_set(client_config)
    return client.ApiClient(configuration=client_config)


def _find_pods(core_v1, label_selector, name_pattern, namespace_pattern):
    pods: typing.List[V1Pod] = []
    _continue = None
    finished = False
    while not finished:
        pod_response: V1PodList = core_v1.list_pod_for_all_namespaces(
            watch=False,
            label_selector=label_selector
        )
        for pod in pod_response.items:
            pod: V1Pod
            if (name_pattern is None or name_pattern.match(pod.metadata.name)) and \
                    namespace_pattern.match(pod.metadata.namespace):
                pods.append(pod)
        _continue = pod_response.metadata._continue
        if _continue is None:
            finished = True
    return pods


@dataclass
class Pod:
    namespace: str
    name: str


@dataclass
class PodKillSuccessOutput:
    pods: typing.Dict[int, Pod] = field(metadata={
        "name": "Pods removed",
        "description": "Map between timestamps and the pods removed. The timestamp is provided in nanoseconds."
    })


@dataclass
class PodWaitSuccessOutput:
    pods: typing.List[Pod] = field(metadata={
        "name": "Pods",
        "description": "List of pods that have been found to run."
    })


@dataclass
class PodErrorOutput:
    error: str


@dataclass
class KillPodConfig:
    """
    This is a configuration structure specific to pod kill  scenario. It describes which pod from which
    namespace(s) to select for killing and how many pods to kill.
    """

    namespace_pattern: re.Pattern = field(metadata={
        "name": "Namespace pattern",
        "description": "Regular expression for target pod namespaces."
    })

    name_pattern: typing.Annotated[
        typing.Optional[re.Pattern],
        validation.required_if_not("label_selector")
    ] = field(default=None, metadata={
        "name": "Name pattern",
        "description": "Regular expression for target pods. Required if label_selector is not set."
    })

    kill: typing.Annotated[int, validation.min(1)] = field(
        default=1,
        metadata={"name": "Number of pods to kill", "description": "How many pods should we attempt to kill?"}
    )

    label_selector: typing.Annotated[
        typing.Optional[str],
        validation.min(1),
        validation.required_if_not("name_pattern")
    ] = field(default=None, metadata={
        "name": "Label selector",
        "description": "Kubernetes label selector for the target pods. Required if name_pattern is not set.\n"
                       "See https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/ for details."
    })

    kubeconfig_path: typing.Optional[str] = field(default=None, metadata={
        "name": "Kubeconfig path",
        "description": "Path to your Kubeconfig file. Defaults to ~/.kube/config.\n"
                       "See https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/ for "
                       "details."
    })

    timeout: int = field(default=180, metadata={
        "name": "Timeout",
        "description": "Timeout to wait for the target pod(s) to be removed in seconds."
    })

    backoff: int = field(default=1, metadata={
        "name": "Backoff",
        "description": "How many seconds to wait between checks for the target pod status."
    })


@plugin.step(
    "kill-pods",
    "Kill pods",
    "Kill pods as specified by parameters",
    {"success": PodKillSuccessOutput, "error": PodErrorOutput}
)
def kill_pods(cfg: KillPodConfig) -> typing.Tuple[str, typing.Union[PodKillSuccessOutput, PodErrorOutput]]:
    try:
        with setup_kubernetes(None) as cli:
            core_v1 = client.CoreV1Api(cli)

            # region Select target pods
            pods = _find_pods(core_v1, cfg.label_selector, cfg.name_pattern, cfg.namespace_pattern)
            if len(pods) < cfg.kill:
                return "error", PodErrorOutput(
                    "Not enough pods match the criteria, expected {} but found only {} pods".format(cfg.kill, len(pods))
                )
            random.shuffle(pods)
            # endregion

            # region Remove pods
            killed_pods: typing.Dict[int, Pod] = {}
            watch_pods: typing.List[Pod] = []
            for i in range(cfg.kill):
                pod = pods[i]
                core_v1.delete_namespaced_pod(pod.metadata.name, pod.metadata.namespace, body=V1DeleteOptions(
                    grace_period_seconds=0,
                ))
                p = Pod(
                    pod.metadata.namespace,
                    pod.metadata.name
                )
                killed_pods[int(time.time_ns())] = p
                watch_pods.append(p)
            # endregion

            # region Wait for pods to be removed
            start_time = time.time()
            while len(watch_pods) > 0:
                time.sleep(cfg.backoff)
                new_watch_pods: typing.List[Pod] = []
                for p in watch_pods:
                    try:
                        read_pod = core_v1.read_namespaced_pod(p.name, p.namespace)
                        new_watch_pods.append(p)
                    except ApiException as e:
                        if e.status != 404:
                            raise
                watch_pods = new_watch_pods
                current_time = time.time()
                if current_time - start_time > cfg.timeout:
                    return "error", PodErrorOutput("Timeout while waiting for pods to be removed.")
            return "success", PodKillSuccessOutput(killed_pods)
            # endregion
    except Exception:
        return "error", PodErrorOutput(
            format_exc()
        )


@dataclass
class WaitForPodsConfig:
    """
    WaitForPodsConfig is a configuration structure for wait-for-pod steps.
    """

    namespace_pattern: re.Pattern

    name_pattern: typing.Annotated[
        typing.Optional[re.Pattern],
        validation.required_if_not("label_selector")
    ] = None

    label_selector: typing.Annotated[
        typing.Optional[str],
        validation.min(1),
        validation.required_if_not("name_pattern")
    ] = None

    count: typing.Annotated[int, validation.min(1)] = field(
        default=1,
        metadata={"name": "Pod count", "description": "Wait for at least this many pods to exist"}
    )

    timeout: typing.Annotated[int, validation.min(1)] = field(
        default=180,
        metadata={"name": "Timeout", "description": "How many seconds to wait for?"}
    )

    backoff: int = field(default=1, metadata={
        "name": "Backoff",
        "description": "How many seconds to wait between checks for the target pod status."
    })

    kubeconfig_path: typing.Optional[str] = None


@plugin.step(
    "wait-for-pods",
    "Wait for pods",
    "Wait for the specified number of pods to be present",
    {"success": PodWaitSuccessOutput, "error": PodErrorOutput}
)
def wait_for_pods(cfg: WaitForPodsConfig) -> typing.Tuple[str, typing.Union[PodWaitSuccessOutput, PodErrorOutput]]:
    try:
        with setup_kubernetes(None) as cli:
            core_v1 = client.CoreV1Api(cli)

            timeout = False
            start_time = datetime.now()
            while not timeout:
                pods = _find_pods(core_v1, cfg.label_selector, cfg.name_pattern, cfg.namespace_pattern)
                if len(pods) >= cfg.count:
                    return "success", \
                           PodWaitSuccessOutput(list(map(lambda p: Pod(p.metadata.namespace, p.metadata.name), pods)))

                time.sleep(cfg.backoff)

                now_time = datetime.now()

                time_diff = now_time - start_time
                if time_diff.seconds > cfg.timeout:
                    return "error", PodErrorOutput(
                        "timeout while waiting for pods to come up"
                    )
    except Exception:
        return "error", PodErrorOutput(
            format_exc()
        )


if __name__ == "__main__":
    sys.exit(plugin.run(plugin.build_schema(
        kill_pods,
        wait_for_pods,
    )))
