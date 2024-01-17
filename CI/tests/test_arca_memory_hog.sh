set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_arca_memory_hog {
  export scenario_type="arcaflow_scenarios"
  export scenario_file="CI/scenarios/arcaflow/memory-hog/input.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/arca_memory_hog.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/arca_memory_hog.yaml
  echo "Arcaflow Memory Hog: Success"
}

functional_test_arca_memory_hog