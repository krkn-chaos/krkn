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
            "checking service %s in namespace: %s",
            service_name,
            service_namespace,
        )
        if not lib_telemetry.get_lib_kubernetes().service_exists(
            service_name, service_namespace
        ):
            logging.error(
                "ServiceHijackingScenarioPlugin service: %s not found in namespace: %s, failed to run scenario.",
                service_name,
                service_namespace,
            )
            return 1
        try:
            logging.info(
                "service: %s found in namespace: %s",
                service_name,
                service_namespace,
            )
            logging.info("creating webservice and initializing test plan...")
            # both named ports and port numbers can be used
            if isinstance(target_port, int):
                logging.info("webservice will listen on port %s", target_port)
                webservice = (
                    lib_telemetry.get_lib_kubernetes().deploy_service_hijacking(
                        service_namespace, plan, image, port_number=target_port, privileged=privileged
                    )
                )
            else:
                logging.info("traffic will be redirected to named port: %s", target_port)
                webservice = (
                    lib_telemetry.get_lib_kubernetes().deploy_service_hijacking(
                        service_namespace, plan, image, port_name=target_port, privileged=privileged
                    )
                )
            logging.info(
                "successfully deployed pod: %s in namespace:%s with selector %s!",
                webservice.pod_name,
                service_namespace,
                webservice.selector,
            )
            logging.info(
                "patching service: %s to hijack traffic towards: %s",
                service_name,
                webservice.pod_name,
            )
            original_service = (
                lib_telemetry.get_lib_kubernetes().replace_service_selector(
                    [webservice.selector], service_name, service_namespace
                )
            )
            if original_service is None:
                logging.error(
                    "ServiceHijackingScenarioPlugin failed to patch service: %s, namespace: %s with selector %s",
                    service_name,
                    service_namespace,
                    webservice.selector,
                )
                return 1

            logging.info("service: %s successfully patched!", service_name)
            logging.info("original service manifest:\n\n%s", yaml.dump(original_service))
            
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
            
            logging.info("waiting %s before restoring the service", chaos_duration)
            time.sleep(chaos_duration)
            selectors = [
                "=".join([key, original_service["spec"]["selector"][key]])
                for key in original_service["spec"]["selector"].keys()
            ]
            logging.info("restoring the service selectors %s", selectors)
            original_service = (
                lib_telemetry.get_lib_kubernetes().replace_service_selector(
                    selectors, service_name, service_namespace
                )
            )
            if original_service is None:
                logging.error(
                    "ServiceHijackingScenarioPlugin failed to restore original service: %s, namespace: %s with selectors: %s",
                    service_name,
                    service_namespace,
                    selectors,
                )
                return 1
            logging.info("selectors successfully restored")
            logging.info("undeploying service-hijacking resources...")
            lib_telemetry.get_lib_kubernetes().undeploy_service_hijacking(webservice)
            return 0
        except Exception as e:
            logging.error(
                "ServiceHijackingScenarioPlugin scenario %s failed with exception: %s",
                scenario,
                e,
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
                "Rolling back service hijacking: restoring service %s in namespace %s",
                service_name,
                service_namespace,
            )
            
            # Restore original service selectors
            selectors = [
                "=".join([key, original_selectors[key]])
                for key in original_selectors.keys()
            ]
            logging.info("Restoring original service selectors: %s", selectors)
            
            restored_service = lib_telemetry.get_lib_kubernetes().replace_service_selector(
                selectors, service_name, service_namespace
            )
            
            if restored_service is None:
                logging.warning(
                    "Failed to restore service %s in namespace %s",
                    service_name,
                    service_namespace,
                )
            else:
                logging.info("Successfully restored service %s", service_name)
            
            # Delete the hijacker pod
            logging.info("Deleting hijacker pod: %s", webservice_pod_name)
            try:
                lib_telemetry.get_lib_kubernetes().delete_pod(
                    webservice_pod_name, service_namespace
                )
                logging.info("Successfully deleted hijacker pod: %s", webservice_pod_name)
            except Exception as e:
                logging.warning(
                    "Failed to delete hijacker pod %s: %s",
                    webservice_pod_name,
                    e,
                )
            
            logging.info("Service hijacking rollback completed successfully.")
        except Exception as e:
            logging.error("Failed to rollback service hijacking: %s", e)

    def get_scenario_types(self) -> list[str]:
        return ["service_hijacking_scenarios"]
