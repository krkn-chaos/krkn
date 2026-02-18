import json
import logging
import time
import base64
import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn_lib.utils import get_yaml_item_value
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator

class ServiceHijackingScenarioPlugin(AbstractScenarioPlugin):
    @set_rollback_context_decorator
    def run(
        self,
        run_uuid: str,
        scenario: str,
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
            
            # Set rollback callable to ensure service restoration and pod cleanup on failure or interruption
            rollback_data = {
                "service_name": service_name,
                "service_namespace": service_namespace,
                "original_selectors": original_service["spec"]["selector"],
                "webservice_pod_name": webservice.pod_name,
            }
            json_str = json.dumps(rollback_data)
            encoded_data = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
            self.rollback_handler.set_rollback_callable(
                self.rollback_service_hijacking,
                RollbackContent(
                    namespace=service_namespace,
                    resource_identifier=encoded_data,
                ),
            )
            
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

    @staticmethod
    def rollback_service_hijacking(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to restore original service selectors and cleanup hijacker pod.

        :param rollback_content: Rollback content containing namespace and encoded rollback data in resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        """
        try:
            namespace = rollback_content.namespace
            import json # noqa
            import base64 # noqa
            # Decode rollback data from resource_identifier
            decoded_data = base64.b64decode(rollback_content.resource_identifier.encode("utf-8")).decode("utf-8")
            rollback_data = json.loads(decoded_data)
            service_name = rollback_data["service_name"]
            service_namespace = rollback_data["service_namespace"]
            original_selectors = rollback_data["original_selectors"]
            webservice_pod_name = rollback_data["webservice_pod_name"]
            
            logging.info(
                f"Rolling back service hijacking: restoring service {service_name} in namespace {service_namespace}"
            )
            
            # Restore original service selectors
            selectors = [
                "=".join([key, original_selectors[key]])
                for key in original_selectors.keys()
            ]
            logging.info(f"Restoring original service selectors: {selectors}")
            
            restored_service = lib_telemetry.get_lib_kubernetes().replace_service_selector(
                selectors, service_name, service_namespace
            )
            
            if restored_service is None:
                logging.warning(
                    f"Failed to restore service {service_name} in namespace {service_namespace}"
                )
            else:
                logging.info(f"Successfully restored service {service_name}")
            
            # Delete the hijacker pod
            logging.info(f"Deleting hijacker pod: {webservice_pod_name}")
            try:
                lib_telemetry.get_lib_kubernetes().delete_pod(
                    webservice_pod_name, service_namespace
                )
                logging.info(f"Successfully deleted hijacker pod: {webservice_pod_name}")
            except Exception as e:
                logging.warning(f"Failed to delete hijacker pod {webservice_pod_name}: {e}")
            
            logging.info("Service hijacking rollback completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback service hijacking: {e}")

    def get_scenario_types(self) -> list[str]:
        return ["service_hijacking_scenarios"]
