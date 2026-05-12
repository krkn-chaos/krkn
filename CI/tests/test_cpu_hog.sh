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


function functional_test_cpu_hog {
  yq -i '."node-selector"="kubernetes.io/hostname=kind-worker2"' scenarios/kube/cpu-hog.yml

  export scenario_type="hog_scenarios"
  export scenario_file="scenarios/kube/cpu-hog.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/cpu_hog.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/cpu_hog.yaml
  echo "CPU Hog: Success"
}

functional_test_cpu_hog