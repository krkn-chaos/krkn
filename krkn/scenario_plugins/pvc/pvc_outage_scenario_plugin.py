import logging
import time
import json
import yaml
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import get_yaml_item_value, get_random_string
from krkn import cerberus
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.rollback.config import RollbackContent
from krkn.rollback.handler import set_rollback_context_decorator


class PvcOutageScenarioPlugin(AbstractScenarioPlugin):
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
                pvc_outage_config_yaml = yaml.full_load(f)
                scenario_config = pvc_outage_config_yaml["pvc_outage"]
                pvc_selector = get_yaml_item_value(
                    scenario_config, "pvc_selector", None
                )
                pvc_name = get_yaml_item_value(scenario_config, "pvc_name", None)
                namespace = get_yaml_item_value(scenario_config, "namespace", "")
                duration = get_yaml_item_value(scenario_config, "duration", 60)

                # Validate input parameters
                if not namespace:
                    logging.error("PvcOutageScenarioPlugin: namespace must be specified")
                    return 1
                
                if not pvc_selector and not pvc_name:
                    logging.error(
                        "PvcOutageScenarioPlugin: Either pvc_selector or pvc_name must be specified"
                    )
                    return 1

                start_time = int(time.time())
                annotation_key = "krkn/pvc-outage"
                annotation_value = f"true-{get_random_string(5)}"

                # Get list of PVCs to annotate
                target_pvcs = []
                if pvc_name:
                    # Single PVC specified by name
                    target_pvcs = [pvc_name]
                    logging.info(f"Targeting PVC: {pvc_name} in namespace: {namespace}")
                else:
                    # Multiple PVCs specified by selector
                    logging.info(
                        f"Querying PVCs with selector: {pvc_selector} in namespace: {namespace}"
                    )
                    try:
                        all_pvcs = lib_telemetry.get_lib_kubernetes().list_pvcs(namespace)
                        # Filter PVCs based on selector (assuming format: key=value)
                        if pvc_selector:
                            selector_parts = pvc_selector.split("=")
                            if len(selector_parts) == 2:
                                selector_key = selector_parts[0].strip()
                                selector_value = selector_parts[1].strip()
                                for pvc in all_pvcs:
                                    pvc_info = lib_telemetry.get_lib_kubernetes().get_pvc_info(
                                        pvc, namespace
                                    )
                                    if hasattr(pvc_info, 'labels') and pvc_info.labels:
                                        if pvc_info.labels.get(selector_key) == selector_value:
                                            target_pvcs.append(pvc)
                            else:
                                # If no specific selector format, target all PVCs
                                target_pvcs = all_pvcs
                        else:
                            target_pvcs = all_pvcs
                    except Exception as e:
                        logging.error(f"Failed to list PVCs in namespace {namespace}: {e}")
                        return 1

                if not target_pvcs:
                    logging.error(
                        f"No PVCs found matching the criteria in namespace: {namespace}"
                    )
                    return 1

                logging.info(f"Found {len(target_pvcs)} PVC(s) to annotate: {target_pvcs}")

                # Store original annotations for rollback
                original_annotations = {}
                annotated_pvcs = []

                # Annotate each PVC to simulate outage
                for pvc in target_pvcs:
                    try:
                        logging.info(f"Annotating PVC: {pvc} in namespace: {namespace}")
                        
                        # Get current PVC info to store original annotations
                        pvc_info = lib_telemetry.get_lib_kubernetes().get_pvc_info(
                            pvc, namespace
                        )
                        
                        # Store original annotation value if it exists
                        if hasattr(pvc_info, 'annotations') and pvc_info.annotations:
                            original_annotations[pvc] = pvc_info.annotations.get(annotation_key)
                        else:
                            original_annotations[pvc] = None

                        # Apply the annotation using patch
                        patch_body = {
                            "metadata": {
                                "annotations": {
                                    annotation_key: annotation_value
                                }
                            }
                        }
                        
                        lib_telemetry.get_lib_kubernetes().cli.patch_namespaced_persistent_volume_claim(
                            name=pvc,
                            namespace=namespace,
                            body=patch_body
                        )
                        
                        annotated_pvcs.append(pvc)
                        logging.info(f"Successfully annotated PVC: {pvc}")
                        
                    except Exception as e:
                        logging.error(f"Failed to annotate PVC {pvc}: {e}")
                        # Continue with other PVCs even if one fails
                        continue

                if not annotated_pvcs:
                    logging.error("Failed to annotate any PVCs")
                    return 1

                # Encode rollback data in resource_identifier as JSON string
                # Format: json encoded dict with pvcs, annotation_key, and original_annotations
                rollback_data = {
                    "pvcs": annotated_pvcs,
                    "annotation_key": annotation_key,
                    "original_annotations": original_annotations
                }
                
                # Set rollback callable to remove annotations
                self.rollback_handler.set_rollback_callable(
                    self.rollback_pvc_annotations,
                    RollbackContent(
                        namespace=namespace,
                        resource_identifier=json.dumps(rollback_data),
                    ),
                )

                # Wait for the specified duration
                logging.info(
                    f"PVC outage in effect. Waiting for duration: {duration}s"
                )
                time.sleep(duration)

                # Remove annotations to restore PVCs
                logging.info("Removing annotations from PVCs to restore normal operation")
                for pvc in annotated_pvcs:
                    try:
                        self._remove_pvc_annotation(
                            lib_telemetry,
                            pvc,
                            namespace,
                            annotation_key,
                            original_annotations.get(pvc)
                        )
                        logging.info(f"Successfully removed annotation from PVC: {pvc}")
                    except Exception as e:
                        logging.error(f"Failed to remove annotation from PVC {pvc}: {e}")

                logging.info(
                    f"PVC outage scenario completed. Waiting for: {wait_duration}s"
                )
                time.sleep(wait_duration)

                end_time = int(time.time())
                cerberus.publish_kraken_status(krkn_config, [], start_time, end_time)
                
        except Exception as e:
            logging.error(
                f"PvcOutageScenarioPlugin exiting due to Exception: {e}"
            )
            return 1
        else:
            return 0

    @staticmethod
    def _remove_pvc_annotation(
        lib_telemetry: KrknTelemetryOpenshift,
        pvc_name: str,
        namespace: str,
        annotation_key: str,
        original_value: str = None
    ):
        """Helper method to remove or restore PVC annotation.
        
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        :param pvc_name: Name of the PVC.
        :param namespace: Namespace where the PVC exists.
        :param annotation_key: Key of the annotation to remove/restore.
        :param original_value: Original value of the annotation (None if it didn't exist).
        """
        if original_value is None:
            # Remove the annotation entirely
            patch_body = {
                "metadata": {
                    "annotations": {
                        annotation_key: None
                    }
                }
            }
        else:
            # Restore original annotation value
            patch_body = {
                "metadata": {
                    "annotations": {
                        annotation_key: original_value
                    }
                }
            }
        
        lib_telemetry.get_lib_kubernetes().cli.patch_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=namespace,
            body=patch_body
        )

    @staticmethod
    def rollback_pvc_annotations(
        rollback_content: RollbackContent,
        lib_telemetry: KrknTelemetryOpenshift,
    ):
        """Rollback function to remove/restore PVC annotations created during the scenario.

        :param rollback_content: Rollback content containing namespace and encoded rollback data in resource_identifier.
        :param lib_telemetry: Instance of KrknTelemetryOpenshift for Kubernetes operations.
        """
        try:
            namespace = rollback_content.namespace
            
            # Decode rollback data from resource_identifier
            rollback_data = json.loads(rollback_content.resource_identifier)
            pvc_names = rollback_data["pvcs"]
            annotation_key = rollback_data["annotation_key"]
            original_annotations = rollback_data.get("original_annotations", {})
            
            logging.info(
                f"Rolling back PVC annotations in namespace: {namespace}"
            )
            
            for pvc_name in pvc_names:
                try:
                    original_value = original_annotations.get(pvc_name)
                    PvcOutageScenarioPlugin._remove_pvc_annotation(
                        lib_telemetry,
                        pvc_name,
                        namespace,
                        annotation_key,
                        original_value
                    )
                    logging.info(f"Rolled back annotation for PVC: {pvc_name}")
                except Exception as e:
                    logging.error(f"Failed to rollback PVC {pvc_name}: {e}")
                    
            logging.info("PVC annotation rollback completed successfully.")
        except Exception as e:
            logging.error(f"Failed to rollback PVC annotations: {e}")

    def get_scenario_types(self) -> list[str]:
        return ["pvc_outage_scenarios"]
    
    