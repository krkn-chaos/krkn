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


function functional_test_app_outage {
  yq -i '.application_outage.duration=10' scenarios/openshift/app_outage.yaml
  yq -i '.application_outage.pod_selector={"scenario":"outage"}' scenarios/openshift/app_outage.yaml
  yq -i '.application_outage.namespace="default"' scenarios/openshift/app_outage.yaml
  export scenario_type="application_outages_scenarios"
  export scenario_file="scenarios/openshift/app_outage.yaml"
  export post_config=""

  kubectl get services -A 

  kubectl get pods 
  envsubst < CI/config/common_test_config.yaml > CI/config/app_outage.yaml
  cat $scenario_file
  cat CI/config/app_outage.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/app_outage.yaml
  echo "App outage scenario test: Success"
}

functional_test_app_outage
