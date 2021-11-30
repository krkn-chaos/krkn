set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_network_chaos {

  export scenario_type="network_chaos"
  export scenario_file="CI/scenarios/network_chaos.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/network_chaos.yaml
  python3 run_kraken.py -c CI/config/network_chaos.yaml
  echo "Network Chaos test: Success"
}

functional_test_network_chaos
