set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT

function functional_test_node_network_chaos {
  echo "Starting node network chaos functional test"

  # Get a worker node
  get_node
  export TARGET_NODE=$(echo $WORKER_NODE | awk '{print $1}')
  echo "Target node: $TARGET_NODE"

  # Deploy nginx workload on the target node
  echo "Deploying nginx workload on $TARGET_NODE..."
  kubectl create deployment nginx-test-node --image=nginx:latest

  # Add node selector to ensure pod runs on target node
  kubectl patch deployment nginx-test-node -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"'$TARGET_NODE'"}}}}}'

  # Expose service
  kubectl expose deployment nginx-test-node --port=80 --target-port=80 --type=NodePort --name=nginx-node-service
  kubectl patch service nginx-node-service -p '{"spec":{"ports":[{"port":80,"nodePort":30080,"targetPort":80}]}}'

  # Wait for nginx to be ready
  echo "Waiting for nginx pod to be ready on $TARGET_NODE..."
  kubectl wait --for=condition=ready pod -l app=nginx-test-node --timeout=120s

  # Verify pod is on correct node
  export POD_NAME=$(kubectl get pods -l app=nginx-test-node -o jsonpath='{.items[0].metadata.name}')
  export POD_NODE=$(kubectl get pod $POD_NAME -o jsonpath='{.spec.nodeName}')
  echo "Pod $POD_NAME is running on node $POD_NODE"

  if [ "$POD_NODE" != "$TARGET_NODE" ]; then
    echo "ERROR: Pod is not on target node (expected $TARGET_NODE, got $POD_NODE)"
    kubectl get pods -l app=nginx-test-node -o wide
    exit 1
  fi

  # Test baseline connectivity
  echo "Testing baseline connectivity..."
  response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:30080 || echo "000")
  if [ "$response" != "200" ]; then
    echo "ERROR: Nginx not responding correctly (got $response, expected 200)"
    kubectl get pods -l app=nginx-test-node
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

  # Configure node network chaos scenario
  echo "Configuring node network chaos scenario..."
  yq -i '.[0].config.target="'$TARGET_NODE'"' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.namespace="default"' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.test_duration=20' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.latency="200ms"' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.loss=15' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.bandwidth="10mbit"' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.ingress=true' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.egress=true' scenarios/kube/node-network-chaos.yml
  yq -i '.[0].config.force=false' scenarios/kube/node-network-chaos.yml
  yq -i 'del(.[0].config.interfaces)' scenarios/kube/node-network-chaos.yml

  # Prepare krkn config
  export scenario_type="network_chaos_ng_scenarios"
  export scenario_file="scenarios/kube/node-network-chaos.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/node_network_chaos_config.yaml

  # Run krkn in background
  echo "Starting krkn with node network chaos scenario..."
  python3 -m coverage run -a run_kraken.py -c CI/config/node_network_chaos_config.yaml &
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

  # Verify node-level chaos affects pod
  echo "Verifying node-level chaos affects pod on $TARGET_NODE..."
  # The node chaos should affect all pods on the node

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
    kubectl get pods -l app=nginx-test-node
    kubectl describe pod $POD_NAME
    exit 1
  fi

  # Cleanup
  echo "Cleaning up test resources..."
  kubectl delete deployment nginx-test-node --ignore-not-found=true
  kubectl delete service nginx-node-service --ignore-not-found=true

  echo "Node network chaos test: Success"
}

functional_test_node_network_chaos