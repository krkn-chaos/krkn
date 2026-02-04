from typing import Dict, Any, Optional
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
    _stop_event: threading.Event = None
    
    # Thread-local storage for context
    _local = threading.local()

    @classmethod
    def get_stop_event(cls) -> threading.Event:
        """Get or create the stop event for graceful thread cancellation."""
        if cls._stop_event is None:
            cls._stop_event = threading.Event()
        return cls._stop_event

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
        """Handle signals - set stop event and raise KeyboardInterrupt for graceful exit."""
        signal_name = signal.Signals(signum).name
        
        # Set the stop event to signal all threads to terminate
        if cls._stop_event is not None:
            cls._stop_event.set()
        
        # Log warning and skip rollback - let the scenario handle graceful exit
        logger.warning(f"Signal {signal_name} received without complete context, skipping rollback.")
        
        # Clear context
        run_uuid, scenario_type, telemetry_ocp = cls._get_context()
        if telemetry_ocp:
            cls._set_context(None, None, telemetry_ocp)
        
        # Raise KeyboardInterrupt for graceful exit
        raise KeyboardInterrupt()

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