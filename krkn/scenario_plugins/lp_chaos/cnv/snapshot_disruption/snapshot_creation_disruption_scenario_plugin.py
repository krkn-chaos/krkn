# Import standard libraries
import logging
import time

# Import Kraken framework components
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from .snapshot_disruption_base import SnapshotDisruptionBase


class SnapshotCreationDisruptionScenarioPlugin(
    SnapshotDisruptionBase, AbstractScenarioPlugin
):
    """
    This plugin implements the specific chaos logic for disrupting a VM
    snapshot during its CREATION phase.
    """

    _NAME = "snapshot_creation_disruption"

    def __init__(self, cfg):
        """
        Initializes the plugin and its base classes.
        """
        # Initialize both parent classes. The order is important.
        AbstractScenarioPlugin.__init__(self, cfg)
        SnapshotDisruptionBase.__init__(self, cfg)
        
        # Set the logger now that the plugin is initialized.
        self.logger = logging.getLogger(f"{self.__class__.__name__}.{self._NAME}")

    @classmethod
    def get_scenario_types(cls):
        """
        Returns the unique scenario type that this plugin registers with
        the scenario plugin factory.
        """
        return ["cnv_snapshot_disruption_scenarios"]

    def execute_test_logic(self):
        """
        Contains the chaos logic specific to disrupting snapshot creation.
        
        This method is called by the `run` method of the base class and will
        raise an exception if any of its critical steps fail.
        """

        # Step 1: Initiate the snapshot
        self.logger.info(f"Initiating snapshot '{self.snapshot_name}'...")
        if not self._create_snapshot():
            raise Exception("Failed to initiate the VM snapshot.")

        self.logger.info(
            f"Snapshot creation initiated. Waiting for {self.snapshot_creation_wait_time} "
            "seconds before disrupting the controller."
        )
        time.sleep(self.snapshot_creation_wait_time)

        # Step 2: Disrupt the snapshot controller
        self.logger.info("Killing the snapshot controller pod...")
        if not self._kill_snapshot_controller():
            self.logger.warning(
                "Failed to kill the snapshot controller pod. The test will continue."
            )
        else:
            self.logger.info("Snapshot controller pod deleted successfully.")

        # Step 3: Verify that the snapshot completes successfully
        self.logger.info("Verifying that the snapshot completes successfully...")
        if not self._verify_snapshot_created():
            raise Exception(
                "Scenario Failed: The VM snapshot did not complete successfully "
                "after the controller was disrupted."
            )

