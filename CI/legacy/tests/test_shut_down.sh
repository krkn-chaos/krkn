set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_shut_down {

  export scenario_type="cluster_shut_down_scenarios"
  export scenario_file="- CI/scenarios/cluster_shut_down_scenario.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/shut_down.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/shut_down.yaml
  echo "Cluster shut down scenario test: Success"
}

functional_test_shut_down
