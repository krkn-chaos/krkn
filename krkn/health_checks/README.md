# Health Check Plugin System

The health check plugin system provides a flexible, extensible architecture for implementing health checks in krkn. This system is modeled after the scenario plugin architecture and allows you to create reusable, independently testable health check implementations.

> **Note:** This is the current architecture for health checks in krkn. Legacy `HealthChecker` and `VirtChecker` classes have been removed and replaced with the plugin system. See [HEALTH_CHECK_MIGRATION_GUIDE.md](../../HEALTH_CHECK_MIGRATION_GUIDE.md) for migration details.

## Architecture Overview

The health check plugin system consists of three main components:

1. **AbstractHealthCheckPlugin** - Base class that all health check plugins must extend
2. **HealthCheckFactory** - Factory class that discovers and loads health check plugins
3. **Plugin Implementations** - Concrete implementations of health check logic

## File Structure

```
krkn/health_checks/
├── __init__.py                          # Module exports
├── abstract_health_check_plugin.py      # Abstract base class
├── health_check_factory.py              # Plugin factory
├── http_health_check_plugin.py          # HTTP health check implementation
├── virt_health_check_plugin.py          # KubeVirt VM health check implementation
├── simple_health_check_plugin.py        # Simple test plugin
└── README.md                            # This file
```

## Creating a Health Check Plugin

### Naming Conventions

To be automatically discovered by the factory, your plugin must follow these naming conventions:

1. **File name**: Must end with `_health_check_plugin.py`
   - Example: `http_health_check_plugin.py`, `database_health_check_plugin.py`

2. **Class name**: Must end with `HealthCheckPlugin` and be in CapitalCamelCase
   - Example: `HttpHealthCheckPlugin`, `DatabaseHealthCheckPlugin`
   - The file name in snake_case must match the class name in CapitalCamelCase

### Example Plugin

```python
"""
My Health Check Plugin

Description of what this plugin does.
"""

import logging
import queue
from typing import Any

from krkn.health_checks.abstract_health_check_plugin import AbstractHealthCheckPlugin


class MyHealthCheckPlugin(AbstractHealthCheckPlugin):
    """
    My custom health check implementation.
    """

    def __init__(
        self,
        health_check_type: str = "my_health_check",
        iterations: int = 1,
        **kwargs
    ):
        """
        Initialize the plugin.

        :param health_check_type: the health check type identifier
        :param iterations: number of chaos iterations to monitor
        :param kwargs: additional keyword arguments
        """
        super().__init__(health_check_type)
        self.iterations = iterations
        self.current_iterations = 0

    def get_health_check_types(self) -> list[str]:
        """
        Return the health check types this plugin handles.
        One plugin can handle multiple types.

        :return: list of health check type identifiers
        """
        return ["my_health_check", "my_custom_check"]

    def increment_iterations(self) -> None:
        """
        Increment the current iteration counter.
        Called by main run loop after each chaos scenario.

        :return: None
        """
        self.current_iterations += 1

    def run_health_check(
        self,
        config: dict[str, Any],
        telemetry_queue: queue.Queue,
    ) -> None:
        """
        Main health check logic.
        This runs in a separate thread and monitors health until
        self.current_iterations >= self.iterations.

        :param config: health check configuration from config.yaml
        :param telemetry_queue: queue to put telemetry data
        :return: None
        """
        while self.current_iterations < self.iterations:
            # Perform health check logic here
            logging.info("Running health check...")

            # If health check fails, set return value
            if some_failure_condition:
                self.set_return_value(2)

            # Sleep between checks
            time.sleep(config.get("interval", 5))

        # Put telemetry data in queue
        telemetry_queue.put({"status": "completed"})
```

## Using the Health Check Factory

### Basic Usage

```python
from krkn.health_checks import HealthCheckFactory, HealthCheckPluginNotFound

# Create factory instance (auto-discovers all plugins)
factory = HealthCheckFactory()

# List all loaded plugins
print(f"Available plugins: {list(factory.loaded_plugins.keys())}")

# List any failed plugins
for module, cls, error in factory.failed_plugins:
    print(f"Failed: {module} ({cls}): {error}")

# Create a plugin instance
try:
    plugin = factory.create_plugin(
        health_check_type="http_health_check",
        iterations=5
    )
except HealthCheckPluginNotFound as e:
    print(f"Plugin not found: {e}")
```

### Integration with Main Run Loop

```python
import queue
import threading

# Create plugin
factory = HealthCheckFactory()
plugin = factory.create_plugin("http_health_check", iterations=iterations)

# Create telemetry queue
telemetry_queue = queue.Queue()

# Start health check in background thread
health_check_thread = threading.Thread(
    target=plugin.run_health_check,
    args=(health_check_config, telemetry_queue)
)
health_check_thread.start()

# Run chaos scenarios
for iteration in range(iterations):
    # Run chaos scenario...

    # Increment health check iteration counter
    plugin.increment_iterations()

# Wait for health check thread to complete
health_check_thread.join()

# Retrieve telemetry
try:
    telemetry_data = telemetry_queue.get_nowait()
except queue.Empty:
    telemetry_data = None

# Check if health check failed
if plugin.get_return_value() != 0:
    logging.error("Health check failed")
    sys.exit(plugin.get_return_value())
```

## Plugin Threading Models

Health check plugins have different threading models depending on their implementation:

### HTTP Health Check Plugin (Continuous Monitoring)
The HTTP plugin runs continuously in a **background thread** and checks endpoints periodically:

```python
# HTTP plugin must run in a separate thread
health_check_worker = threading.Thread(
    target=health_checker.run_health_check,
    args=(health_check_config, health_check_telemetry_queue)
)
health_check_worker.start()
```

### Virt Health Check Plugin (Batch Processing)
The virt plugin **spawns its own worker threads** internally and returns immediately:

```python
# Virt plugin spawns threads internally - no wrapper thread needed
kubevirt_checker.run_health_check(kubevirt_check_config, kubevirt_check_telemetry_queue)
# Returns immediately after spawning worker threads
```

**Important:** When using the virt plugin, call `run_health_check()` directly (not `batch_list()`). The `run_health_check()` method:
1. Initializes from config (`_initialize_from_config()`)
2. Spawns worker threads (`batch_list()`)
3. Returns immediately while workers run in background

Calling `batch_list()` directly will fail because `vm_list` and `batch_size` are only populated during initialization.

## Configuration Format

Health check configuration in `config.yaml`:

```yaml
health_checks:
  type: http_health_check    # Must match plugin's get_health_check_types()
  interval: 2                # Plugin-specific configuration
  config:
    - url: "http://example.com/health"
      bearer_token: "optional-token"
      auth: "username,password"  # Optional basic auth
      verify_url: true           # Optional SSL verification
      exit_on_failure: false     # Optional exit behavior
```

## Abstract Base Class API

### Required Methods

#### `get_health_check_types() -> list[str]`
Returns the health check type identifiers this plugin handles.

#### `run_health_check(config: dict, telemetry_queue: queue.Queue) -> None`
Main health check logic. Runs until `current_iterations >= iterations`.

#### `increment_iterations() -> None`
Called by main loop after each chaos iteration to keep health check synchronized.

### Inherited Methods

#### `get_return_value() -> int`
Returns 0 for success, non-zero for failure.

#### `set_return_value(value: int) -> None`
Sets return value (0 = success, non-zero = failure).

## Testing Your Plugin

```python
import unittest
from unittest.mock import MagicMock
from krkn.health_checks import HealthCheckFactory

class TestMyHealthCheckPlugin(unittest.TestCase):
    def test_plugin_loads(self):
        factory = HealthCheckFactory()
        self.assertIn("my_health_check", factory.loaded_plugins)

    def test_plugin_creation(self):
        factory = HealthCheckFactory()
        plugin = factory.create_plugin("my_health_check", iterations=5)
        self.assertEqual(plugin.iterations, 5)
        self.assertEqual(plugin.current_iterations, 0)

    def test_increment_iterations(self):
        factory = HealthCheckFactory()
        plugin = factory.create_plugin("my_health_check", iterations=5)
        plugin.increment_iterations()
        self.assertEqual(plugin.current_iterations, 1)
```

## Using Health Check Plugins

The plugin-based architecture is the standard way to use health checks in krkn:

```python
from krkn.health_checks import HealthCheckFactory
import threading
import queue

# Create factory instance
factory = HealthCheckFactory()

# Create health check plugin
health_checker = factory.create_plugin(
    health_check_type="http_health_check",
    iterations=5
)

# Create telemetry queue
health_check_telemetry_queue = queue.Queue()

# Run in background thread
health_check_worker = threading.Thread(
    target=health_checker.run_health_check,
    args=(health_check_config, health_check_telemetry_queue)
)
health_check_worker.start()

# In main loop
for iteration in range(iterations):
    # Run chaos scenarios...

    # Increment health check iteration
    health_checker.increment_iterations()

# Wait for completion
health_check_worker.join()

# Check results
if health_checker.get_return_value() != 0:
    logging.error("Health check failed")
```

## Benefits of Plugin Architecture

1. **Extensibility**: Easy to add new health check types without modifying core code
2. **Testability**: Each plugin is independently testable
3. **Maintainability**: Clear separation of concerns
4. **Discoverability**: Automatic plugin discovery reduces configuration
5. **Reusability**: Plugins can be shared across different chaos experiments
6. **Type Safety**: Type hints and abstract base class enforce API contracts

## Troubleshooting

### Plugin Not Loading

Check `factory.failed_plugins` to see why a plugin failed to load:

```python
factory = HealthCheckFactory()
for module, cls, error in factory.failed_plugins:
    print(f"Failed: {module} ({cls}): {error}")
```

Common issues:
- Module doesn't end with `_health_check_plugin.py`
- Class doesn't end with `HealthCheckPlugin`
- Class name doesn't match file name (snake_case to CapitalCamelCase)
- Missing dependencies (will show in error message)
- Import errors

### Duplicate Health Check Types

If two plugins return the same health check type from `get_health_check_types()`, the second one will fail to load with a duplicate error.

## Examples

See the following implementations for reference:
- [http_health_check_plugin.py](http_health_check_plugin.py) - HTTP endpoint monitoring
- [virt_health_check_plugin.py](virt_health_check_plugin.py) - KubeVirt VM health monitoring with SSH access checks
- [simple_health_check_plugin.py](simple_health_check_plugin.py) - Minimal example for testing

## Available Plugins

### HTTP Health Check Plugin
- **Types:** `http_health_check`
- **Purpose:** Monitor HTTP/HTTPS endpoints
- **Features:** Basic auth, bearer tokens, SSL verification, failure detection
- **Threading:** Runs continuously in a background thread

### Virt Health Check Plugin
- **Types:** `virt_health_check`, `kubevirt_health_check`, `vm_health_check`
- **Purpose:** Monitor KubeVirt virtual machine accessibility
- **Features:** virtctl access checks, disconnected SSH checks, VM migration tracking, batch processing
- **Threading:** Spawns worker threads internally (no wrapper thread needed)
