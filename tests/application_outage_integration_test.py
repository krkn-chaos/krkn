import logging
import yaml
import time
import os
import random
import string
import tempfile
import subprocess
from unittest.mock import MagicMock
from krkn.scenario_plugins.application_outage.application_outage_scenario_plugin import ApplicationOutageScenarioPlugin

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s',
                   datefmt='%Y-%m-%d %H:%M:%S')

class MockK8sLib:
    def create_net_policy(self, yaml_spec, namespace):
        logging.info(f"Creating NetworkPolicy in namespace {namespace}")
        logging.info(f"Policy spec: {yaml_spec}")
        return True
        
    def delete_net_policy(self, policy_name, namespace):
        logging.info(f"Deleting NetworkPolicy {policy_name} in namespace {namespace}")
        return True

class MockLibTelemetry:
    def __init__(self):
        self.k8s_lib = MockK8sLib()
        
    def get_lib_kubernetes(self):
        return self.k8s_lib

def generate_random_string(length=5):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def run_mock_test():
    """Run the plugin with mock K8s objects"""
    # Initialize the plugin
    plugin = ApplicationOutageScenarioPlugin()
    
    # Create mock objects
    mock_lib_telemetry = MockLibTelemetry()
    mock_scenario_telemetry = MagicMock()
    
    # Configuration for the plugin
    krkn_config = {
        "tunings": {
            "wait_duration": 5
        },
        "cerberus": {
            "cerberus_enabled": False
        }
    }
    
    # Create a test scenario file
    scenario_file = create_test_scenario()
    
    # Run the plugin
    logging.info(f"Running application outage plugin with scenario from {scenario_file}")
    result = plugin.run(
        run_uuid="test-uuid",
        scenario=scenario_file,
        krkn_config=krkn_config,
        lib_telemetry=mock_lib_telemetry,
        scenario_telemetry=mock_scenario_telemetry
    )
    
    # Clean up
    os.unlink(scenario_file)
    
    # Return result
    return result

def create_test_scenario():
    """Create a temporary test scenario file"""
    scenario_data = {
        "application_outage": {
            "namespace": "default",
            "pod_selector": {
                "app": "nginx",
                "test-selector": "true"
            },
            "block": ["Ingress"],
            "duration": 30
        }
    }
    
    # Create a temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.yaml')
    yaml.dump(scenario_data, temp_file)
    temp_file.close()
    
    return temp_file.name

def run_kubernetes_test(kubeconfig_path=None):
    """Run test with real Kubernetes if available"""
    try:
        from krkn_lib.models.telemetry import ScenarioTelemetry
        from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
        from krkn_lib.k8s import KrknKubernetes
        from krkn_lib.ocp import KrknOpenshift
        from krkn_lib.utils.safe_logger import SafeLogger
        
        # Use provided kubeconfig or default
        if not kubeconfig_path:
            kubeconfig_path = os.path.expanduser("~/.kube/config")
        
        logging.info(f"Using kubeconfig at: {kubeconfig_path}")
        
        # Create kubernetes clients
        kubecli = KrknKubernetes(kubeconfig_path=kubeconfig_path)
        opencli = KrknOpenshift(kubeconfig_path=kubeconfig_path)
        safe_logger = SafeLogger()
        
        # Create telemetry objects
        telemetry = KrknTelemetryOpenshift(safe_logger, opencli)
        scenario_telemetry = ScenarioTelemetry()
        
        # Config with required settings
        krkn_config = {
            "tunings": {
                "wait_duration": 10
            },
            "cerberus": {
                "cerberus_enabled": False
            }
        }
        
        # Initialize the plugin
        plugin = ApplicationOutageScenarioPlugin()
        
        # Create test scenario
        scenario_file = create_test_scenario()
        
        # Run the plugin
        logging.info("Running application outage plugin with real Kubernetes")
        result = plugin.run(
            run_uuid="test-k8s-run",
            scenario=scenario_file,
            krkn_config=krkn_config,
            lib_telemetry=telemetry,
            scenario_telemetry=scenario_telemetry
        )
        
        # Clean up
        os.unlink(scenario_file)
        
        return result
    except ImportError as e:
        logging.error(f"Required Kubernetes libraries not available: {e}")
        return None
    except Exception as e:
        logging.error(f"Error running Kubernetes test: {e}")
        return None

def verify_kubernetes_integration():
    """Run verification with kubectl if available"""
    try:
        # Clean up any existing resources first
        logging.info("Cleaning up any existing test resources...")
        subprocess.run(
            "kubectl delete deployment nginx-test --ignore-not-found",
            shell=True, check=True
        )
        subprocess.run(
            "kubectl delete service nginx-service --ignore-not-found",
            shell=True, check=True
        )
        
        # Give Kubernetes a moment to clean up
        time.sleep(2)
        
        # Test 1: Create a test deployment
        logging.info("Creating test deployment...")
        subprocess.run(
            "kubectl create deployment nginx-test --image=nginx",
            shell=True, check=True
        )
        
        # Add labels in a separate command
        logging.info("Adding labels to deployment...")
        subprocess.run(
            "kubectl label deployment nginx-test app=nginx test-selector=true --overwrite",
            shell=True, check=True
        )
        
        # Test 2: Expose the deployment
        logging.info("Exposing deployment as a service...")
        subprocess.run(
            "kubectl expose deployment nginx-test --port=80 --name=nginx-service",
            shell=True, check=True
        )
        
        # Test 3: Run the application outage test
        result = run_kubernetes_test()
        
        # Test 4: Verify connectivity (should be restored after test)
        logging.info("Verifying connectivity after test...")
        subprocess.run(
            "kubectl run -i --rm test-pod --image=busybox --restart=Never -- wget -O- nginx-service",
            shell=True, check=True
        )
        
        # Clean up
        logging.info("Cleaning up test resources...")
        subprocess.run("kubectl delete service nginx-service --ignore-not-found", shell=True)
        subprocess.run("kubectl delete deployment nginx-test --ignore-not-found", shell=True)
        
        return result == 0
    except subprocess.CalledProcessError:
        logging.error("Kubernetes commands failed - cluster may not be available")
        # Clean up even if there was an error
        subprocess.run("kubectl delete service nginx-service --ignore-not-found", shell=True)
        subprocess.run("kubectl delete deployment nginx-test --ignore-not-found", shell=True)
        return False
    except Exception as e:
        logging.error(f"Error during verification: {e}")
        # Clean up even if there was an error
        subprocess.run("kubectl delete service nginx-service --ignore-not-found", shell=True)
        subprocess.run("kubectl delete deployment nginx-test --ignore-not-found", shell=True)
        return False

if __name__ == "__main__":
    # First try the mock test
    logging.info("Running mock test...")
    mock_result = run_mock_test()
    if mock_result == 0:
        logging.info("✅ Mock test passed")
    else:
        logging.error("❌ Mock test failed")
    
    # Then try with Kubernetes if available
    logging.info("Attempting to run with real Kubernetes...")
    k8s_result = verify_kubernetes_integration()
    if k8s_result:
        logging.info("✅ Kubernetes integration test passed")
    else:
        logging.info("❓ Kubernetes integration test unavailable or failed")
