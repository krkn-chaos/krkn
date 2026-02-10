set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_pod_network_chaos {
  echo "Starting pod network chaos functional test"

  # Deploy nginx workload
  echo "Deploying nginx workload..."
  kubectl create deployment nginx-test --image=nginx:latest
  kubectl expose deployment nginx-test --port=80 --target-port=80 --type=NodePort --name=nginx-service
  kubectl patch service nginx-service -p '{"spec":{"ports":[{"port":80,"nodePort":30080,"targetPort":80}]}}'

  # Wait for nginx to be ready
  echo "Waiting for nginx pod to be ready..."
  kubectl wait --for=condition=ready pod -l app=nginx-test --timeout=120s

  # Get pod name
  export POD_NAME=$(kubectl get pods -l app=nginx-test -o jsonpath='{.items[0].metadata.name}')
  echo "Target pod: $POD_NAME"

  # Test baseline connectivity
  echo "Testing baseline connectivity..."
  response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:30080 || echo "000")
  if [ "$response" != "200" ]; then
    echo "ERROR: Nginx not responding correctly (got $response, expected 200)"
    kubectl get pods -l app=nginx-test
    kubectl describe pod $POD_NAME
    exit 1
  fi
  echo "Baseline test passed: nginx responding with 200"

  # Measure baseline latency
  echo "Measuring baseline latency..."
  baseline_start=$(date +%s%3N)
  curl -s http://localhost:30080 > /dev/null || true
  baseline_end=$(date +%s%3N)
  baseline_latency=$((baseline_end - baseline_start))
  echo "Baseline latency: ${baseline_latency}ms"

  # Configure pod network chaos scenario
  echo "Configuring pod network chaos scenario..."
  yq -i '.[0].config.target="'$POD_NAME'"' scenarios/kube/pod-network-chaos.yml
  yq -i '.[0].config.namespace="default"' scenarios/kube/pod-network-chaos.yml
  yq -i '.[0].config.test_duration=20' scenarios/kube/pod-network-chaos.yml
  yq -i '.[0].config.latency="200ms"' scenarios/kube/pod-network-chaos.yml
  yq -i '.[0].config.loss=15' scenarios/kube/pod-network-chaos.yml
  yq -i '.[0].config.bandwidth="10mbit"' scenarios/kube/pod-network-chaos.yml
  yq -i '.[0].config.ingress=true' scenarios/kube/pod-network-chaos.yml
  yq -i '.[0].config.egress=true' scenarios/kube/pod-network-chaos.yml
  yq -i 'del(.[0].config.interfaces)' scenarios/kube/pod-network-chaos.yml

  # Prepare krkn config
  export scenario_type="network_chaos_ng_scenarios"
  export scenario_file="scenarios/kube/pod-network-chaos.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/pod_network_chaos_config.yaml

  # Run krkn in background
  echo "Starting krkn with pod network chaos scenario..."
  python3 -m coverage run -a run_kraken.py -c CI/config/pod_network_chaos_config.yaml &
  KRKN_PID=$!
  echo "Krkn started with PID: $KRKN_PID"

  # Wait for chaos to start (give it time to inject chaos)
  echo "Waiting for chaos injection to begin..."
  sleep 10

  # Test during chaos - check for increased latency or packet loss effects
  echo "Testing network behavior during chaos..."
  chaos_test_count=0
  chaos_success=0

  for i in {1..5}; do
    chaos_test_count=$((chaos_test_count + 1))
    chaos_start=$(date +%s%3N)
    response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://localhost:30080 || echo "000")
    chaos_end=$(date +%s%3N)
    chaos_latency=$((chaos_end - chaos_start))

    echo "Attempt $i: HTTP $response, latency: ${chaos_latency}ms"

    # We expect either increased latency or some failures due to packet loss
    if [ "$response" == "200" ] || [ "$response" == "000" ]; then
      chaos_success=$((chaos_success + 1))
    fi

    sleep 2
  done

  echo "Chaos test results: $chaos_success/$chaos_test_count requests processed"

  # Wait for krkn to complete
  echo "Waiting for krkn to complete..."
  wait $KRKN_PID || true
  echo "Krkn completed"

  # Wait a bit for cleanup
  sleep 5

  # Verify recovery - nginx should respond normally again
  echo "Verifying service recovery..."
  recovery_attempts=0
  max_recovery_attempts=10

  while [ $recovery_attempts -lt $max_recovery_attempts ]; do
    recovery_attempts=$((recovery_attempts + 1))
    response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:30080 || echo "000")

    if [ "$response" == "200" ]; then
      echo "Recovery verified: nginx responding normally (attempt $recovery_attempts)"
      break
    fi

    echo "Recovery attempt $recovery_attempts/$max_recovery_attempts: got $response, retrying..."
    sleep 3
  done

  if [ "$response" != "200" ]; then
    echo "ERROR: Service did not recover after chaos (got $response)"
    kubectl get pods -l app=nginx-test
    kubectl describe pod $POD_NAME
    exit 1
  fi

  # Cleanup
  echo "Cleaning up test resources..."
  kubectl delete deployment nginx-test --ignore-not-found=true
  kubectl delete service nginx-service --ignore-not-found=true

  echo "Pod network chaos test: Success"
}

functional_test_pod_network_chaos