import logging
import time
import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, get_random_string
from jinja2 import Template
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class ApplicationOutageScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
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
                exclude_label = get_yaml_item_value(
                    scenario_config, "exclude_label", None
                )
                match_expressions = self._build_exclude_expressions(exclude_label)
                if match_expressions:
                    # Log the format being used for better clarity
                    format_type = "dict" if isinstance(exclude_label, dict) else "string"
                    logging.info(
                        "Excluding pods with labels (%s format): %s",
                        format_type,
                        ", ".join(
                            f"{expr['key']} NOT IN {expr['values']}"
                            for expr in match_expressions
                        ),
                    )

                start_time = int(time.time())
                policy_name = f"krkn-deny-{get_random_string(5)}"

                network_policy_template = (
                    """---
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: {{ policy_name }}
        spec:
          podSelector:
            matchLabels: {{ pod_selector }}
{% if match_expressions %}
            matchExpressions:
{% for expression in match_expressions %}
              - key: {{ expression["key"] }}
                operator: NotIn
                values:
{% for value in expression["values"] %}
                  - {{ value }}
{% endfor %}
{% endfor %}
{% endif %}
          policyTypes: {{ traffic_type }}
        """
                )
                t = Template(network_policy_template)
                rendered_spec = t.render(
                    pod_selector=pod_selector,
                    traffic_type=traffic_type,
                    match_expressions=match_expressions,
                    policy_name=policy_name,
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

                end_time = int(time.time())
                
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

    def get_scenario_types(self) -> list[str]:
        return ["application_outages_scenarios"]

    @staticmethod
    def _build_exclude_expressions(exclude_label) -> list[dict]:
        """
        Build match expressions for NetworkPolicy from exclude_label.
        
        Supports multiple formats:
        - Dict format (preferred, similar to pod_selector): {key1: value1, key2: [value2, value3]}
          Example: {tier: "gold", env: ["prod", "staging"]}
        - String format: "key1=value1,key2=value2" or "key1=value1|value2"
          Example: "tier=gold,env=prod" or "tier=gold|platinum"
        - List format (list of strings): ["key1=value1", "key2=value2"]
          Example: ["tier=gold", "env=prod"]
          Note: List elements must be strings in "key=value" format.
        
        :param exclude_label: Can be dict, string, list of strings, or None
        :return: List of match expression dictionaries
        """
        expressions: list[dict] = []

        if not exclude_label:
            return expressions

        def _append_expr(key: str, values):
            if not key or values is None:
                return
            if not isinstance(values, list):
                values = [values]
            cleaned_values = [str(v).strip() for v in values if str(v).strip()]
            if cleaned_values:
                expressions.append({"key": key.strip(), "values": cleaned_values})

        if isinstance(exclude_label, dict):
            for k, v in exclude_label.items():
                _append_expr(str(k), v)
            return expressions

        if isinstance(exclude_label, list):
            selectors = exclude_label
        else:
            selectors = [sel.strip() for sel in str(exclude_label).split(",")]

        for selector in selectors:
            if not selector:
                continue
            if "=" not in selector:
                logging.warning(
                    "exclude_label entry '%s' is invalid, expected key=value format",
                    selector,
                )
                continue
            key, value = selector.split("=", 1)
            value_items = (
                [item.strip() for item in value.split("|") if item.strip()]
                if value
                else []
            )
            _append_expr(key, value_items or value)

        return expressions
