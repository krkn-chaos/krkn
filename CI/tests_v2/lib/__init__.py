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

# Shared framework for CI/tests_v2 functional tests.
# base: BaseScenarioTest, timeout constants
# utils: assertions, K8s helpers, patch_namespace_in_docs
# k8s: K8s client fixtures, cluster context checks
# namespace: test_namespace, stale namespace cleanup
# deploy: deploy_workload, wait_for_pods_running, wait_for_deployment_replicas
# kraken: run_kraken, run_kraken_background, build_config
