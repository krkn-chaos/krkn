set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_app_outage {
  yq -i '.application_outage.duration=10' scenarios/openshift/app_outage.yaml
  yq -i '.application_outage.pod_selector={"scenario":"outage"}' scenarios/openshift/app_outage.yaml
  yq -i '.application_outage.namespace="default"' scenarios/openshift/app_outage.yaml
  export scenario_type="application_outages"
  export scenario_file="scenarios/openshift/app_outage.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/app_outage.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/app_outage.yaml
  echo "App outage scenario test: Success"
}

functional_test_app_outage
