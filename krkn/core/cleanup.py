#!/usr/bin/env python
"""
Cleanup manager for Krkn. This module provides a centralized mechanism for registering and executing
cleanup callbacks when Krkn terminates due to signals, exceptions, or normal exit.
"""

import signal
import atexit
import sys
import os
import logging
import datetime
import json
from kubernetes import client
from typing import Callable, List, Optional, Dict, Any


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
        Capture diagnostic info about the cluster using the Kubernetes Python client API.
        
        This method collects information about pods, nodes, and events, 
        and saves them to files in the artifacts directory.
        """
        logging.info("Capturing diagnostic information...")
        
        try:
            # Use Kubernetes Python client instead of kubectl
            k8s_client = client.ApiClient()
            core_v1 = client.CoreV1Api(k8s_client)
            
            # Get all pods across all namespaces
            try:
                pods = core_v1.list_pod_for_all_namespaces(watch=False)
                pod_data = [{
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "node": pod.spec.node_name,
                    "ip": pod.status.pod_ip,
                    "creation_timestamp": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                } for pod in pods.items]
                self._save_json_data(pod_data, "all-pods.json")
            except Exception as e:
                logging.error(f"Error getting pod information: {e}")
            
            # Get all nodes
            try:
                nodes = core_v1.list_node(watch=False)
                node_data = [{
                    "name": node.metadata.name,
                    "status": [cond.type for cond in node.status.conditions if cond.status == 'True'],
                    "addresses": [addr.address for addr in node.status.addresses],
                    "kubelet_version": node.status.node_info.kubelet_version if node.status.node_info else None,
                    "creation_timestamp": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None
                } for node in nodes.items]
                self._save_json_data(node_data, "nodes.json")
                
                for node in nodes.items:
                    try:
                        node_detail = core_v1.read_node(node.metadata.name)
                        node_detail_dict = self._extract_node_details(node_detail)
                        self._save_json_data(
                            node_detail_dict,
                            f"node-{node.metadata.name}-details.json"
                        )
                    except Exception as node_err:
                        logging.error(f"Error getting details for node {node.metadata.name}: {node_err}")
            except Exception as e:
                logging.error(f"Error getting node information: {e}")
            
            try:
                events = core_v1.list_event_for_all_namespaces(watch=False)
                event_data = [{
                    "name": event.metadata.name,
                    "namespace": event.metadata.namespace,
                    "reason": event.reason,
                    "message": event.message,
                    "involved_object": {
                        "kind": event.involved_object.kind,
                        "name": event.involved_object.name,
                        "namespace": event.involved_object.namespace
                    },
                    "count": event.count,
                    "first_timestamp": event.first_timestamp.isoformat() if event.first_timestamp else None,
                    "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                    "type": event.type
                } for event in events.items]
                self._save_json_data(event_data, "events.json")
            except Exception as e:
                logging.error(f"Error getting event information: {e}")
        except Exception as e:
            logging.error(f"Error capturing diagnostics: {e}")
    
    def _extract_node_details(self, node) -> Dict[str, Any]:
        """Extract important details from a node object."""
        details = {
            "name": node.metadata.name,
            "labels": node.metadata.labels,
            "annotations": node.metadata.annotations,
            "creation_timestamp": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
            "status": {
                "conditions": [{
                    "type": cond.type,
                    "status": cond.status,
                    "reason": cond.reason,
                    "message": cond.message,
                    "last_transition_time": cond.last_transition_time.isoformat() if cond.last_transition_time else None
                } for cond in node.status.conditions],
                "capacity": node.status.capacity,
                "allocatable": node.status.allocatable,
                "addresses": [{
                    "type": addr.type,
                    "address": addr.address
                } for addr in node.status.addresses],
                "node_info": {
                    "machine_id": node.status.node_info.machine_id,
                    "system_uuid": node.status.node_info.system_uuid,
                    "boot_id": node.status.node_info.boot_id,
                    "kernel_version": node.status.node_info.kernel_version,
                    "os_image": node.status.node_info.os_image,
                    "container_runtime_version": node.status.node_info.container_runtime_version,
                    "kubelet_version": node.status.node_info.kubelet_version,
                    "kube_proxy_version": node.status.node_info.kube_proxy_version,
                    "operating_system": node.status.node_info.operating_system,
                    "architecture": node.status.node_info.architecture
                } if node.status.node_info else None
            },
            "spec": {
                "unschedulable": node.spec.unschedulable if hasattr(node.spec, 'unschedulable') else None,
                "taints": [{
                    "key": taint.key,
                    "value": taint.value,
                    "effect": taint.effect
                } for taint in node.spec.taints] if node.spec.taints else []
            }
        }
        return details

    def _save_json_data(self, data: Any, output_file: str) -> None:
        """
        Save data as JSON to a file in the artifacts directory.
        
        Args:
            data: Data to save (must be JSON serializable)
            output_file: Filename to save the data to
        """
        try:
            output_path = os.path.join(self.artifacts_dir, output_file)
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)
                
            logging.debug(f"Saved data to {output_path}")
            
        except Exception as e:
            logging.error(f"Error saving data to {output_file}: {e}")
            
            error_path = os.path.join(self.artifacts_dir, f"error-{output_file}")
            try:
                with open(error_path, "w") as f:
                    f.write(f"Error saving data: {str(e)}\n")
            except Exception:
                logging.error(f"Could not even save error information to {error_path}")
                pass
