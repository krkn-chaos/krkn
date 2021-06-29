set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_time_scenario {
  export scenario_type="time_scenarios"
  export scenario_file="CI/scenarios/time_scenarios.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/time_config.yaml

  python3 run_kraken.py -c CI/config/time_config.yaml
  echo "Time scenario test: Success"
}

functional_test_time_scenario
