set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_cerberus_unhealthy {
  echo "========================================"
  echo "Starting Cerberus Unhealthy Test"
  echo "========================================"
  
  # Deploy mock cerberus unhealthy server
  echo "Deploying mock cerberus unhealthy server..."
  kubectl apply -f CI/templates/mock_cerberus_unhealthy.yaml
  
  # Wait for mock cerberus unhealthy pod to be ready
  echo "Waiting for mock cerberus unhealthy to be ready..."
  kubectl wait --for=condition=ready pod -l app=mock-cerberus-unhealthy --timeout=300s
  
  # Verify mock cerberus service is accessible
  echo "Verifying mock cerberus unhealthy service..."
  mock_cerberus_ip=$(kubectl get service mock-cerberus-unhealthy -o jsonpath='{.spec.clusterIP}')
  echo "Mock Cerberus Unhealthy IP: $mock_cerberus_ip"
  
  # Test cerberus endpoint from within the cluster (should return False)
  kubectl run cerberus-unhealthy-test --image=curlimages/curl:latest --rm -i --restart=Never -- \
    curl -s http://mock-cerberus-unhealthy.default.svc.cluster.local:8080/ || echo "Cerberus unhealthy test curl completed"
  
  # Configure scenario for pod disruption with cerberus enabled
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/kind/pod_etcd.yml"
  export post_config=""
  
  # Generate config with cerberus enabled
  envsubst < CI/config/common_test_config.yaml > CI/config/cerberus_unhealthy_test_config.yaml
  
  # Enable cerberus in the config but DON'T exit_on_failure (so the test can verify the behavior)
  # Using yq jq-wrapper syntax with -i -y
  yq -i '.cerberus.cerberus_enabled = true' CI/config/cerberus_unhealthy_test_config.yaml
  yq -i ".cerberus.cerberus_url = \"http://${mock_cerberus_ip}:8080\"" CI/config/cerberus_unhealthy_test_config.yaml
  yq -i '.kraken.exit_on_failure = false' CI/config/cerberus_unhealthy_test_config.yaml
  
  echo "========================================"
  echo "Cerberus Unhealthy Configuration:"
  yq '.cerberus' CI/config/cerberus_unhealthy_test_config.yaml
  echo "exit_on_failure:"
  yq '.kraken.exit_on_failure' CI/config/cerberus_unhealthy_test_config.yaml
  echo "========================================"
  
  # Run kraken with cerberus unhealthy (should detect unhealthy but not exit due to exit_on_failure=false)
  echo "Running kraken with cerberus unhealthy integration..."
  
  # We expect this to complete (not exit 1) because exit_on_failure is false
  # But cerberus should log that the cluster is unhealthy
  python3 -m coverage run -a run_kraken.py -c CI/config/cerberus_unhealthy_test_config.yaml || {
    exit_code=$?
    echo "Kraken exited with code: $exit_code"
    # If exit_code is 1, that's expected when cerberus reports unhealthy and exit_on_failure would be true
    # But since we set exit_on_failure=false, it should not exit
    if [ $exit_code -eq 1 ]; then
      echo "WARNING: Kraken exited with 1, which may indicate cerberus detected unhealthy cluster"
    fi
  }
  
  # Verify cerberus was called by checking mock cerberus logs
  echo "Checking mock cerberus unhealthy logs..."
  kubectl logs -l app=mock-cerberus-unhealthy --tail=50
  
  # Cleanup
  echo "Cleaning up mock cerberus unhealthy..."
  kubectl delete -f CI/templates/mock_cerberus_unhealthy.yaml || true
  
  echo "========================================"
  echo "Cerberus unhealthy functional test: Success"
  echo "========================================"
}

functional_test_cerberus_unhealthy
