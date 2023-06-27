import yaml
import logging
import time
import kraken.cerberus.setup as cerberus
from jinja2 import Template
import kraken.invoke.command as runcommand
from krkn_lib_kubernetes import ScenarioTelemetry, KrknTelemetry

# Reads the scenario config, applies and deletes a network policy to
# block the traffic for the specified duration
def run(scenarios_list, config, wait_duration, telemetry: KrknTelemetry) -> (list[str], list[ScenarioTelemetry]):
    failed_post_scenarios = ""
    scenario_telemetries: list[ScenarioTelemetry] = []
    failed_scenarios = []
    for app_outage_config in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = app_outage_config[0]
        scenario_telemetry.startTimeStamp = time.time()
        telemetry.set_parameters_base64(scenario_telemetry, app_outage_config[0])
        if len(app_outage_config) > 1:
            try:
                with open(app_outage_config, "r") as f:
                    app_outage_config_yaml = yaml.full_load(f)
                    scenario_config = app_outage_config_yaml["application_outage"]
                    pod_selector = scenario_config.get("pod_selector", "{}")
                    traffic_type = scenario_config.get("block", "[Ingress, Egress]")
                    namespace = scenario_config.get("namespace", "")
                    duration = scenario_config.get("duration", 60)

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
                    rendered_spec = t.render(pod_selector=pod_selector, traffic_type=traffic_type)
                    # Write the rendered template to a file
                    with open("kraken_network_policy.yaml", "w") as f:
                        f.write(rendered_spec)
                    # Block the traffic by creating network policy
                    logging.info("Creating the network policy")
                    runcommand.invoke(
                        "kubectl create -f %s -n %s --validate=false" % ("kraken_network_policy.yaml", namespace)
                    )

                    # wait for the specified duration
                    logging.info("Waiting for the specified duration in the config: %s" % (duration))
                    time.sleep(duration)

                    # unblock the traffic by deleting the network policy
                    logging.info("Deleting the network policy")
                    runcommand.invoke("kubectl delete -f %s -n %s" % ("kraken_network_policy.yaml", namespace))

                    logging.info("End of scenario. Waiting for the specified duration: %s" % (wait_duration))
                    time.sleep(wait_duration)

                    end_time = int(time.time())
                    cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)
            except Exception as e :
                scenario_telemetry.exitStatus = 1
                failed_scenarios.append(app_outage_config[0])
                telemetry.log_exception(app_outage_config[0])
            else:
                scenario_telemetry.exitStatus = 0
            scenario_telemetry.endTimeStamp = time.time()
            scenario_telemetries.append(scenario_telemetry)
    return failed_scenarios, scenario_telemetries

