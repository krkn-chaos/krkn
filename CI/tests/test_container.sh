#!/bin/bash
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

set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

pod_file="CI/scenarios/hello_pod.yaml"

function functional_test_container_crash {
  yq -i '.scenarios[0].namespace="default"' scenarios/openshift/container_etcd.yml
  yq -i '.scenarios[0].label_selector="scenario=container"' scenarios/openshift/container_etcd.yml
  yq -i '.scenarios[0].container_name="fedtools"' scenarios/openshift/container_etcd.yml
  export scenario_type="container_scenarios"
  export scenario_file="scenarios/openshift/container_etcd.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/container_config.yaml

  python3 -m coverage run -a run_kraken.py -c CI/config/container_config.yaml -d True
  echo "Container scenario test: Success"

  kubectl get pods -n kube-system -l component=etcd
}

functional_test_container_crash
