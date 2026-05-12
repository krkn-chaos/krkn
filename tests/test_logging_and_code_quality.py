#!/usr/bin/env python3
#
# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Tests for fixes introduced in issues #24–#28.

Stubs all external dependencies (krkn_lib, kubernetes, broken urllib3)
so tests run without any additional installs.

Usage (run from repo root):
    python3 -m coverage run -a -m unittest tests/test_fixes_24_to_28.py -v
"""

import queue
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Inject minimal stubs for every external dependency
# ---------------------------------------------------------------------------

def _inject(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return sys.modules[name]


# -- krkn_lib ----------------------------------------------------------------
_inject("krkn_lib")
_inject("krkn_lib.utils", deep_get_attribute=MagicMock(return_value=[]))
_inject("krkn_lib.utils.functions",
        get_yaml_item_value=MagicMock(
            side_effect=lambda cfg, key, default: (
                cfg.get(key, default) if isinstance(cfg, dict) else default
            )
        ))
_inject("krkn_lib.models.telemetry",
        ScenarioTelemetry=MagicMock(), ChaosRunTelemetry=MagicMock())


class _VirtCheck:
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


_inject("krkn_lib.models.telemetry.models", VirtCheck=_VirtCheck)
_inject("krkn_lib.models.krkn",
        ChaosRunAlertSummary=MagicMock(), ChaosRunAlert=MagicMock())
_inject("krkn_lib.models.elastic.models", ElasticAlert=MagicMock())
_inject("krkn_lib.models.elastic", ElasticChaosRunTelemetry=MagicMock())
_inject("krkn_lib.models.k8s", ResiliencyReport=MagicMock())
_inject("krkn_lib.elastic.krkn_elastic", KrknElastic=MagicMock())
_inject("krkn_lib.prometheus.krkn_prometheus", KrknPrometheus=MagicMock())
_inject("krkn_lib.telemetry.ocp", KrknTelemetryOpenshift=MagicMock())
_inject("krkn_lib.telemetry.k8s", KrknTelemetryKubernetes=MagicMock())
_inject("krkn_lib.k8s", KrknKubernetes=MagicMock())
_inject("krkn_lib.ocp", KrknOpenshift=MagicMock())

# -- broken third-party ------------------------------------------------------
# urllib3.exceptions doesn't export HTTPError on this Python version
import urllib3.exceptions  # noqa: E402 (real module, just patch the attr)
if not hasattr(urllib3.exceptions, "HTTPError"):
    urllib3.exceptions.HTTPError = Exception

# kubernetes – stub the whole chain before anything imports it
_inject("kubernetes")
_inject("kubernetes.client")
_inject("kubernetes.client.rest", ApiException=type("ApiException", (Exception,), {}))

# -- other stubs needed by krkn internals ------------------------------------
_inject("tzlocal")
_inject("tzlocal.unix", get_localzone=MagicMock(return_value="UTC"))

# kubevirt plugin (imports kubernetes.client.rest)
_KubevirtPlugin = MagicMock()
_inject(
    "krkn.scenario_plugins.kubevirt_vm_outage"
    ".kubevirt_vm_outage_scenario_plugin",
    KubevirtVmOutageScenarioPlugin=_KubevirtPlugin,
)

# -- yaml (real or stub) -----------------------------------------------------
try:
    import yaml as _yaml  # noqa: F401
except ImportError:
    _inject("yaml")

# ---------------------------------------------------------------------------
# Now import the actual krkn modules under test
# ---------------------------------------------------------------------------

from krkn.prometheus import client                        # noqa: E402
from krkn.utils import VirtChecker as VirtCheckerModule  # noqa: E402
from krkn.utils.VirtChecker import VirtChecker           # noqa: E402


# ===========================================================================
# #1 — Typo "wating" -> "waiting"
# ===========================================================================

class TestIssue24TypoFix(unittest.TestCase):
    """#24: Log message must spell 'waiting' correctly."""

    def test_no_wating_typo_in_source(self):
        import pathlib
        src = pathlib.Path("krkn/scenario_plugins/abstract_scenario_plugin.py").read_text()
        self.assertNotIn('"wating ', src,
                         "Typo 'wating' still present in abstract_scenario_plugin.py")

    def test_waiting_present_in_source(self):
        import pathlib
        src = pathlib.Path("krkn/scenario_plugins/abstract_scenario_plugin.py").read_text()
        self.assertIn('"waiting ', src,
                      "'waiting' not found in abstract_scenario_plugin.py")


# ===========================================================================
# #2 — print() replaced by logging.debug()
# ===========================================================================

class TestIssue25NoPrintInClient(unittest.TestCase):
    """#25: client.py must not use print() for pod metric messages."""

    def test_no_print_adding_pod(self):
        import pathlib
        src = pathlib.Path("krkn/prometheus/client.py").read_text()
        self.assertNotIn("print('adding pod'", src)
        self.assertNotIn('print("adding pod"', src)

    def test_logging_debug_used(self):
        import pathlib
        src = pathlib.Path("krkn/prometheus/client.py").read_text()
        self.assertIn('logging.debug("adding pod', src)

    def test_metrics_does_not_write_to_stdout(self):
        """metrics() must not emit to stdout for pod telemetry entries."""
        import io, json, os, tempfile
        prom_cli = MagicMock()
        prom_cli.process_prom_query_in_range.return_value = []
        prom_cli.process_query.return_value = []

        telemetry_data = {
            "scenarios": [{
                "affected_pods": {
                    "disrupted": [{"name": "pod-1", "namespace": "default"}]
                },
                "affected_vmis": {
                    "recovered": [{"vmi_name": "vm-1", "namespace": "default"}]
                },
                "affected_nodes": [],
            }],
            "health_checks": [],
            "virt_checks": [],
        }
        profile = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        profile.write("metrics:\n  - query: up\n    metricName: uptime\n")
        profile.close()

        elastic = MagicMock()
        elastic.upload_metrics_to_elasticsearch.return_value = 0

        captured = io.StringIO()
        sys.stdout, orig = captured, sys.stdout
        try:
            client.metrics(
                prom_cli, elastic, "uuid-1",
                1_000_000.0, 1_000_060.0,
                profile.name, "idx",
                json.dumps(telemetry_data),
            )
        finally:
            sys.stdout = orig
            os.unlink(profile.name)

        self.assertEqual(
            captured.getvalue(), "",
            f"stdout was not empty: {captured.getvalue()!r}",
        )


# ===========================================================================
# #3 — Star import removed
# ===========================================================================

class TestIssue26NoStarImport(unittest.TestCase):
    """#26: utils/__init__.py must use explicit imports, not star import."""

    def test_no_star_import(self):
        import pathlib
        src = pathlib.Path("krkn/utils/__init__.py").read_text()
        self.assertNotIn("import *", src)

    def test_explicit_names_present(self):
        import pathlib
        src = pathlib.Path("krkn/utils/__init__.py").read_text()
        self.assertIn("populate_cluster_events", src)
        self.assertIn("collect_and_put_ocp_logs", src)
        self.assertIn("KrknKubernetes", src)
        self.assertIn("ScenarioTelemetry", src)
        self.assertIn("KrknTelemetryOpenshift", src)

    def test_functions_accessible_from_package(self):
        from krkn import utils
        self.assertTrue(hasattr(utils, "populate_cluster_events"))
        self.assertTrue(hasattr(utils, "collect_and_put_ocp_logs"))
        self.assertTrue(hasattr(utils, "KrknKubernetes"))
        self.assertTrue(hasattr(utils, "ScenarioTelemetry"))
        self.assertTrue(hasattr(utils, "KrknTelemetryOpenshift"))


# ===========================================================================
# #4 — global declaration removed from main()
# ===========================================================================

class TestIssue27NoGlobalInMain(unittest.TestCase):
    """#27: main() in run_kraken.py must not declare global variables."""

    def test_no_global_statement_in_main(self):
        import ast, pathlib
        src = pathlib.Path("run_kraken.py").read_text()
        tree = ast.parse(src)
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                for child in ast.walk(node):
                    if isinstance(child, ast.Global):
                        found.extend(child.names)
        self.assertEqual(found, [],
                         f"Global declarations found in main(): {found}")


# ===========================================================================
# #5 — Exception logged at ERROR level, not INFO
# ===========================================================================

class TestIssue28ExceptionLogLevel(unittest.TestCase):
    """#28: VirtChecker must log VM status exceptions at ERROR, not INFO."""

    def test_no_info_for_vm_exception_in_source(self):
        import pathlib
        src = pathlib.Path("krkn/utils/VirtChecker.py").read_text()
        self.assertNotIn(
            "logging.info('Exception in get vm status')", src
        )

    def test_error_level_present_in_source(self):
        import pathlib
        src = pathlib.Path("krkn/utils/VirtChecker.py").read_text()
        self.assertIn(
            'logging.exception("Exception in get vm status")', src
        )

    def test_runtime_exception_triggers_error_log(self):
        """When get_vm_access raises, the handler must call logging.error."""
        config = {}
        mock_krkn = MagicMock()

        with patch(
            "krkn.utils.VirtChecker.get_yaml_item_value",
            side_effect=lambda cfg, key, default: (
                cfg.get(key, default) if isinstance(cfg, dict) else default
            ),
        ):
            checker = VirtChecker(config, iterations=1, krkn_lib=mock_krkn)

        checker.batch_size = 1
        checker.interval = 0
        checker.disconnected = False

        vm = _VirtCheck({
            "vm_name": "vm-1",
            "ip_address": "1.2.3.4",
            "namespace": "ns",
            "node_name": "w1",
            "new_ip_address": "",
        })

        error_calls, info_calls, exception_calls = [], [], []

        with (
            patch.object(
                checker, "get_vm_access",
                side_effect=RuntimeError("connection refused"),
            ),
            patch("krkn.utils.VirtChecker.logging") as mock_log,
            patch("krkn.utils.VirtChecker.time") as mock_time,
        ):
            mock_log.error.side_effect = (
                lambda msg, *a, **kw: error_calls.append(msg % a if a else msg)
            )
            mock_log.info.side_effect = (
                lambda msg, *a, **kw: info_calls.append(msg % a if a else msg)
            )
            mock_log.exception.side_effect = (
                lambda msg, *a, **kw: exception_calls.append(msg % a if a else msg)
            )
            # End loop after first sleep
            mock_time.sleep.side_effect = (
                lambda _: setattr(checker, "current_iterations", 999)
            )
            checker.current_iterations = 0

            q = queue.SimpleQueue()
            checker.run_virt_check([vm], q)

        vm_infos  = [m for m in info_calls  if "Exception in get vm status" in m]
        err_vm_msgs  = [m for m in error_calls + exception_calls if "Exception in get vm status" in m]

        self.assertEqual(
            vm_infos, [],
            "Exception still logged at INFO level at runtime",
        )
        self.assertGreater(
            len(err_vm_msgs), 0,
            "Exception not logged at ERROR level at runtime",
        )


if __name__ == "__main__":
    unittest.main()