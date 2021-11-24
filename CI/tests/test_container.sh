set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

pod_file="CI/scenarios/hello_pod.yaml"

function functional_test_container_crash {

  export scenario_type="container_scenarios"
  export scenario_file="- CI/scenarios/container_scenario.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/container_config.yaml

  python3 run_kraken.py -c CI/config/container_config.yaml
  echo "Container scenario test: Success"
}

functional_test_container_crash
