set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_time_scenario {
  yq -i '.time_scenarios[0].label_selector="scenario=time-skew"' scenarios/openshift/time_scenarios_example.yml
  yq -i '.time_scenarios[0].container_name=""' scenarios/openshift/time_scenarios_example.yml
  yq -i '.time_scenarios[0].namespace="default"' scenarios/openshift/time_scenarios_example.yml
  yq -i '.time_scenarios[1].label_selector="kubernetes.io/hostname=kind-worker2"' scenarios/openshift/time_scenarios_example.yml
  export scenario_type="time_scenarios"
  export scenario_file="scenarios/openshift/time_scenarios_example.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/time_config.yaml

  python3 -m coverage run -a run_kraken.py -c CI/config/time_config.yaml
  echo "Time scenario test: Success"
}

functional_test_time_scenario
