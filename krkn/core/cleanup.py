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

    def _capture_diagnostics(self) -> None:
        """
        Capture diagnostic info about the cluster.
        
        This method runs kubectl commands to gather information about pods, nodes, 
        and events, and saves them to files in the artifacts directory.
        """
        logging.info("Capturing diagnostic information...")
        
        try:
            self._run_and_save_command(["kubectl", "get", "pods", "-A", "-o", "wide"], "all-pods.txt")
            self._run_and_save_command(["kubectl", "get", "nodes", "-o", "wide"], "nodes.txt")
            self._run_and_save_command(["kubectl", "get", "events", "-A"], "events.txt")
            
            try:
                nodes_output = subprocess.run(
                    ["kubectl", "get", "nodes", "-o", "name"], 
                    capture_output=True, 
                    text=True,
                    check=True
                )
                
                for node in nodes_output.stdout.strip().split('\n'):
                    if node:  # Skip empty lines
                        node_name = node.replace('node/', '')
                        self._run_and_save_command(
                            ["kubectl", "describe", "node", node_name],
                            f"node-{node_name}-details.txt"
                        )
            except subprocess.CalledProcessError as e:
                logging.error(f"Error getting node details: {e}")
                
        except Exception as e:
            logging.error(f"Error capturing diagnostics: {e}")

    def _run_and_save_command(self, command: List[str], output_file: str) -> None:
        """
        Run a command and save its output to a file in the artifacts directory.
        
        Args:
            command: Command to run as a list of strings
            output_file: Filename to save the output to
        """
        try:
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True,
                check=True
            )
            
            output_path = os.path.join(self.artifacts_dir, output_file)
            with open(output_path, "w") as f:
                f.write(result.stdout)
                
            logging.debug(f"Saved output of '{' '.join(command)}' to {output_path}")
            
        except subprocess.CalledProcessError as e:
            logging.error(f"Command '{' '.join(command)}' failed with exit code {e.returncode}: {e.stderr}")
            output_path = os.path.join(self.artifacts_dir, f"error-{output_file}")
            with open(output_path, "w") as f:
                f.write(f"Command: {' '.join(command)}\n")
                f.write(f"Exit code: {e.returncode}\n")
                f.write(f"Stdout:\n{e.stdout}\n")
                f.write(f"Stderr:\n{e.stderr}\n")
