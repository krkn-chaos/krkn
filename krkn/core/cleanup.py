#!/usr/bin/env python
"""
Cleanup manager for Krkn. This module provides a centralized mechanism for registering and executing
cleanup callbacks when Krkn terminates due to signals, exceptions, or normal exit.
"""

import signal
import atexit
import sys
import os
import subprocess
import logging
import datetime
from typing import Callable, List, Optional


class CleanupManager:
    """    
    This class handles registering signal handlers, exit handlers, and exception hooks
    to ensure cleanup functions are called exactly once during termination, regardless
    of how the termination occurs (Ctrl+C, kill signal, exception, or normal exit).
    
    It also captures diagnostic information to help with debugging.
    """
    
    def __init__(self, artifacts_dir: Optional[str] = None):
        """
        Initialization of the cleanup manager.
        
        Args:
            artifacts_dir: Directory where diagnostic artifacts will be stored.
                           If None, a default timestamped directory will be created.
        """
        self._cleanup_funcs = []
        self._done = False
        
        if artifacts_dir is None:
            run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.artifacts_dir = os.path.abspath(os.path.join("artifacts", f"krkn-run-{run_id}"))
        else:
            self.artifacts_dir = os.path.abspath(artifacts_dir)
            
        os.makedirs(self.artifacts_dir, exist_ok=True)
        logging.info(f"Artifacts will be stored in: {self.artifacts_dir}")
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        atexit.register(self._run_cleanup)
        
        sys.excepthook = self._exception_handler

    def register_cleanup(self, func: Callable) -> None:
        """
        Register a cleanup callback function.
        
        Args:
            func: A callable that will be invoked during cleanup.
                  This is a scenario.cleanup() method.
        """
        if callable(func):
            self._cleanup_funcs.append(func)
            logging.debug(f"Registered cleanup function: {func.__qualname__ if hasattr(func, '__qualname__') else str(func)}")

    def _signal_handler(self, signum: int, frame) -> None:
        #TODO: frame is not used
        """
        Called when a signal (SIGINT/SIGTERM) is received.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logging.info(f"Received signal {signum}, initiating cleanup...")
        self._run_cleanup()
        sys.exit(128 + signum)  # exit code indicating the signal

    def _exception_handler(self, exc_type, exc_value, exc_traceback) -> None:
        """
        Called on uncaught exception to ensure cleanup before handling.
        
        Args:
            exc_type: Exception type
            exc_value: Exception value
            exc_traceback: Exception traceback
        """
        logging.error(f"Unhandled exception ({exc_type.__name__}): {exc_value}")
        self._run_cleanup()
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _run_cleanup(self) -> None:
        """
        Execute all registered cleanup functions once.
        
        This method ensures cleanup runs once even if triggered from multiple sources.
        After running all cleanup callbacks, it captures diagnostic info.
        """
        if self._done:
            return
        
        self._done = True
        logging.info("Running cleanup callbacks...")
        
        for func in list(self._cleanup_funcs):
            try:
                func()
                logging.info(f"Successfully executed cleanup function: {func.__qualname__ if hasattr(func, '__qualname__') else str(func)}")
            except Exception as e:
                logging.error(f"Error during cleanup function {func.__qualname__ if hasattr(func, '__qualname__') else str(func)}: {e}")
        
        self._capture_diagnostics()
        
        logging.info(f"Cleanup completed. Artifacts saved to {self.artifacts_dir}")

   