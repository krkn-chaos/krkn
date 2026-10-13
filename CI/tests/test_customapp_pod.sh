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
  # pod count restored, and the scenario times out. Wait for the rollout to
  # fully settle (new pods available and old-generation pods gone) so Kraken
  # baselines on the final pod count instead of overlapping generations.
  kubectl -n kube-system patch deployment coredns --type=strategic -p \
    '{"spec":{"template":{"spec":{"nodeSelector":{"node-role.kubernetes.io/control-plane":""}}}}}'
  kubectl -n kube-system rollout status deployment coredns --timeout=180s
  # rollout status can return while old-generation pods are still Terminating
  # (phase Running); Kraken must not baseline on the overlapping generations.
  for _ in $(seq 1 60); do
    running=$(kubectl -n kube-system get pods -l k8s-app=kube-dns \
      --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    [ "$running" -eq 2 ] && break
    sleep 2
  done

  python3 -m coverage run -a run_kraken.py -c CI/config/customapp_pod_config.yaml -d True
  echo "Pod disruption with node_label_selector test: Success"
}

functional_test_customapp_pod_node_selector
