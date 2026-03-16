# Disk Stress Chaos Scenario

## Description
This scenario applies disk I/O stress to target nodes to test application performance and storage subsystem under high disk load conditions.

## Risk Level
**Medium** - This will cause high disk I/O and may affect application performance.

## Target
Kubernetes Nodes

## Usage

### Basic Usage
```bash
krkn run-template disk-stress
```

### With Custom Parameters
```bash
krkn run-template disk-stress \
  --param duration=120 \
  --param io-load-percentage=90 \
  --param io-file-size="2G" \
  --param number-of-nodes=2
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `duration` | integer | `60` | Duration of disk stress in seconds |
| `workers` | string | `""` | Number of worker processes (empty for auto-detection) |
| `io-load-percentage` | integer | `80` | Target I/O load percentage |
| `io-file-size` | string | `"1G"` | Size of test files for I/O operations |
| `io-block-size` | string | `"4K"` | Block size for I/O operations |
| `node-selector` | string | `"node-role.kubernetes.io/worker="` | Node selector for targeting specific nodes |
| `number-of-nodes` | integer | `1` | Number of nodes to stress |
| `taints` | array | `[]` | Node taints to consider/exclude |

## What Happens
1. KRKN deploys disk stress pods on target nodes
2. Stress pods generate high disk I/O using stress-ng
3. Disk utilization is monitored and maintained at target level
4. Applications on affected nodes are tested for performance degradation
5. Stress pods are terminated after specified duration
6. System recovery is monitored

## Prerequisites
- Sufficient disk space on target nodes
- Permissions to deploy pods on target nodes
- Storage performance monitoring should be in place

## Cleanup
Stress test pods are automatically terminated after the specified duration.

## Example Output
```
✓ Found 2 worker nodes matching selector
✓ Deploying disk stress on node worker-1
✓ Target I/O load: 80%
✓ Stress test running for 60 seconds...
✓ I/O load maintained at 80% ± 5%
✓ Stress test completed
✓ System recovered to normal I/O performance
```
