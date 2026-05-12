#!/usr/bin/env python
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
Functional test for pod disruption scenario (pod crash and recovery).
Equivalent to CI/tests/test_pod.sh with proper before/after assertions.
Each test runs in its own ephemeral namespace with workload deployed automatically.
"""

import pytest

from lib.base import BaseScenarioTest, READINESS_TIMEOUT
from lib.utils import (
    assert_all_pods_running_and_ready,
    assert_kraken_success,
    assert_pod_count_unchanged,
    get_pods_list,
    pod_uids,
    restart_counts,
)


@pytest.mark.functional
@pytest.mark.pod_disruption
class TestPodDisruption(BaseScenarioTest):
    """Pod disruption scenario: kill pods and verify recovery."""

    WORKLOAD_MANIFEST = "CI/tests_v2/scenarios/pod_disruption/resource.yaml"
    WORKLOAD_IS_PATH = True
    LABEL_SELECTOR = "app=krkn-pod-disruption-target"
    SCENARIO_NAME = "pod_disruption"
    SCENARIO_TYPE = "pod_disruption_scenarios"
    NAMESPACE_KEY_PATH = [0, "config", "namespace_pattern"]
    NAMESPACE_IS_REGEX = True

    @pytest.mark.order(1)
    def test_pod_crash_and_recovery(self, wait_for_pods_running):
        ns = self.ns
        before = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        before_uids = pod_uids(before)
        before_restarts = restart_counts(before)

        result = self.run_scenario(self.tmp_path, ns)
        assert_kraken_success(result, context=f"namespace={ns}", tmp_path=self.tmp_path)

        after = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        after_uids = pod_uids(after)
        after_restarts = restart_counts(after)
        uids_changed = set(after_uids) != set(before_uids)
        restarts_increased = after_restarts > before_restarts
        assert uids_changed or restarts_increased, (
            f"Chaos had no effect in namespace={ns}: pod UIDs unchanged and restart count did not increase. "
            f"Before UIDs: {before_uids}, restarts: {before_restarts}. "
            f"After UIDs: {after_uids}, restarts: {after_restarts}."
        )

        wait_for_pods_running(ns, self.LABEL_SELECTOR, timeout=READINESS_TIMEOUT)

        after_final = get_pods_list(self.k8s_core, ns, self.LABEL_SELECTOR)
        assert_pod_count_unchanged(before, after_final, namespace=ns)
        assert_all_pods_running_and_ready(after_final, namespace=ns)
