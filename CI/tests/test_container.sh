set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

pod_file="CI/scenarios/hello_pod.yaml"

function functional_test_container_crash {
  yq -i '.scenarios[0].namespace="default"' scenarios/openshift/container_etcd.yml
  yq -i '.scenarios[0].label_selector="scenario=container"' scenarios/openshift/container_etcd.yml
  yq -i '.scenarios[0].container_name="fedtools"' scenarios/openshift/container_etcd.yml
  export scenario_type="container_scenarios"
  export scenario_file="scenarios/openshift/container_etcd.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/container_config.yaml

  python3 -m coverage run -a run_kraken.py -c CI/config/container_config.yaml -d True
  echo "Container scenario test: Success"

  kubectl get pods -n kube-system -l component=etcd
}

functional_test_container_crash
