set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function funtional_test_node_crash {

  export scenario_type="node_scenarios"
  export scenario_file="CI/scenarios/node_scenario.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/node_config.yaml

  python3 -m coverage run -a run_kraken.py -c CI/config/node_config.yaml
  echo "Node scenario test: Success"
}

funtional_test_node_crash
