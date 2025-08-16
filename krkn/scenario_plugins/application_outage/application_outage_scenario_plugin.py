import logging
import time
import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, get_random_string
from jinja2 import Template
# Change the import to make it easier to mock in tests
try:
    from krkn import cerberus
except ImportError:
    cerberus = None  # Handle case when cerberus is not available
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
                if "application_outage" not in app_outage_config_yaml:
                    logging.error("Missing 'application_outage' section in scenario config")
                    return 1
                    
                scenario_config = app_outage_config_yaml["application_outage"]
                
                # Get pod selector and ensure it's a dictionary
                pod_selector = get_yaml_item_value(
                    scenario_config, "pod_selector", "{}"
                )
                if isinstance(pod_selector, str):
                    try:
                        pod_selector = yaml.safe_load(pod_selector)
                    except yaml.YAMLError:
                        logging.error("Invalid pod_selector format. Expected a valid YAML dictionary")
                        return 1
                
                # Ensure pod_selector is a non-empty dictionary
                if not pod_selector or not isinstance(pod_selector, dict):
                    logging.error("pod_selector must be a non-empty dictionary of labels")
                    return 1
                
                # Get traffic type and ensure it's a list
                traffic_type = get_yaml_item_value(
                    scenario_config, "block", "[Ingress, Egress]"
                )
                if isinstance(traffic_type, str):
                    try:
                        traffic_type = yaml.safe_load(traffic_type)
                    except yaml.YAMLError:
                        logging.error("Invalid traffic_type format. Expected a valid YAML list")
                        return 1
                
                # Validate traffic_type is a list of valid policy types
                if not isinstance(traffic_type, list):
                    logging.error("traffic_type must be a list")
                    return 1
                
                valid_policy_types = ["Ingress", "Egress"]
                for policy_type in traffic_type:
                    if policy_type not in valid_policy_types:
                        logging.error(f"Invalid policy type: {policy_type}. Must be one of {valid_policy_types}")
                        return 1
                
                namespace = get_yaml_item_value(scenario_config, "namespace", "")
                if not namespace:
                    logging.error("namespace is required")
                    return 1
                
                duration = get_yaml_item_value(scenario_config, "duration", 60)
                try:
                    duration = int(duration)
                except ValueError:
                    logging.error("duration must be an integer")
                    return 1

                start_time = int(time.time())
                # Get custom policy name if provided
                policy_name = get_yaml_item_value(
                    scenario_config, "policy_name", f"krkn-deny-{get_random_string(5)}"
                )

                network_policy_template = """---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ policy_name }}
  labels:
    app: krkn
    scenario: application-outage
spec:
  podSelector:
    matchLabels: {{ pod_selector }}
  policyTypes:
{% for type in traffic_type %}
    - {{ type }}
{% endfor %}
{% if "Ingress" in traffic_type %}
  ingress: []  # Empty array = deny all ingress traffic
{% endif %}
{% if "Egress" in traffic_type %}
  egress: []   # Empty array = deny all egress traffic
{% endif %}
"""
                t = Template(network_policy_template)
                rendered_spec = t.render(
                    policy_name=policy_name,
                    pod_selector=pod_selector, 
                    traffic_type=traffic_type
                )
                
                try:
                    yaml_spec = yaml.safe_load(rendered_spec)
                    # Block the traffic by creating network policy
                    logging.info(f"Creating the network policy {policy_name} in namespace {namespace}")
                    lib_telemetry.get_lib_kubernetes().create_net_policy(
                        yaml_spec, namespace
                    )
                except yaml.YAMLError as yaml_err:
                    logging.error(f"Error parsing network policy YAML: {yaml_err}")
                    return 1
                except Exception as net_err:
                    logging.error(f"Error creating network policy: {net_err}")
                    return 1

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

    def get_scenario_types(self) -> list[str]:
        return ["application_outages_scenarios"]
