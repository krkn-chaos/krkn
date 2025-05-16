import logging

from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.utils import log_exception

from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class KubevirtVmOutageScenarioPlugin(AbstractScenarioPlugin):
    """
    A scenario plugin that injects chaos by deleting a KubeVirt Virtual Machine Instance (VMI).
    This plugin simulates a VM crash or outage scenario and supports automated or manual recovery.
    """

    def __init__(self):
        self.kubevirt_api = None
        self.k8s_api = None
        self.original_vmi = None
        
    def get_scenario_types(self) -> list[str]:
        """
        Returns the list of scenario types this plugin supports.
        """
        return ["kubevirt_vm_outage"]

    def run(
        self,
        run_uuid: str,
        scenario: str,
        krkn_config: dict[str, any],
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        """
        Main entry point for the plugin.
        Parses the scenario configuration and executes the chaos scenario.
        """
        try:
            with open(scenario, "r") as f:
                scenario_config = yaml.full_load(f)
                
            self.init_clients(lib_telemetry.get_lib_kubernetes())
            
            for config in scenario_config["scenarios"]:
                if config.get("scenario") == "kubevirt_vm_outage":
                    result = self.execute_scenario(config, scenario_telemetry)
                    if result != 0:
                        return 1
                        
            return 0
        except Exception as e:
            logging.error(f"KubeVirt VM Outage scenario failed: {e}")
            log_exception(e)
            return 1
            logging.error(f"Unexpected error getting VMI {vm_name}: {e}")
            raise

    def inject(self, vm_name: str, namespace: str) -> int:
        """
        Delete a Virtual Machine Instance to simulate a VM outage.
        
        :param vm_name: Name of the VMI to delete
        :param namespace: Namespace of the VMI
        :return: 0 for success, 1 for failure
        """
        return 0

    def recover(self, vm_name: str, namespace: str) -> int:
        """
        Recover a deleted VMI, either by waiting for auto-recovery or manually recreating it.
        
        :param vm_name: Name of the VMI to recover
        :param namespace: Namespace of the VMI
        :return: 0 for success, 1 for failure
        """
        return 0
