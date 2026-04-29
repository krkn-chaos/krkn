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



source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_pod_error {
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/kind/pod_etcd.yml"
  export post_config=""
  # this test will check if krkn exits with an error when too many pods are targeted
  yq -i '.[0].config.kill=5' scenarios/kind/pod_etcd.yml
  yq -i '.[0].config.krkn_pod_recovery_time=1' scenarios/kind/pod_etcd.yml
  envsubst < CI/config/common_test_config.yaml > CI/config/pod_config.yaml
  cat CI/config/pod_config.yaml

  cat scenarios/kind/pod_etcd.yml
  python3 -m coverage run -a run_kraken.py -c CI/config/pod_config.yaml
  
  ret=$?
  echo "\n\nret $ret"
  if [[ $ret -ge 1 ]]; then
      echo "Pod disruption error scenario test: Success"
  else 
    echo "Pod disruption error scenario test: Failure"
    exit 1
  fi
}

functional_test_pod_error
