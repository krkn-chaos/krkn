set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_zone_crash {

  export scenario_type="zone_outages"
  export scenario_file="CI/scenarios/zone_outage_env.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/zone3_config.yaml
  envsubst < CI/scenarios/zone_outage.yaml > CI/scenarios/zone_outage_env.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/zone3_config.yaml
  echo "zone3 scenario test: Success"
}

functional_test_zone_crash
