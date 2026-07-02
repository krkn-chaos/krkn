# How to Add a New Scenario Plugin

This guide walks through adding a new chaos scenario plugin to Krkn. There are two patterns depending on complexity:

- **Simple plugin** — one plugin, one behavior (e.g., `pod_disruption`)
- **Factory plugin** — one plugin entry point, multiple sub-modules dispatched by ID (e.g., `network_chaos_ng`)

---

## How Plugin Discovery Works

`ScenarioPluginFactory` automatically finds plugins at startup using `pkgutil.walk_packages()`. It looks for any class that:

1. Lives in a file named `*_scenario_plugin.py`
2. Inherits from `AbstractScenarioPlugin`
3. Has a class name that is the CamelCase version of the filename

**Naming rules are enforced — get these wrong and the plugin silently fails to load:**

| File | Class |
|------|-------|
| `my_scenario_plugin.py` | `MyScenarioPlugin` |
| `node_network_chaos_scenario_plugin.py` | `NodeNetworkChaosScenarioPlugin` |
| `vmi_network_chaos_scenario_plugin.py` | `VmiNetworkChaosScenarioPlugin` |

The parent folder name must **not** contain `scenario` or `plugin`.

---

## Pattern 1: Simple Plugin

Use this when your plugin has a single behavior with no sub-modes.

### Step 1 — Create the folder and plugin file

```
krkn/scenario_plugins/my_chaos/
├── __init__.py
└── my_chaos_scenario_plugin.py
```

### Step 2 — Implement the plugin class

```python
# my_chaos_scenario_plugin.py
import logging
import yaml
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin


class MyChaosScenarioPlugin(AbstractScenarioPlugin):

    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario) as f:
                config = yaml.safe_load(f)

            # your chaos logic here
            logging.info(f"running my chaos scenario: {config}")

            return 0
        except Exception as e:
            logging.error(f"my chaos scenario failed: {e}")
            return 1

    def get_scenario_types(self) -> list[str]:
        # Must match the key used in config.yaml under scenario_types
        return ["my_chaos_scenarios"]
```

### Step 3 — Create a scenario YAML

```yaml
# scenarios/my_chaos_example.yaml
target: ".*"
namespace: "default"
duration: 60
```

### Step 4 — Reference in config.yaml

```yaml
scenario_types:
  my_chaos_scenarios:
    - scenarios/my_chaos_example.yaml
```

---

## Pattern 2: Factory Plugin (Multiple Sub-modules)

Use this when your plugin supports multiple behaviors dispatched by an `id` field, like `network_chaos_ng`.

### Step 1 — Create the folder structure

```
krkn/scenario_plugins/my_chaos_ng/
├── __init__.py
├── my_chaos_ng_scenario_plugin.py   ← entry point
├── my_chaos_factory.py              ← dispatches by id
├── models.py                        ← config dataclasses
└── modules/
    ├── __init__.py
    ├── abstract_my_chaos_module.py  ← abstract base for sub-modules
    ├── my_first_module.py
    ├── my_second_module.py
    └── utils.py
```

### Step 2 — Define config models

```python
# models.py
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class MyChaosScenarioType(Enum):
    First = 1
    Second = 2


@dataclass
class BaseMyChaosConfig:
    id: str
    namespace: str
    target: str
    test_duration: int
    instance_count: int
    execution: str        # "serial" or "parallel"
    label_selector: str
    image: str
    service_account: str
    taints: list[str]
    wait_duration: int
    ingress: bool
    egress: bool
    interfaces: list[str]

    def validate(self) -> list[str]:
        errors = []
        if self.execution not in ["serial", "parallel"]:
            errors.append(f"execution must be serial or parallel, got: {self.execution}")
        if not isinstance(self.test_duration, int):
            errors.append("test_duration must be an int")
        return errors


@dataclass
class FirstModeConfig(BaseMyChaosConfig):
    # first-mode-specific fields
    rate: Optional[str] = None

    def validate(self) -> list[str]:
        errors = super().validate()
        if self.rate and not self.rate.endswith(("mbit", "kbit", "gbit")):
            errors.append("rate must end with mbit, kbit, or gbit")
        return errors
```

### Step 3 — Define the abstract sub-module

```python
# modules/abstract_my_chaos_module.py
import abc
import queue
from typing import Tuple
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.my_chaos_ng.models import MyChaosScenarioType, BaseMyChaosConfig


class AbstractMyChaosModule(abc.ABC):

    def __init__(self, config: BaseMyChaosConfig, kubecli: KrknTelemetryOpenshift):
        self.config = config
        self.kubecli = kubecli
        self.base_config = config

    @abc.abstractmethod
    def run(self, target: str, error_queue: queue.Queue = None):
        """Execute chaos on a single target. Put errors in error_queue if parallel."""

    @abc.abstractmethod
    def get_config(self) -> Tuple[MyChaosScenarioType, BaseMyChaosConfig]:
        """Return the scenario type enum and config."""

    @abc.abstractmethod
    def get_targets(self) -> list[str]:
        """Return list of target identifiers to run chaos against."""
```

### Step 4 — Implement a sub-module

```python
# modules/my_first_module.py
import queue
import time
from typing import Tuple
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.my_chaos_ng.models import (
    MyChaosScenarioType, BaseMyChaosConfig, FirstModeConfig,
)
from krkn.scenario_plugins.my_chaos_ng.modules.abstract_my_chaos_module import (
    AbstractMyChaosModule,
)


class MyFirstModule(AbstractMyChaosModule):

    def __init__(self, config: FirstModeConfig, kubecli: KrknTelemetryOpenshift):
        super().__init__(config, kubecli)
        self.config = config

    def _rollback(self, namespace: str, chaos_pod: str, ...):
        # clean up any applied rules, then delete the chaos pod
        self.kubecli.get_lib_kubernetes().delete_pod(chaos_pod, namespace)

    def run(self, target: str, error_queue: queue.Queue = None):
        parallel = error_queue is not None
        chaos_pod = None
        try:
            # 1. Resolve the target (e.g., node name, pod, VMI)
            # 2. Deploy a privileged chaos pod on the target's node
            # 3. Apply chaos rules
            time.sleep(self.config.test_duration)
            # 4. Clean up via _rollback (success path)
            self._rollback(...)
        except Exception as e:
            if chaos_pod:
                self._rollback(...)   # always clean up
            if error_queue is None:
                raise
            error_queue.put(str(e))

    def get_config(self) -> Tuple[MyChaosScenarioType, BaseMyChaosConfig]:
        return MyChaosScenarioType.First, self.config

    def get_targets(self) -> list[str]:
        # query kubernetes for matching targets
        return self.kubecli.get_lib_kubernetes().list_nodes(
            label_selector=self.config.label_selector or None
        )
```

### Step 5 — Create the factory

```python
# my_chaos_factory.py
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn.scenario_plugins.my_chaos_ng.models import FirstModeConfig
from krkn.scenario_plugins.my_chaos_ng.modules.abstract_my_chaos_module import (
    AbstractMyChaosModule,
)
from krkn.scenario_plugins.my_chaos_ng.modules.my_first_module import MyFirstModule

supported_modules = ["my_first_mode", "my_second_mode"]


class MyChaosFactory:

    @staticmethod
    def get_instance(config: dict, kubecli: KrknTelemetryOpenshift) -> AbstractMyChaosModule:
        if config["id"] not in supported_modules:
            raise Exception(f"{config['id']} is not a supported module")

        if config["id"] == "my_first_mode":
            scenario_config = FirstModeConfig(**config)
            errors = scenario_config.validate()
            if errors:
                raise Exception(f"config validation errors: [{';'.join(errors)}]")
            return MyFirstModule(scenario_config, kubecli)
        else:
            raise Exception(f"invalid id {config['id']}")
```

### Step 6 — Implement the plugin entry point

```python
# my_chaos_ng_scenario_plugin.py
import logging
import yaml
import queue
import threading
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ScenarioTelemetry
from krkn.scenario_plugins.abstract_scenario_plugin import AbstractScenarioPlugin
from krkn.scenario_plugins.my_chaos_ng.my_chaos_factory import MyChaosFactory


class MyChaosNgScenarioPlugin(AbstractScenarioPlugin):

    def run(
        self,
        run_uuid: str,
        scenario: str,
        lib_telemetry: KrknTelemetryOpenshift,
        scenario_telemetry: ScenarioTelemetry,
    ) -> int:
        try:
            with open(scenario) as f:
                scenario_configs = yaml.safe_load(f)

            for config in scenario_configs:
                module = MyChaosFactory.get_instance(config, lib_telemetry)
                targets = module.get_targets()

                if not targets:
                    logging.warning("no targets found, skipping")
                    continue

                targets = targets[: config.get("instance_count", 1)]

                if config.get("execution") == "parallel":
                    error_queue = queue.Queue()
                    threads = [
                        threading.Thread(target=module.run, args=(t, error_queue))
                        for t in targets
                    ]
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join()
                    if not error_queue.empty():
                        raise Exception(error_queue.get())
                else:
                    for target in targets:
                        module.run(target)

            return 0
        except Exception as e:
            logging.error(f"my chaos ng scenario failed: {e}")
            return 1

    def get_scenario_types(self) -> list[str]:
        return ["my_chaos_ng_scenarios"]
```

### Step 7 — Create a scenario YAML

```yaml
# scenarios/my_chaos_ng_example.yaml
- id: my_first_mode
  image: "quay.io/krkn-chaos/krkn-network-chaos:latest"
  namespace: "default"
  target: ".*"
  test_duration: 60
  wait_duration: 300
  instance_count: 1
  execution: serial
  label_selector: ""
  service_account: ""
  taints: []
  interfaces: []
  ingress: true
  egress: true
  rate: "100mbit"
```

### Step 8 — Reference in config.yaml

```yaml
scenario_types:
  my_chaos_ng_scenarios:
    - scenarios/my_chaos_ng_example.yaml
```

---

## Checklist

- [ ] Folder name does **not** contain `scenario` or `plugin`
- [ ] Plugin filename ends with `_scenario_plugin.py`
- [ ] Class name is the CamelCase of the filename (e.g., `my_chaos_ng_scenario_plugin.py` → `MyChaosNgScenarioPlugin`)
- [ ] `get_scenario_types()` returns a string matching the key in `config.yaml`
- [ ] `run()` returns `0` on success, `1` on failure
- [ ] Config dataclass has a `validate()` method returning a list of error strings
- [ ] Sub-module `run()` accepts an optional `error_queue` for parallel execution
- [ ] Rollback cleans up all applied changes even when an exception is raised
- [ ] Unit tests exist for each sub-module covering success, error, and rollback paths

---

## Useful References

| File | Purpose |
|------|---------|
| `abstract_scenario_plugin.py` | Base class all plugins inherit from |
| `scenario_plugin_factory.py` | Auto-discovers and loads plugins |
| `network_chaos_ng/` | Full example of the factory pattern |
| `pod_disruption/` | Full example of the simple pattern |
| `network_chaos_ng/models.py` | Example config dataclasses with `validate()` |
| `network_chaos_ng/modules/utils.py` | Shared helpers (pod deployment, logging) |
