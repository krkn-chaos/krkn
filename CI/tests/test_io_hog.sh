set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_io_hog {
  yq -i '.node_selector="kubernetes.io/hostname=kind-worker2"' scenarios/kube/io-hog.yml
  export scenario_type="hog_scenarios"
  export scenario_file="scenarios/kube/io-hog.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/io_hog.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/io_hog.yaml
  echo "IO Hog: Success"
}

functional_test_io_hog