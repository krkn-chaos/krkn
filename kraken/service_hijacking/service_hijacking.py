import logging
import time
import yaml

from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import log_exception

from kraken import utils


def run(scenarios_list: list[str],
        wait_duration: int,
        telemetry: KrknTelemetryOpenshift,
        telemetry_request_id: str) -> (list[str], list[ScenarioTelemetry]):

    scenario_telemetries = list[ScenarioTelemetry]()
    failed_post_scenarios = []
    for scenario in scenarios_list:
        scenario_telemetry = ScenarioTelemetry()
        scenario_telemetry.scenario = scenario
        scenario_telemetry.start_timestamp = time.time()
        parsed_scenario_config = telemetry.set_parameters_base64(scenario_telemetry, scenario)
        with open(scenario) as stream:
            scenario_config = yaml.safe_load(stream)

        service_name = scenario_config['service_name']
        service_namespace = scenario_config['service_namespace']
        plan = scenario_config["plan"]
        image = scenario_config["image"]
        target_port = scenario_config["service_target_port"]
        chaos_duration = scenario_config["chaos_duration"]

        logging.info(f"checking service {service_name} in namespace: {service_namespace}")
        if not telemetry.kubecli.service_exists(service_name, service_namespace):
            logging.error(f"service: {service_name} not found in namespace: {service_namespace}, failed to run scenario.")
            fail_scenario_telemetry(scenario_telemetry)
            failed_post_scenarios.append(scenario)
            break
        try:
            logging.info(f"service: {service_name} found in namespace: {service_namespace}")
            logging.info(f"creating webservice and initializing test plan...")
            # both named ports and port numbers can be used
            if isinstance(target_port, int):
                logging.info(f"webservice will listen on port {target_port}")
                webservice = telemetry.kubecli.deploy_service_hijacking(service_namespace, plan, image, port_number=target_port)
            else:
                logging.info(f"traffic will be redirected to named port: {target_port}")
                webservice = telemetry.kubecli.deploy_service_hijacking(service_namespace, plan, image, port_name=target_port)
            logging.info(f"successfully deployed pod: {webservice.pod_name} "
                         f"in namespace:{service_namespace} with selector {webservice.selector}!"
                         )
            logging.info(f"patching service: {service_name} to hijack traffic towards: {webservice.pod_name}")
            original_service = telemetry.kubecli.replace_service_selector([webservice.selector], service_name, service_namespace)
            if original_service is None:
                logging.error(f"failed to patch service: {service_name}, namespace: {service_namespace} with selector {webservice.selector}")
                fail_scenario_telemetry(scenario_telemetry)
                failed_post_scenarios.append(scenario)
                break

            logging.info(f"service: {service_name} successfully patched!")
            logging.info(f"original service manifest:\n\n{yaml.dump(original_service)}")
            logging.info(f"waiting {chaos_duration} before restoring the service")
            time.sleep(chaos_duration)
            selectors = ["=".join([key, original_service["spec"]["selector"][key]]) for key in original_service["spec"]["selector"].keys()]
            logging.info(f"restoring the service selectors {selectors}")
            original_service = telemetry.kubecli.replace_service_selector(selectors, service_name, service_namespace)
            if original_service is None:
                logging.error(f"failed to restore original service: {service_name}, namespace: {service_namespace} with selectors: {selectors}")
                fail_scenario_telemetry(scenario_telemetry)
                failed_post_scenarios.append(scenario)
                break
            logging.info("selectors successfully restored")
            logging.info("undeploying service-hijacking resources...")
            telemetry.kubecli.undeploy_service_hijacking(webservice)

            logging.info("End of scenario. Waiting for the specified duration: %s" % (wait_duration))
            time.sleep(wait_duration)
            scenario_telemetry.exit_status = 0
            logging.info("success")
        except Exception as e:
            logging.error(f"scenario {scenario} failed with exception: {e}")
            fail_scenario_telemetry(scenario_telemetry)
            log_exception(scenario)

        scenario_telemetry.end_timestamp = time.time()
        utils.collect_and_put_ocp_logs(telemetry,
                                       parsed_scenario_config,
                                       telemetry_request_id,
                                       int(scenario_telemetry.start_timestamp),
                                       int(scenario_telemetry.end_timestamp))
        utils.populate_cluster_events(scenario_telemetry,
                                      parsed_scenario_config,
                                      telemetry.kubecli,
                                      int(scenario_telemetry.start_timestamp),
                                      int(scenario_telemetry.end_timestamp))
        scenario_telemetries.append(scenario_telemetry)

    return failed_post_scenarios, scenario_telemetries

def fail_scenario_telemetry(scenario_telemetry: ScenarioTelemetry):
    scenario_telemetry.exit_status = 1
    scenario_telemetry.end_timestamp = time.time()