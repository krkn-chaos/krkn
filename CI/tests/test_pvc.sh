set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_pvc_fill {
  export scenario_type="pvc_scenarios"
  export scenario_file="scenarios/kind/pvc_scenario.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/pvc_config.yaml
  cat CI/config/pvc_config.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/pvc_config.yaml --debug True
  echo "PVC Fill scenario test: Success"
}

functional_test_pvc_fill
