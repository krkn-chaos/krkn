# CPU Stress Chaos Scenario

## Description
This scenario applies CPU stress to target nodes to test application performance and resource management under high CPU load conditions.

## Risk Level
**Medium** - This will cause high CPU utilization and may affect application performance.

## Target
Kubernetes Nodes

## Usage

### Basic Usage
```bash
krkn run-template cpu-stress
```

### With Custom Parameters
```bash
krkn run-template cpu-stress \
  --param duration=120 \
  --param cpu-load-percentage=95 \
  --param number-of-nodes=2 \
  --param node-selector="node-role.kubernetes.io/worker="
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `duration` | integer | `60` | Duration of CPU stress in seconds |
| `workers` | string | `""` | Number of worker processes (empty for auto-detection) |
| `cpu-load-percentage` | integer | `90` | Target CPU load percentage |
| `cpu-method` | string | `"all"` | CPU stress method (all, single, or specific core) |
| `node-selector` | string | `"node-role.kubernetes.io/worker="` | Node selector for targeting specific nodes |
| `number-of-nodes` | integer | `1` | Number of nodes to stress |
| `taints` | array | `[]` | Node taints to consider/exclude |

## What Happens
1. KRKN deploys stress test pods on target nodes
2. Stress pods generate high CPU load using stress-ng
3. CPU utilization is monitored and maintained at target level
4. Applications on affected nodes are tested for performance degradation
5. Stress pods are terminated after specified duration
6. System recovery is monitored

## Prerequisites
- Sufficient CPU resources on target nodes
- Permissions to deploy pods on target nodes
- Resource limits should be configured for critical applications

## Cleanup
Stress test pods are automatically terminated after the specified duration.

## Example Output
```
✓ Found 2 worker nodes matching selector
✓ Deploying CPU stress on node worker-1
✓ Target CPU load: 90%
✓ Stress test running for 60 seconds...
✓ CPU load maintained at 90% ± 5%
✓ Stress test completed
✓ System recovered to normal CPU utilization
```
