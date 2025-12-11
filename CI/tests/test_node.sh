uset -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_node_stop_start {
  export scenario_type="node_scenarios"
  export scenario_file="scenarios/kind/node_scenarios_example.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/node_config.yaml
  cat CI/config/node_config.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/node_config.yaml
  echo "Node Stop/Start scenario test: Success"
}

functional_test_node_stop_start
