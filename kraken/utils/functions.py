import krkn_lib.utils
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.telemetry import ScenarioTelemetry
from tzlocal.unix import get_localzone


def populate_cluster_events(scenario_telemetry: ScenarioTelemetry,
                                  scenario_config: dict,
                                  kubecli: KrknKubernetes,
                                  start_timestamp: int,
                                  end_timestamp: int
                                  ):
    namespaces = []
    events = []
    namespaces.extend(krkn_lib.utils.deep_get_attribute("namespace", scenario_config))
    namespace_patterns = krkn_lib.utils.deep_get_attribute("namespace_pattern", scenario_config)
    for pattern in namespace_patterns:
        namespaces.extend(kubecli.list_namespaces_by_regex(pattern))

    if len(namespaces) == 0:
        events.extend(kubecli.collect_and_parse_cluster_events(start_timestamp, end_timestamp, str(get_localzone())))
    else:
        for namespace in namespaces:
            events.extend(kubecli.collect_and_parse_cluster_events(start_timestamp, end_timestamp, str(get_localzone()), namespace=namespace))

    scenario_telemetry.set_cluster_events(events)
