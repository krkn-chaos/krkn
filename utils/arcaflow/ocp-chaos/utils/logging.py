import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional

class WorkflowLogger:
    def __init__(self, log_file: str = "workflow.log"):
        self.logger = logging.getLogger("workflow")
        self.logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.workflow_start_time = datetime.now()
        self.workflow_metrics: Dict[str, Any] = {
            "start_time": self.workflow_start_time.isoformat(),
            "workflows": {},
            "errors": [],
            "warnings": []
        }

    def _serialize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Remove non-serializable objects from config."""
        serializable_config = {}
        for key, value in config.items():
            if key != 'workflow_func':  # Skip function objects
                if isinstance(value, dict):
                    serializable_config[key] = self._serialize_config(value)
                elif isinstance(value, (str, int, float, bool, list)):
                    serializable_config[key] = value
        return serializable_config

    def log_workflow_start(self, workflow_name: str, config: Dict[str, Any]) -> None:
        """Log the start of a workflow with its configuration."""
        serializable_config = self._serialize_config(config)
        self.workflow_metrics["workflows"][workflow_name] = {
            "start_time": datetime.now().isoformat(),
            "config": serializable_config,
            "status": "running"
        }
        self.logger.info(f"Starting workflow: {workflow_name}")
        self.logger.debug(f"Workflow config: {json.dumps(serializable_config, indent=2)}")

    def log_workflow_end(self, workflow_name: str, status: str, 
                        duration: Optional[float] = None) -> None:
        """Log the end of a workflow with its status and duration."""
        if workflow_name in self.workflow_metrics["workflows"]:
            self.workflow_metrics["workflows"][workflow_name].update({
                "end_time": datetime.now().isoformat(),
                "status": status,
                "duration": duration
            })
        self.logger.info(f"Workflow {workflow_name} ended with status: {status}")

    def log_error(self, workflow_name: str, error: Exception, 
                  context: Optional[Dict[str, Any]] = None) -> None:
        """Log an error that occurred during workflow execution."""
        serializable_context = self._serialize_config(context) if context else {}
        error_info = {
            "workflow": workflow_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now().isoformat(),
            "context": serializable_context
        }
        self.workflow_metrics["errors"].append(error_info)
        self.logger.error(f"Error in workflow {workflow_name}: {str(error)}")
        if context:
            self.logger.debug(f"Error context: {json.dumps(serializable_context, indent=2)}")

    def log_warning(self, workflow_name: str, message: str, 
                   context: Optional[Dict[str, Any]] = None) -> None:
        """Log a warning during workflow execution."""
        serializable_context = self._serialize_config(context) if context else {}
        warning_info = {
            "workflow": workflow_name,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "context": serializable_context
        }
        self.workflow_metrics["warnings"].append(warning_info)
        self.logger.warning(f"Warning in workflow {workflow_name}: {message}")
        if context:
            self.logger.debug(f"Warning context: {json.dumps(serializable_context, indent=2)}")

    def log_metric(self, workflow_name: str, metric_name: str, 
                  value: Any) -> None:
        """Log a metric for a workflow."""
        if workflow_name in self.workflow_metrics["workflows"]:
            if "metrics" not in self.workflow_metrics["workflows"][workflow_name]:
                self.workflow_metrics["workflows"][workflow_name]["metrics"] = {}
            self.workflow_metrics["workflows"][workflow_name]["metrics"][metric_name] = value
            self.logger.info(f"Metric for {workflow_name} - {metric_name}: {value}")

    def get_workflow_summary(self) -> Dict[str, Any]:
        """Get a summary of all workflows and their status."""
        summary = {
            "total_workflows": len(self.workflow_metrics["workflows"]),
            "completed_workflows": sum(1 for w in self.workflow_metrics["workflows"].values() 
                                    if w.get("status") == "completed"),
            "failed_workflows": sum(1 for w in self.workflow_metrics["workflows"].values() 
                                  if w.get("status") == "failed"),
            "total_errors": len(self.workflow_metrics["errors"]),
            "total_warnings": len(self.workflow_metrics["warnings"]),
            "workflows": self.workflow_metrics["workflows"]
        }
        return summary

    def save_metrics(self, file_path: str) -> None:
        """Save workflow metrics to a file."""
        try:
            with open(file_path, 'w') as f:
                json.dump(self.workflow_metrics, f, indent=2)
            self.logger.info(f"Workflow metrics saved to {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to save metrics: {str(e)}") 