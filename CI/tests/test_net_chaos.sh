set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_network_chaos {
  yq -i '.network_chaos.duration=10' scenarios/openshift/network_chaos.yaml
  yq -i '.network_chaos.node_name="kind-worker2"' scenarios/openshift/network_chaos.yaml
  yq -i '.network_chaos.egress.bandwidth="100mbit"' scenarios/openshift/network_chaos.yaml
  yq -i 'del(.network_chaos.interfaces)' scenarios/openshift/network_chaos.yaml
  yq -i 'del(.network_chaos.label_selector)' scenarios/openshift/network_chaos.yaml
  yq -i 'del(.network_chaos.egress.latency)' scenarios/openshift/network_chaos.yaml
  yq -i 'del(.network_chaos.egress.loss)' scenarios/openshift/network_chaos.yaml

  export scenario_type="network_chaos"
  export scenario_file="scenarios/openshift/network_chaos.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/network_chaos.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/network_chaos.yaml
  echo "Network Chaos test: Success"
}

functional_test_network_chaos
