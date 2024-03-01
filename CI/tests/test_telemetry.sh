set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT


function functional_test_telemetry {
  AWS_CLI=`which aws`
  [ -z "$AWS_CLI" ]&& echo "AWS cli not found in path" && exit 1
  [ -z "$AWS_BUCKET" ] && echo "AWS bucket not set in environment" && exit 1

  export RUN_TAG="funtest-telemetry"
  yq -i '.telemetry.enabled=True' CI/config/common_test_config.yaml
  yq -i '.telemetry.full_prometheus_backup=True' CI/config/common_test_config.yaml
  yq -i '.performance_monitoring.check_critical_alerts=True' CI/config/common_test_config.yaml
  yq -i '.performance_monitoring.prometheus_url="http://localhost:9090"' CI/config/common_test_config.yaml
  yq -i '.telemetry.run_tag=env(RUN_TAG)' CI/config/common_test_config.yaml

  export scenario_type="arcaflow_scenarios"
  export scenario_file="scenarios/arcaflow/cpu-hog/input.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/telemetry.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/telemetry.yaml
  RUN_FOLDER=`cat CI/out/test_telemetry.out | grep amazonaws.com | sed -rn "s#.*https:\/\/.*\/files/(.*)#\1#p"`
  $AWS_CLI s3 ls "s3://$AWS_BUCKET/$RUN_FOLDER/" | awk '{ print $4 }' > s3_remote_files
  echo "checking if telemetry files are uploaded on s3"
  cat s3_remote_files | grep events-00.json || ( echo "FAILED: events-00.json not uploaded" && exit 1 )
  cat s3_remote_files | grep critical-alerts-00.json || ( echo "FAILED: critical-alerts-00.json not uploaded" && exit 1 )
  cat s3_remote_files | grep prometheus-00.tar || ( echo "FAILED: prometheus backup not uploaded" && exit 1 )
  cat s3_remote_files | grep telemetry.json || ( echo "FAILED: telemetry.json not uploaded" && exit 1 )
  echo "all files uploaded!"
  echo "Telemetry Collection: Success"
}

functional_test_telemetry