import queue
import re
import time
from fnmatch import fnmatch
from typing import List, Union

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_random_string
from krkn.scenario_plugins.network_chaos_ng.models import (
    BaseNetworkChaosConfig,
    NetworkFilterConfig,
    NetworkChaosScenarioType,
)
from krkn.scenario_plugins.network_chaos_ng.modules.abstract_network_chaos_module import (
    AbstractNetworkChaosModule,
)
from krkn.scenario_plugins.network_chaos_ng.modules.utils import log_info

from krkn.scenario_plugins.network_chaos_ng.modules.utils_network_filter import (
    deploy_network_filter_pod,
    apply_network_rules,
    clean_network_rules,
    generate_rules,
    get_default_interface,
)


class NodeNetworkFilterModule(AbstractNetworkChaosModule):
    config: NetworkFilterConfig
    kubecli: KrknTelemetryOpenshift

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = False
        if error_queue:
            parallel = True
        try:
            log_info(
                f"creating workload to filter node {target} network"
                f"ports {','.join([str(port) for port in self.config.ports])}, "
                f"ingress:{str(self.config.ingress)}, "
                f"egress:{str(self.config.egress)}",
                parallel,
                target,
            )

            pod_name = f"node-filter-{get_random_string(5)}"
            deploy_network_filter_pod(
                self.config,
                target,
                pod_name,
                self.kubecli.get_lib_kubernetes(),
            )

            if len(self.config.interfaces) == 0:
                interfaces = [
                    get_default_interface(
                        pod_name,
                        self.config.namespace,
                        self.kubecli.get_lib_kubernetes(),
                    )
                ]

                log_info(
                    f"detected default interface {interfaces[0]}", parallel, target
                )

            else:
                interfaces = self.config.interfaces

            input_rules, output_rules = generate_rules(interfaces, self.config)

            apply_network_rules(
                self.kubecli.get_lib_kubernetes(),
                input_rules,
                output_rules,
                pod_name,
                self.config.namespace,
                parallel,
                target,
            )

            log_info(
                f"waiting {self.config.test_duration} seconds before removing the iptables rules",
                parallel,
                target,
            )

            time.sleep(self.config.test_duration)

            log_info("removing iptables rules", parallel, target)

            clean_network_rules(
                self.kubecli.get_lib_kubernetes(),
                input_rules,
                output_rules,
                pod_name,
                self.config.namespace,
            )

            self.kubecli.get_lib_kubernetes().delete_pod(
                pod_name, self.config.namespace
            )

        except Exception as e:
            if error_queue is None:
                raise e
            else:
                error_queue.put(str(e))

    def __init__(self, config: NetworkFilterConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def get_config(self) -> (NetworkChaosScenarioType, BaseNetworkChaosConfig):
        return NetworkChaosScenarioType.Node, self.config

    def get_targets(self) -> list[str]:
        kube = self.kubecli.get_lib_kubernetes()
        candidates: list[str] = []

        if self.base_network_config.label_selector:
            candidates = kube.list_nodes(self.base_network_config.label_selector)
            if not candidates:
                raise Exception(
                    f"no nodes found for selector {self.base_network_config.label_selector}"
                )

        else:
            node_info = kube.list_nodes()
            if not node_info:
                raise Exception("no nodes found in the cluster, aborting")

            parsed_targets = self._parse_target_spec(node_info)
            if not parsed_targets:
                raise Exception("target specification produced an empty node set")

            missing = [node for node in parsed_targets if node not in node_info]
            if missing:
                raise Exception(f"nodes {','.join(missing)} not found, aborting")

            candidates = parsed_targets

        if self.config.exclude_label:
            excluded_nodes = self._resolve_exclude_nodes(kube, self.config.exclude_label)
            candidates = [node for node in candidates if node not in excluded_nodes]
            if not candidates:
                raise Exception("all nodes excluded by exclude_label, aborting")

        return candidates

    def _parse_target_spec(self, available_nodes: list[str]) -> list[str]:
        raw_target = self.config.target
        if raw_target is None:
            return []

        if isinstance(raw_target, list):
            return raw_target

        target_text = raw_target.strip()
        if target_text == "*":
            return available_nodes

        if "," in target_text:
            return [item.strip() for item in target_text.split(",") if item.strip()]

        if target_text.startswith("regex:"):
            pattern_text = target_text[len("regex:") :].strip()
            if not pattern_text:
                raise Exception("regex pattern cannot be empty")
            try:
                pattern = re.compile(pattern_text)
            except re.error as exc:
                raise Exception(f"invalid regex pattern {pattern_text}: {exc}") from exc
            return [node for node in available_nodes if pattern.search(node)]

        if "*" in target_text or "?" in target_text:
            return [node for node in available_nodes if fnmatch(node, target_text)]

        return [target_text]

    def _resolve_exclude_nodes(
        self, kube, exclude_spec: Union[str, List[str]]
    ) -> set[str]:
        selectors: List[str] = []
        if isinstance(exclude_spec, str):
            selectors = self._split_selectors(exclude_spec)
        elif isinstance(exclude_spec, list):
            for entry in exclude_spec:
                if not isinstance(entry, str):
                    raise Exception("exclude_label list entries must be strings")
                selectors.extend(self._split_selectors(entry))
        else:
            raise Exception("exclude_label must be a string or list of strings")

        excluded = set()
        for selector in selectors:
            excluded.update(kube.list_nodes(selector))
        return excluded

    @staticmethod
    def _split_selectors(selector_text: str) -> List[str]:
        return [item.strip() for item in selector_text.split(",") if item.strip()]
