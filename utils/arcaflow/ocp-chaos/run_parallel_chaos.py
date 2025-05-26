import asyncio
import yaml
import argparse
from typing import Dict, Any, Callable
from utils.workflow_executor import WorkflowExecutor
from utils.logging import WorkflowLogger

# Import Krkn modules
from krkn.krkn import Krkn
from krkn.krkn_lib.k8s import KrknKubernetes
from krkn.krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn.krkn_lib.telemetry.ocm import KrknTelemetryOCM
from krkn.krkn_lib.telemetry.psap import KrknTelemetryPSAP
from krkn.krkn_lib.telemetry.telemetry import KrknTelemetry
from krkn.krkn_lib.utils import KrknScenarioUtils
from krkn.krkn_lib.utils.functions import log_exception
from krkn.krkn_lib.utils.signal_handler import SignalHandler

async def load_config(config_path: str) -> Dict[str, Any]:
    """Load and validate the configuration file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        raise Exception(f"Failed to load config file: {str(e)}")

async def run_kubeburner(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run kubeburner workload using Krkn's native implementation."""
    try:
        # Initialize Krkn
        krkn = Krkn()
        k8s = KrknKubernetes()
        telemetry = KrknTelemetry(k8s)
        
        # Extract kubeburner configuration
        kubeburner_config = config.get('kubeburner', {})
        
        # Run kubeburner workload
        result = await krkn.run_kubeburner(
            workload=kubeburner_config.get('workload', 'cluster-density'),
            qps=kubeburner_config.get('qps', 20),
            burst=kubeburner_config.get('burst', 20),
            timeout=kubeburner_config.get('timeout', '5m'),
            iterations=kubeburner_config.get('iterations', 1),
            churn=kubeburner_config.get('churn', False),
            churn_duration=kubeburner_config.get('churn_duration', '30s'),
            churn_delay=kubeburner_config.get('churn_delay', '10s'),
            churn_percent=kubeburner_config.get('churn_percent', 20)
        )
        
        return {
            'status': 'success',
            'output': result,
            'config': kubeburner_config
        }
    except Exception as e:
        raise Exception(f"Failed to run kubeburner: {str(e)}")

async def run_pod_chaos(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run pod chaos scenarios using Krkn's native implementation."""
    try:
        # Initialize Krkn
        krkn = Krkn()
        k8s = KrknKubernetes()
        telemetry = KrknTelemetry(k8s)
        
        # Extract pod chaos configuration
        pod_chaos_config = config.get('pod_chaos', {})
        
        # Run pod chaos scenario
        result = await krkn.run_pod_chaos(
            namespace_pattern=pod_chaos_config.get('namespace_pattern', '^openshift-etcd$'),
            label_selector=pod_chaos_config.get('label_selector', 'k8s-app=etcd'),
            kill_count=pod_chaos_config.get('kill', 1),
            recovery_time=pod_chaos_config.get('krkn_pod_recovery_time', 60),
            timeout=pod_chaos_config.get('timeout', 180)
        )
        
        return {
            'status': 'success',
            'output': result,
            'config': pod_chaos_config
        }
    except Exception as e:
        raise Exception(f"Failed to run pod chaos: {str(e)}")

async def run_cpu_hog(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run CPU hog scenarios using Krkn's native implementation."""
    try:
        # Initialize Krkn
        krkn = Krkn()
        k8s = KrknKubernetes()
        telemetry = KrknTelemetry(k8s)
        
        # Extract CPU hog configuration
        cpu_hog_config = config.get('cpu_hog', {})
        stressng_params = cpu_hog_config.get('stressng_params', {})
        
        # Run CPU hog scenario
        result = await krkn.run_cpu_hog(
            namespace=cpu_hog_config.get('namespace', 'default'),
            node_selector=cpu_hog_config.get('node_selector', 'node-role.kubernetes.io/worker='),
            timeout=stressng_params.get('timeout', 300),
            workers=stressng_params.get('workers', 2),
            cpu_load=stressng_params.get('cpu-load', 50),
            cpu_method=stressng_params.get('cpu-method', 'all')
        )
        
        return {
            'status': 'success',
            'output': result,
            'config': cpu_hog_config
        }
    except Exception as e:
        raise Exception(f"Failed to run CPU hog: {str(e)}")

def create_workflow_config(name: str, enabled: bool, func: Callable, config: Dict[str, Any]) -> Dict[str, Any]:
    """Create a workflow configuration dictionary."""
    return {
        'enabled': enabled,
        'workflow_func': func,
        'config': config
    }

async def main():
    parser = argparse.ArgumentParser(description='Run parallel chaos scenarios')
    parser.add_argument('-c', '--config', required=True, help='Path to config file')
    parser.add_argument('-l', '--log-file', default='workflow.log', help='Path to log file')
    args = parser.parse_args()

    # Initialize logger
    logger = WorkflowLogger(args.log_file)
    
    try:
        # Load configuration
        config = await load_config(args.config)
        logger.log_metric("main", "config_loaded", True)

        # Initialize workflow executor with continuous load support
        executor = WorkflowExecutor(
            max_workers=config.get('max_parallel_workflows', 3),
            timeout=config.get('workflow_timeout', 3600),
            continuous_load=config.get('continuous_load', False),
            load_churn_interval=config.get('load_churn_interval', 300)
        )

        # Prepare load workflow if continuous load is enabled
        load_workflow = None
        if config.get('continuous_load', False):
            load_workflow = create_workflow_config(
                'continuous_load',
                True,
                run_kubeburner,
                config.get('kubeburner_list', [])
            )

        # Prepare chaos workflows
        workflows = {
            'kubeburner': create_workflow_config(
                'kubeburner',
                config.get('kubeburner_enabled', True),
                run_kubeburner,
                config.get('kubeburner_list', [])
            ),
            'pod_chaos': create_workflow_config(
                'pod_chaos',
                config.get('pod_chaos_enabled', True),
                run_pod_chaos,
                config.get('pod_chaos_list', [])
            ),
            'cpu_hog': create_workflow_config(
                'cpu_hog',
                config.get('cpu_hog_enabled', True),
                run_cpu_hog,
                config.get('cpu_hog_list', [])
            )
        }

        # Execute workflows with continuous load if enabled
        await executor.execute_workflows(workflows, load_workflow)

        # Get final status
        status = executor.get_all_workflow_statuses()
        logger.log_metric("main", "final_status", status)

        # Check for failures
        failed_workflows = [
            name for name, status in status.items()
            if status and status.get('status') == 'failed'
        ]
        
        if failed_workflows:
            logger.log_warning(
                "main",
                f"Some workflows failed: {', '.join(failed_workflows)}"
            )
            return 1

        logger.log_metric("main", "execution_completed", True)
        return 0

    except Exception as e:
        logger.log_error("main", e)
        return 1
    finally:
        if 'executor' in locals():
            executor.cleanup()

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    exit(exit_code) 