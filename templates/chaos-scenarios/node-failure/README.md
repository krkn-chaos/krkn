# Node Failure Chaos Scenario

## Description
This scenario simulates node failure by terminating or shutting down Kubernetes nodes to test cluster resiliency and failover mechanisms.

## Risk Level
**High** - This will cause actual node termination and significant service disruption.

## Target
Kubernetes Nodes

## Usage

### Basic Usage
```bash
krkn run-template node-failure
```

### With Custom Parameters
```bash
krkn run-template node-failure \
  --param label_selector="node-role.kubernetes.io/worker=" \
  --param node_count=1 \
  --param wait_duration=600 \
  --param force_termination=true
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `node_name` | string | `""` | Specific node name to target (empty for random selection) |
| `instance_type` | string | `""` | Cloud instance type filter (for cloud environments) |
| `label_selector` | string | `"node-role.kubernetes.io/worker="` | Label selector to target nodes |
| `wait_duration` | integer | `300` | Time to wait for node recovery in seconds |
| `force_termination` | boolean | `false` | Force node termination instead of graceful shutdown |
| `node_count` | integer | `1` | Number of nodes to impact |

## What Happens
1. KRKN identifies target nodes based on criteria
2. Initiates node shutdown or termination
3. Monitors node recovery for the specified duration
4. Reports on cluster failover and recovery success

## Prerequisites
- Sufficient cluster size to handle node loss
- Proper pod anti-affinity and disruption budgets
- Cloud provider permissions (if applicable)
- Cluster auto-scaling configured (recommended)

## Cleanup
- Terminated nodes should be automatically replaced by cluster auto-scaler
- Manual intervention may be required for on-premise clusters

## Example Output
```
✓ Found 3 worker nodes matching criteria
✓ Selected node worker-1 for termination
✓ Initiated node termination
✓ Waiting 300 seconds for node recovery...
✓ Node successfully replaced by new instance
✓ All pods rescheduled and running
```
