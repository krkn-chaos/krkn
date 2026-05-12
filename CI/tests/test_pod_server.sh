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

function functional_test_pod_server {
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/kind/pod_etcd.yml"
  export post_config=""

  envsubst < CI/config/common_test_config.yaml > CI/config/pod_config.yaml
  yq -i '.[0].config.kill=1' scenarios/kind/pod_etcd.yml
  
  yq -i '.tunings.daemon_mode=True' CI/config/pod_config.yaml
  cat CI/config/pod_config.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/pod_config.yaml & 
  sleep 15
  curl -X POST http:/0.0.0.0:8081/STOP

  wait

  yq -i '.kraken.signal_state="PAUSE"' CI/config/pod_config.yaml
  yq -i '.tunings.daemon_mode=False' CI/config/pod_config.yaml
  cat CI/config/pod_config.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/pod_config.yaml & 
  sleep 5
  curl -X POST http:/0.0.0.0:8081/RUN
  wait

  echo "Pod disruption with server scenario test: Success"
}

functional_test_pod_server
