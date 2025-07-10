set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_cpu_hog {
  yq -i '."node-selector"="kubernetes.io/hostname=kind-worker2"' scenarios/kube/cpu-hog.yml

  export scenario_type="hog_scenarios"
  export scenario_file="scenarios/kube/cpu-hog.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/cpu_hog.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/cpu_hog.yaml
  echo "CPU Hog: Success"
}

functional_test_cpu_hog