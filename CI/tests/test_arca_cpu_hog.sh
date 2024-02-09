set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_arca_cpu_hog {
  yq -i '.input_list[0].node_selector={"kubernetes.io/hostname":"kind-worker2"}' scenarios/arcaflow/cpu-hog/input.yaml
  export scenario_type="arcaflow_scenarios"
  export scenario_file="scenarios/arcaflow/cpu-hog/input.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/arca_cpu_hog.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/arca_cpu_hog.yaml
  echo "Arcaflow CPU Hog: Success"
}

functional_test_arca_cpu_hog