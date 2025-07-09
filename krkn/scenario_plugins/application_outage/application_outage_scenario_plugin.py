import logging
import time
import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, get_random_string
from jinja2 import Template
from krkn import cerberus
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class ApplicationOutageScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
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
                policy_name = f"krkn-deny-{get_random_string(5)}"

                network_policy_template = (
                    """---
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: """
                    + policy_name
                    + """
        spec:
          podSelector:
            matchLabels: {{ pod_selector }}
          policyTypes: {{ traffic_type }}
        """
                )
                t = Template(network_policy_template)
                rendered_spec = t.render(
                    pod_selector=pod_selector, traffic_type=traffic_type
                )
                yaml_spec = yaml.safe_load(rendered_spec)
                # Block the traffic by creating network policy
                logging.info("Creating the network policy")

                self.rollback_handler.set_rollback_callable(
                    self.rollback_network_policy,
                    RollbackContent(
                        namespace=namespace,
                        resource_identifier=policy_name,
                    ),
                )
                lib_telemetry.get_lib_kubernetes().create_net_policy(
                    yaml_spec, namespace
                )
                self.rollback_handler.set_rollback_callable(
                    self.rollback_network_policy,
                    RollbackContent(
                        namespace=namespace,
                        resource_identifier=policy_name,
                    ),
                )

                # wait for the specified duration
                logging.info(
                    "Waiting for the specified duration in the config: %s" % duration
                )
                time.sleep(duration)

                # unblock the traffic by deleting the network policy
                logging.info("Deleting the network policy")
                lib_telemetry.get_lib_kubernetes().delete_net_policy(
                    policy_name, namespace
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

    @staticmethod
    def rollback_network_policy(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to delete the network policy created during the scenario.

        :param rollback_content: Rollback content containing namespace and resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        """
        try:
            namespace = rollback_content.namespace
            policy_name = rollback_content.resource_identifier
            logging.info(
                f"Rolling back network policy: {policy_name} in namespace: {namespace}"
            )
            lib_telemetry.get_lib_kubernetes().delete_net_policy(policy_name, namespace)
            logging.info("Network policy rollback completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback network policy: {e}")

    @staticmethod
    def rollback_network_policy(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to delete the network policy created during the scenario.

        :param rollback_content: Rollback content containing namespace and resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        """
        try:
            namespace = rollback_content.namespace
            policy_name = rollback_content.resource_identifier
            logging.info(
                f"Rolling back network policy: {policy_name} in namespace: {namespace}"
            )
            lib_telemetry.get_lib_kubernetes().delete_net_policy(policy_name, namespace)
            logging.info("Network policy rollback completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback network policy: {e}")

    def get_scenario_types(self) -> list[str]:
        return ["application_outages_scenarios"]
