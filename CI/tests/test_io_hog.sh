set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_litmus_io {

  export scenario_type="litmus_scenarios"
  export scenario_file="- scenarios/templates/litmus-rbac.yaml"
  export post_config="- CI/scenarios/node_io_engine_node.yaml"
  envsubst < CI/config/common_test_config.yaml > CI/config/litmus_config.yaml
  envsubst < CI/scenarios/node_io_engine.yaml > CI/scenarios/node_io_engine_node.yaml
  python3 run_kraken.py -c CI/config/litmus_config.yaml
  echo "Litmus scenario $1 test: Success"
}

functional_test_litmus_io
