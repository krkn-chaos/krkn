set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_litmus_mem {
  [ -z $NODE_NAME ] && echo "[ERR] NODE_NAME variable not set, failing." && exit 1
  yq -i ' .spec.experiments = [{"name": "node-io-stress", "spec":{"components":{"env":[{"name":"TOTAL_CHAOS_DURATION","value":"10"},{"name":"CPU","value":"1"},{"name":"TARGET_NODES","value":"'$NODE_NAME'"}]}}}]' CI/scenarios/node_mem_engine_node.yaml
  cp CI/config/common_test_config.yaml CI/config/litmus_config.yaml
  yq '.kraken.chaos_scenarios = [{"litmus_scenarios":[["scenarios/openshift/templates/litmus-rbac.yaml","CI/scenarios/node_mem_engine_node.yaml"]]}]' -i CI/config/litmus_config.yaml

  python3 -m coverage run -a run_kraken.py -c CI/config/litmus_config.yaml
  echo "Litmus scenario test: Success"
}

functional_test_litmus_mem
