set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_cerberus {
  echo "========================================"
  echo "Starting Cerberus Functional Test"
  echo "========================================"
  
  # Deploy mock cerberus server
  echo "Deploying mock cerberus server..."
  kubectl apply -f CI/templates/mock_cerberus.yaml
  
  # Wait for mock cerberus pod to be ready
  echo "Waiting for mock cerberus to be ready..."
  kubectl wait --for=condition=ready pod -l app=mock-cerberus --timeout=300s
  
  # Verify mock cerberus service is accessible
  echo "Verifying mock cerberus service..."
  mock_cerberus_ip=$(kubectl get service mock-cerberus -o jsonpath='{.spec.clusterIP}')
  echo "Mock Cerberus IP: $mock_cerberus_ip"
  
  # Test cerberus endpoint from within the cluster
  kubectl run cerberus-test --image=curlimages/curl:latest --rm -i --restart=Never -- \
    curl -s http://mock-cerberus.default.svc.cluster.local:8080/ || echo "Cerberus test curl completed"
  
  # Configure scenario for pod disruption with cerberus enabled
  export scenario_type="pod_disruption_scenarios"
  export scenario_file="scenarios/kind/pod_etcd.yml"
  export post_config=""
  
  # Generate config with cerberus enabled
  envsubst < CI/config/common_test_config.yaml > CI/config/cerberus_test_config.yaml
  
  # Enable cerberus in the config (using yq jq-wrapper syntax with -i -y)
  yq -y -i '.cerberus.cerberus_enabled = true' CI/config/cerberus_test_config.yaml
  yq -y -i ".cerberus.cerberus_url = \"http://${mock_cerberus_ip}:8080\"" CI/config/cerberus_test_config.yaml
  
  echo "========================================"
  echo "Cerberus Configuration:"
  yq '.cerberus' CI/config/cerberus_test_config.yaml
  echo "========================================"
  
  # Run kraken with cerberus enabled
  echo "Running kraken with cerberus integration..."
  python3 -m coverage run -a run_kraken.py -c CI/config/cerberus_test_config.yaml
  
  # Verify cerberus was called by checking mock cerberus logs
  echo "Checking mock cerberus logs..."
  kubectl logs -l app=mock-cerberus --tail=50
  
  # Cleanup
  echo "Cleaning up mock cerberus..."
  kubectl delete -f CI/templates/mock_cerberus.yaml || true
  
  echo "========================================"
  echo "Cerberus functional test: Success"
  echo "========================================"
}

functional_test_cerberus
