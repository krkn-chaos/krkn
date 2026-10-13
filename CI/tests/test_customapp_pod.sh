set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_customapp_pod_node_selector {
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/openshift/customapp_pod.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/customapp_pod_config.yaml

  # The scenario's node_label_selector scopes both victim selection and pod
  # recovery to control-plane nodes. Without this pin the replacement pod can
  # be scheduled on a worker, the node-scoped recovery check never sees the
  # pod count restored, and the scenario times out.
  kubectl -n kube-system patch deployment coredns --type=strategic -p \
    '{"spec":{"template":{"spec":{"nodeSelector":{"node-role.kubernetes.io/control-plane":""}}}}}'

  python3 -m coverage run -a run_kraken.py -c CI/config/customapp_pod_config.yaml -d True
  echo "Pod disruption with node_label_selector test: Success"
}

functional_test_customapp_pod_node_selector
