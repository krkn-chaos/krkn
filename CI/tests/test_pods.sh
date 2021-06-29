set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function funtional_test_pod_deletion {
  export scenario_type="pod_scenarios"
  export scenario_file="-  CI/scenarios/hello_pod_killing.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/pod_config.yaml

  python3 run_kraken.py -c CI/config/pod_config.yaml
  echo $?
  echo "Pod scenario test: Success"
}

funtional_test_pod_deletion
