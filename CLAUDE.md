# CLAUDE.md - Krkn Chaos Engineering Framework

## Project Overview

Krkn (Kraken) is a chaos engineering tool for Kubernetes/OpenShift clusters. It injects deliberate failures to validate cluster resilience. Plugin-based architecture with multi-cloud support (AWS, Azure, GCP, IBM Cloud, VMware, Alibaba, OpenStack).

## Repository Structure

```
krkn/
├── krkn/
│   ├── scenario_plugins/        # Chaos scenario plugins (pod, node, network, hogs, etc.)
│   ├── utils/                   # Utility functions
│   ├── rollback/                # Rollback management
│   ├── prometheus/              # Prometheus integration
│   └── cerberus/                # Health monitoring
├── tests/                       # Unit tests (unittest framework)
├── scenarios/                   # Example scenario configs (openshift/, kube/, kind/)
├── config/                      # Configuration files
└── CI/                          # CI/CD test scripts
```

## Quick Start

```bash
# Setup (ALWAYS use virtual environment)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run Krkn
python run_kraken.py --config config/config.yaml

# Note: Scenarios are specified in config.yaml under kraken.chaos_scenarios
# There is no --scenario flag; edit config/config.yaml to select scenarios

# Run tests
python -m unittest discover -s tests -v
python -m coverage run -a -m unittest discover -s tests -v
```

## Critical Requirements

### Python Environment
- **Python 3.9+** required
- **NEVER install packages globally** - always use virtual environment
- **CRITICAL**: `docker` must be <7.0 and `requests` must be <2.32 (Unix socket compatibility)

### Key Dependencies
- **krkn-lib** (5.1.13): Core library for Kubernetes/OpenShift operations
- **kubernetes** (34.1.0): Kubernetes Python client
- **docker** (<7.0), **requests** (<2.32): DO NOT upgrade without verifying compatibility
- Cloud SDKs: boto3 (AWS), azure-mgmt-* (Azure), google-cloud-compute (GCP), ibm_vpc (IBM), pyVmomi (VMware)

## Plugin Architecture (CRITICAL)

**Strictly enforced naming conventions:**

### Naming Rules
- **Module files**: Must end with `_scenario_plugin.py` and use snake_case
  - Example: `pod_disruption_scenario_plugin.py`
- **Class names**: Must be CamelCase and end with `ScenarioPlugin`
  - Example: `PodDisruptionScenarioPlugin`
  - Must match module filename (snake_case ↔ CamelCase)
- **Directory structure**: Plugin dirs CANNOT contain "scenario" or "plugin"
  - Location: `krkn/scenario_plugins/<plugin_name>/`

### Plugin Implementation
Every plugin MUST:
1. Extend `AbstractScenarioPlugin`
2. Implement `run()` method
3. Implement `get_scenario_types()` method

```python
from krkn.scenario_plugins import AbstractScenarioPlugin

class PodDisruptionScenarioPlugin(AbstractScenarioPlugin):
    def run(self, config, scenarios_list, kubeconfig_path, wait_duration):
        pass
    
    def get_scenario_types(self):
        return ["pod_scenarios", "pod_outage"]
```

### Creating a New Plugin
1. Create directory: `krkn/scenario_plugins/<plugin_name>/`
2. Create module: `<plugin_name>_scenario_plugin.py`
3. Create class: `<PluginName>ScenarioPlugin` extending `AbstractScenarioPlugin`
4. Implement `run()` and `get_scenario_types()`
5. Create unit test: `tests/test_<plugin_name>_scenario_plugin.py`
6. Add example scenario: `scenarios/<platform>/<scenario>.yaml`

**DO NOT**: Violate naming conventions (factory will reject), include "scenario"/"plugin" in directory names, create plugins without tests.

## Testing

### Unit Tests
```bash
# Run all tests
python -m unittest discover -s tests -v

# Specific test
python -m unittest tests.test_pod_disruption_scenario_plugin

# With coverage
python -m coverage run -a -m unittest discover -s tests -v
python -m coverage html
```

**Test requirements:**
- Naming: `test_<module>_scenario_plugin.py`
- Mock external dependencies (Kubernetes API, cloud providers)
- Test success, failure, and edge cases
- Keep tests isolated and independent

### Functional Tests
Located in `CI/tests/`. Can be run locally on a kind cluster with Prometheus and Elasticsearch set up.

**Setup for local testing:**
1. Deploy Prometheus and Elasticsearch on your kind cluster:
   - Prometheus setup: https://krkn-chaos.dev/docs/developers-guide/testing-changes/#prometheus
   - Elasticsearch setup: https://krkn-chaos.dev/docs/developers-guide/testing-changes/#elasticsearch

2. Or disable monitoring features in `config/config.yaml`:
   ```yaml
   performance_monitoring:
       enable_alerts: False
       enable_metrics: False
       check_critical_alerts: False
   ```

**Note:** Functional tests run automatically in CI with full monitoring enabled.

## Cloud Provider Implementations

Node chaos scenarios are cloud-specific. Each in `krkn/scenario_plugins/node_actions/<provider>_node_scenarios.py`:
- AWS, Azure, GCP, IBM Cloud, VMware, Alibaba, OpenStack, Bare Metal

Implement: stop, start, reboot, terminate instances.

**When modifying**: Maintain consistency with other providers, handle API errors, add logging, update tests.

### Adding Cloud Provider Support
1. Create: `krkn/scenario_plugins/node_actions/<provider>_node_scenarios.py`
2. Extend: `abstract_node_scenarios.AbstractNodeScenarios`
3. Implement: `stop_instances`, `start_instances`, `reboot_instances`, `terminate_instances`
4. Add SDK to `requirements.txt`
5. Create unit test with mocked SDK
6. Add example scenario: `scenarios/openshift/<provider>_node_scenarios.yml`

## Configuration

**Main config**: `config/config.yaml`
- `kraken`: Core settings
- `cerberus`: Health monitoring
- `performance_monitoring`: Prometheus
- `elastic`: Elasticsearch telemetry

**Scenario configs**: `scenarios/` directory
```yaml
- config:
    scenario_type: <type>  # Must match plugin's get_scenario_types()
```

## Code Style

- **Import order**: Standard library, third-party, local imports
- **Naming**: snake_case (functions/variables), CamelCase (classes)
- **Logging**: Use Python's `logging` module
- **Error handling**: Return appropriate exit codes
- **Docstrings**: Required for public functions/classes

## Exit Codes

Krkn uses specific exit codes to communicate execution status:

- `0`: Success - all scenarios passed, no critical alerts
- `1`: Scenario failure - one or more scenarios failed
- `2`: Critical alerts fired during execution
- `3+`: Health check failure (Cerberus monitoring detected issues)

**When implementing scenarios:**
- Return `0` on success
- Return `1` on scenario-specific failures
- Propagate health check failures appropriately
- Log exit code reasons clearly

## Container Support

Krkn can run inside a container. See `containers/` directory.

**Building custom image:**
```bash
cd containers
./compile_dockerfile.sh  # Generates Dockerfile from template
docker build -t krkn:latest .
```

**Running containerized:**
```bash
docker run -v ~/.kube:/root/.kube:Z \
  -v $(pwd)/config:/config:Z \
  -v $(pwd)/scenarios:/scenarios:Z \
  krkn:latest
```

## Git Workflow

- **NEVER commit directly to main**
- **NEVER use `--force` without approval**
- **ALWAYS create feature branches**: `git checkout -b feature/description`
- **ALWAYS run tests before pushing**

**Conventional commits**: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`

```bash
git checkout main && git pull origin main
git checkout -b feature/your-feature-name
# Make changes, write tests
python -m unittest discover -s tests -v
git add <specific-files>
git commit -m "feat: description"
git push -u origin feature/your-feature-name
```

## Environment Variables

- `KUBECONFIG`: Path to kubeconfig
- `AWS_*`, `AZURE_*`, `GOOGLE_APPLICATION_CREDENTIALS`: Cloud credentials
- `PROMETHEUS_URL`, `ELASTIC_URL`, `ELASTIC_PASSWORD`: Monitoring config

**NEVER commit credentials or API keys.**

## Common Pitfalls

1. Missing virtual environment - always activate venv
2. Running functional tests without cluster setup
3. Ignoring exit codes
4. Modifying krkn-lib directly (it's a separate package)
5. Upgrading docker/requests beyond version constraints

## Before Writing Code

1. Check for existing implementations
2. Review existing plugins as examples
3. Maintain consistency with cloud provider patterns
4. Plan rollback logic
5. Write tests alongside code
6. Update documentation

## When Adding Dependencies

1. Check if functionality exists in krkn-lib or current dependencies
2. Verify compatibility with existing versions
3. Pin specific versions in `requirements.txt`
4. Check for security vulnerabilities
5. Test thoroughly for conflicts

## Common Development Tasks

### Modifying Existing Plugin
1. Read plugin code and corresponding test
2. Make changes
3. Update/add unit tests
4. Run: `python -m unittest tests.test_<plugin>_scenario_plugin`

### Writing Unit Tests
1. Create: `tests/test_<module>_scenario_plugin.py`
2. Import `unittest` and plugin class
3. Mock external dependencies
4. Test success, failure, and edge cases
5. Run: `python -m unittest tests.test_<module>_scenario_plugin`

