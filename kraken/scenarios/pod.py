import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Dict, List

from kraken.scenarios import base
from kraken.scenarios.base import ScenarioConfig, Scenario
from kraken.scenarios.kube import Client, Pod, NotFoundException


@dataclass
class PodScenarioConfig(ScenarioConfig):
    """
    PodScenarioConfig is a configuration structure specific to pod scenarios. It describes which pod from which
    namespace(s) to select for killing and how many pods to kill.
    """

    name_pattern: str
    namespace_pattern: str
    label_selector: str
    kill: int

    def from_dict(self, data: Dict) -> None:
        self.name_pattern = data.get("name_pattern")
        self.namespace_pattern = data.get("namespace_pattern")
        self.label_selector = data.get("label_selector")
        self.kill = data.get("kill")

    def validate(self) -> None:
        re.compile(self.name_pattern)
        re.compile(self.namespace_pattern)
        if self.kill < 1:
            raise Exception("Invalid value for 'kill': %d" % self.kill)

    def namespace_regexp(self) -> re.Pattern:
        return re.compile(self.namespace_pattern)

    def name_regexp(self) -> re.Pattern:
        return re.compile(self.name_pattern)


class PodScenario(Scenario[PodScenarioConfig]):
    """
    PodScenario is a scenario that tests the stability of a Kubernetes cluster by killing one or more pods based on the
    PodScenarioConfig.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def create_config(self) -> PodScenarioConfig:
        return PodScenarioConfig(
            name_pattern=".*",
            namespace_pattern=".*",
            label_selector="",
            kill=1,
        )

    def run(self, kube: Client, config: PodScenarioConfig):
        pod_candidates: List[Pod] = []
        namespace_re = config.namespace_regexp()
        name_re = config.name_regexp()

        self.logger.info("Listing all pods to determine viable pods to kill...")
        for pod in kube.list_all_pods(label_selector=config.label_selector):
            if namespace_re.match(pod.namespace) and name_re.match(pod.name):
                pod_candidates.append(pod)
        random.shuffle(pod_candidates)
        removed_pod: List[Pod] = []
        pods_to_kill = min(config.kill, len(pod_candidates))

        self.logger.info("Killing %d pods...", pods_to_kill)
        for i in range(pods_to_kill):
            pod = pod_candidates[i]
            self.logger.info("Killing pod %s...", pod.name)
            removed_pod.append(pod)
            kube.remove_pod(pod.name, pod.namespace)

        self.logger.info("Waiting for pods to be removed...")
        for i in range(60):
            time.sleep(1)
            for pod in removed_pod:
                try:
                    kube.get_pod(pod.name, pod.namespace)
                    self.logger.info("Pod %s still exists...", pod.name)
                except NotFoundException:
                    self.logger.info("Pod %s is now removed.", pod.name)
                    removed_pod.remove(pod)
            if len(removed_pod) == 0:
                self.logger.info("All pods removed, pod scenario complete.")
                return

        self.logger.warning("Timeout waiting for pods to be removed.")
        raise base.TimeoutException("Timeout while waiting for pods to be removed.")
