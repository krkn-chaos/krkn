import logging
import time
import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value
from jinja2 import Template
from krkn import cerberus
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class ApplicationOutageScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        wait_duration = krkn_config["tunings"]["wait_duration"]
        try:
            with open(scenario, "r") as f:
                app_outage_config_yaml = yaml.full_load(f)
                scenario_config = app_outage_config_yaml["application_outage"]
                pod_selector = get_yaml_item_value(
                    scenario_config, "pod_selector", "{}"
                )
                traffic_type = get_yaml_item_value(
                    scenario_config, "block", "[Ingress, Egress]"
                )
                namespace = get_yaml_item_value(scenario_config, "namespace", "")
                duration = get_yaml_item_value(scenario_config, "duration", 60)

                start_time = int(time.time())

                network_policy_template = """---
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: kraken-deny
        spec:
          podSelector:
            matchLabels: {{ pod_selector }}
          policyTypes: {{ traffic_type }}
        """
                t = Template(network_policy_template)
                rendered_spec = t.render(
                    pod_selector=pod_selector, traffic_type=traffic_type
                )
                yaml_spec = yaml.safe_load(rendered_spec)
                # Block the traffic by creating network policy
                logging.info("Creating the network policy")

                lib_telemetry.get_lib_kubernetes().create_net_policy(
                    yaml_spec, namespace
                )

                # wait for the specified duration
                logging.info(
                    "Waiting for the specified duration in the config: %s" % duration
                )
                time.sleep(duration)

                # unblock the traffic by deleting the network policy
                logging.info("Deleting the network policy")
                lib_telemetry.get_lib_kubernetes().delete_net_policy(
                    "kraken-deny", namespace
                )

                logging.info(
                    "End of scenario. Waiting for the specified duration: %s"
                    % wait_duration
                )
                time.sleep(wait_duration)

                end_time = int(time.time())
                cerberus.publish_kraken_status(krkn_config, [], start_time, end_time)
        except Exception as e:
            logging.error(
                "ApplicationOutageScenarioPlugin exiting due to Exception %s" % e
            )
            return 1
        else:
            return 0

    def get_scenario_type(self) -> str:
        return "application_outages"
