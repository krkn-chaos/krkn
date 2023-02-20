set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_app_outage {
  [ -z $DEPLOYMENT_NAME ] && echo "[ERR] DEPLOYMENT_NAME variable not set, failing." && exit 1
  yq -i '.application_outage.pod_selector={"app":"'$DEPLOYMENT_NAME'"}' CI/scenarios/app_outage.yaml
  yq -i '.application_outage.namespace="'$NAMESPACE'"' CI/scenarios/app_outage.yaml
  export scenario_type="application_outages"
  export scenario_file="CI/scenarios/app_outage.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/app_outage.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/app_outage.yaml
  echo "App outage scenario test: Success"
}

functional_test_app_outage
