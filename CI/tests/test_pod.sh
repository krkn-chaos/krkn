set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_pod_crash {
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/kind/pod_path_provisioner.yml"

  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/pod_config.yaml
  yq -i '.object_state_checks = {
    "interval": 1,
    "run_during": ["during"],
    "exit_on_failure": false,
    "only_failures": false,
    "config": [{
      "name": "local-pods-ready",
      "kind": "Pod",
      "object_name": "",
      "namespace": "local-path-storage",
      "label_selector": "app=local-path-provisioner",
      "condition": {"type": "Ready", "status": "True"}
    }]
  }' CI/config/pod_config.yaml

  python3 -m coverage run -a run_kraken.py -c CI/config/pod_config.yaml
  echo "Pod disruption scenario test: Success"
  date
  kubectl get pods -n local-path-storage -l app=local-path-provisioner -o yaml
}

functional_test_pod_crash
