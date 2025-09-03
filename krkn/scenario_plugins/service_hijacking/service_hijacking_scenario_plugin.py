import logging
import time

import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn_lib.utils import get_yaml_item_value

class ServiceHijackingScenarioPlugin(AbstractScenarioPlugin):
    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        with open(scenario) as stream:
            scenario_config = yaml.safe_load(stream)

        service_name = scenario_config["service_name"]
        service_namespace = scenario_config["service_namespace"]
        plan = scenario_config["plan"]
        image = scenario_config["image"]
        target_port = scenario_config["service_target_port"]
        chaos_duration = scenario_config["chaos_duration"]
        privileged = get_yaml_item_value(scenario_config,"privileged", True)


        logging.info(
            f"checking service {service_name} in namespace: {service_namespace}"
        )
        if not lib_telemetry.get_lib_kubernetes().service_exists(
            service_name, service_namespace
        ):
            logging.error(
                f"ServiceHijackingScenarioPlugin service: {service_name} not found in namespace: {service_namespace}, failed to run scenario."
            )
            return 1
        try:
            logging.info(
                f"service: {service_name} found in namespace: {service_namespace}"
            )
            logging.info(f"creating webservice and initializing test plan...")
            # both named ports and port numbers can be used
            if isinstance(target_port, int):
                logging.info(f"webservice will listen on port {target_port}")
                webservice = (
                    lib_telemetry.get_lib_kubernetes().deploy_service_hijacking(
                        service_namespace, plan, image, port_number=target_port, privileged=privileged
                    )
                )
            else:
                logging.info(f"traffic will be redirected to named port: {target_port}")
                webservice = (
                    lib_telemetry.get_lib_kubernetes().deploy_service_hijacking(
                        service_namespace, plan, image, port_name=target_port, privileged=privileged
                    )
                )
            logging.info(
                f"successfully deployed pod: {webservice.pod_name} "
                f"in namespace:{service_namespace} with selector {webservice.selector}!"
            )
            logging.info(
                f"patching service: {service_name} to hijack traffic towards: {webservice.pod_name}"
            )
            original_service = (
                lib_telemetry.get_lib_kubernetes().replace_service_selector(
                    [webservice.selector], service_name, service_namespace
                )
            )
            if original_service is None:
                logging.error(
                    f"ServiceHijackingScenarioPlugin failed to patch service: {service_name}, namespace: {service_namespace} with selector {webservice.selector}"
                )
                return 1

            logging.info(f"service: {service_name} successfully patched!")
            logging.info(f"original service manifest:\n\n{yaml.dump(original_service)}")
            logging.info(f"waiting {chaos_duration} before restoring the service")
            time.sleep(chaos_duration)
            selectors = [
                "=".join([key, original_service["spec"]["selector"][key]])
                for key in original_service["spec"]["selector"].keys()
            ]
            logging.info(f"restoring the service selectors {selectors}")
            original_service = (
                lib_telemetry.get_lib_kubernetes().replace_service_selector(
                    selectors, service_name, service_namespace
                )
            )
            if original_service is None:
                logging.error(
                    f"ServiceHijackingScenarioPlugin failed to restore original "
                    f"service: {service_name}, namespace: {service_namespace} with selectors: {selectors}"
                )
                return 1
            logging.info("selectors successfully restored")
            logging.info("undeploying service-hijacking resources...")
            lib_telemetry.get_lib_kubernetes().undeploy_service_hijacking(webservice)
            return 0
        except Exception as e:
            logging.error(
                f"ServiceHijackingScenarioPlugin scenario {scenario} failed with exception: {e}"
            )
            return 1

    def get_scenario_types(self) -> list[str]:
        return ["service_hijacking_scenarios"]
