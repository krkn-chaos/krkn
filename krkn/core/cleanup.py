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
    Manages cleanup operations for Krkn.
    
    This class handles registering signal handlers, exit handlers, and exception hooks
    to ensure cleanup functions are called during termination.
    
    Implementted capturing of diagnostic information to help with debugging.
    """
    
    def __init__(self, artifacts_dir: Optional[str] = None):
        """
        Initialization ofthe cleanup manager.
        
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

   