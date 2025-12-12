set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_pod_crash {
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/kind/pod_etcd.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/pod_config.yaml

  python3 -m coverage run -a run_kraken.py -c CI/config/pod_config.yaml
  echo "Pod disruption scenario test: Success"
  date
  kubectl get pods -n kube-system -l component=etcd -o yaml
}

functional_test_pod_crash
