set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_pod_network_chaos {
  export SERVICE_URL=http://localhost:8888
  yq -i '.[0].test_duration=10' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].wait_duration=1' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].execution="parallel"' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].network_shaping_execution="parallel"' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].instance_count=1' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].bandwidth="1mbit"' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].loss="100%"' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].latency="1000ms"' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].target="nginx"' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].namespace="default"' scenarios/openshift/pod_egress_shaping.yml
  yq -i '.[0].label_selector=""' scenarios/openshift/pod_egress_shaping.yml

  export scenario_type="network_chaos_ng_scenarios"
  export scenario_file="scenarios/openshift/pod_egress_shaping.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/network_chaos.yaml

  # check if nginx is reachable before the chaos
  if ! curl curl --max-time 1 $SERVICE_URL>/dev/null 2>&1; then echo "failed to contact nginx"; exit 1; fi
  python3 -m coverage run -a run_kraken.py -c CI/config/network_chaos.yaml&
  PID=$!
  # check if the latency introduced makes the curl request fail
  if curl --max-time 1 $SERVICE_URL>/dev/null 2>&1; then echo "latency injection was not successful"; exit 1; fi
  wait $PID
  # check if connectivity has been restored
  if ! curl curl --max-time 1 $SERVICE_URL>/dev/null 2>&1; then echo "failed to contact nginx"; exit 1; fi
  echo "Pod Network Chaos test (Egress): Success"
}



functional_test_pod_network_chaos