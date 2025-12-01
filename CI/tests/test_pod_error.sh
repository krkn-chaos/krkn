
source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_pod_error {
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/kind/pod_etcd.yml"
  export post_config=""
  yq -i '.[0].config.kill=5' scenarios/kind/pod_etcd.yml
  envsubst < CI/config/common_test_config.yaml > CI/config/pod_config.yaml
  cat CI/config/pod_config.yaml

  cat scenarios/kind/pod_etcd.yml
  python3 -m coverage run -a run_kraken.py -c CI/config/pod_config.yaml
  
  ret=$?
  echo "\n\nret $ret"
  if [[ $ret -ge 1 ]]; then
      echo "Pod disruption error scenario test: Success"
  else 
    echo "Pod disruption error scenario test: Failure"
    exit 1
  fi
}

functional_test_pod_error
