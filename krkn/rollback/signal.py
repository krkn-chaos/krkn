from typing import Dict, Any, Optional, cast
import threading
import signal
import sys
import logging
from contextlib import contextmanager

from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift

from krkn.rollback.handler import execute_rollback_version_files

logger = logging.getLogger(__name__)

class SignalHandler:
    # Class-level variables for signal handling (shared across all instances)
    _signal_handlers_installed = False  # No need for thread-safe variable due to _signal_lock
    _original_handlers: Dict[int, Any] = {}
    _signal_lock = threading.Lock()
    
    # Thread-local storage for context
    _local = threading.local()

    @classmethod
    def _set_context(cls, run_uuid: str, scenario_type: str, telemetry_ocp: KrknTelemetryOpenshift):
        """Set the current execution context for this thread."""
        cls._local.run_uuid = run_uuid
        cls._local.scenario_type = scenario_type
        cls._local.telemetry_ocp = telemetry_ocp
        logger.debug(f"Set signal context set for thread {threading.current_thread().name} - run_uuid={run_uuid}, scenario_type={scenario_type}")

    @classmethod
    def _get_context(cls) -> tuple[Optional[str], Optional[str], Optional[KrknTelemetryOpenshift]]:
        """Get the current execution context for this thread."""
        run_uuid = getattr(cls._local, 'run_uuid', None)
        scenario_type = getattr(cls._local, 'scenario_type', None)
        telemetry_ocp = getattr(cls._local, 'telemetry_ocp', None)
        return run_uuid, scenario_type, telemetry_ocp

    @classmethod
    def _signal_handler(cls, signum: int, frame):
        """Handle signals with current thread context information."""
        signal_name = signal.Signals(signum).name
        run_uuid, scenario_type, telemetry_ocp = cls._get_context()
        if not run_uuid or not scenario_type or not telemetry_ocp:
            logger.warning(f"Signal {signal_name} received without complete context, skipping rollback.")
            return

        # Clear the context for the next signal, as another signal may arrive before the rollback completes.
        # This ensures that the rollback is performed only once.
        cls._set_context(None, None, telemetry_ocp)
        
        # Perform rollback
        logger.info(f"Performing rollback for signal {signal_name} with run_uuid={run_uuid}, scenario_type={scenario_type}")
        execute_rollback_version_files(telemetry_ocp, run_uuid, scenario_type)
        
        # Call original handler if it exists
        if signum not in cls._original_handlers:
            logger.debug(f"Signal {signal_name} has no registered handler, exiting...")
            sys.exit(1)

        original_handler = cls._original_handlers[signum]
        if callable(original_handler):
            logger.info(f"Calling original handler for {signal_name}")
            original_handler(signum, frame)
        elif original_handler == signal.SIG_DFL:
            # Restore default behavior
            logger.info(f"Restoring default signal handler for {signal_name}")
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)

    @classmethod
    def _register_signal_handler(cls):
        """Register signal handlers once (called by first instance)."""
        with cls._signal_lock:  # Lock protects _signal_handlers_installed from race conditions
            if cls._signal_handlers_installed:
                return
                
            signals_to_handle = [signal.SIGINT, signal.SIGTERM]
            if hasattr(signal, 'SIGHUP'):
                signals_to_handle.append(signal.SIGHUP)
            
            for sig in signals_to_handle:
                try:
                    original_handler = signal.signal(sig, cls._signal_handler)
                    cls._original_handlers[sig] = original_handler
                    logger.debug(f"SignalHandler: Registered signal handler for {signal.Signals(sig).name}")
                except (OSError, ValueError) as e:
                    logger.warning(f"AbstractScenarioPlugin: Could not register handler for signal {sig}: {e}")
            
            cls._signal_handlers_installed = True
            logger.info("Signal handlers registered globally")

    @classmethod
    @contextmanager
    def signal_context(cls, run_uuid: str, scenario_type: str, telemetry_ocp: KrknTelemetryOpenshift):
        """Context manager to set the signal context for the current thread."""
        cls._set_context(run_uuid, scenario_type, telemetry_ocp)
        cls._register_signal_handler()
        try:
            yield
        finally:
            # Clear context after exiting the context manager
            cls._set_context(None, None, telemetry_ocp)


signal_handler = SignalHandler()