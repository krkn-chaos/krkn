# Import standard libraries
import logging
import time

from krkn.scenario_plugins.abstract_scenario_plugin import \
    AbstractScenarioPlugin

from .snapshot_disruption_base import SnapshotDisruptionBase


class SnapshotCreationDisruptionScenarioPlugin(
    SnapshotDisruptionBase, AbstractScenarioPlugin
):
    """
    Implements a chaos scenario that disrupts the VM snapshot creation process.

    The scenario tests the resilience of the snapshotting mechanism by killing the
    snapshot controller partway through the creation of a VolumeSnapshot.
    The primary success criterion is that the snapshot eventually enters the
    'Ready' state, proving that the system can recover from a temporary
    controller outage.
    """

    _NAME = "snapshot_creation_disruption"

    def __init__(self, scenario_type: str = None):
        # Initialize the base classes in the correct order
        SnapshotDisruptionBase.__init__(self)
        AbstractScenarioPlugin.__init__(self, scenario_type)

    def get_scenario_types(self) -> list[str]:
        """
        Returns the unique scenario type that this plugin registers with
        the scenario plugin factory.
        """
        return ["cnv_snapshot_disruption_scenarios"]

    def execute_test_logic(self):
        """
        Executes the core logic of the snapshot creation disruption.

        Workflow:
        1. Initiates a VolumeSnapshot for the target VM.
        2. Waits for a configured duration (`snapshot_creation_wait_time`)
           to allow the creation process to begin.
        3. Kills the snapshot controller pod to simulate a controller failure.
        4. Polls and verifies that the VolumeSnapshot eventually becomes ready,
           confirming the system's ability to self-heal and complete the snapshot.

        Raises:
            Exception: If the snapshot fails to initiate or does not become
                       ready within the `snapshot_ready_timeout`.
        """

        # 1. Initiate the snapshot for the specified VM
        logging.info(
            f"Initiating snapshot '{self.snapshot_name}' for VM '{self.vm_name}'..."
        )
        if not self.k8s_client.create_snapshot(
            self.snapshot_name, self.vm_namespace, self.vm_name
        ):
            raise Exception(
                f"Failed to create VolumeSnapshot resource '{self.snapshot_name}' for VM '{self.vm_name}'."
            )

        # 2. Wait for a strategic moment before disrupting the controller
        logging.info(
            f"Waiting {self.snapshot_creation_wait_time}s before disrupting the snapshot controller..."
        )
        time.sleep(self.snapshot_creation_wait_time)

        # 3. Kill the snapshot controller to inject chaos
        logging.info("Attempting to disrupt the snapshot controller...")
        disruption_start_time = time.time()
        if not self._kill_snapshot_controller():
            # If the controller isn't found, the test cannot proceed with its core disruption.
            # This is treated as a failure because the intended chaos was not introduced.
            raise Exception(
                "Snapshot controller pod not found; disruption could not be performed."
            )
        else:
            logging.info("Snapshot controller pod successfully killed.")

        # 4. Key validation: Verify the snapshot eventually recovers and completes.
        # This confirms that even with the controller disruption, the snapshot
        # process is resilient enough to finish.
        logging.info(
            f"Verifying snapshot reaches 'Ready' state within {self.snapshot_ready_timeout}s..."
        )
        
        start_verify_time = time.time()
        while time.time() - start_verify_time < self.snapshot_ready_timeout:
            snap = self.k8s_client.get_snapshot(self.snapshot_name, self.vm_namespace)
            if snap and snap.get("status", {}).get("readyToUse"):
                recovery_time = time.time() - disruption_start_time
                logging.info(
                    f"Success: Snapshot is ready to use after controller disruption. "
                    f"Recovery took {recovery_time:.2f}s."
                )
                return
            time.sleep(5)

        # If the loop completes without returning, the snapshot failed to become ready.
        raise Exception(
            f"Timeout: Snapshot '{self.snapshot_name}' failed to become ready after controller disruption."
        )
