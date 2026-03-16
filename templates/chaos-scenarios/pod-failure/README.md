# Pod Failure Chaos Scenario

## Description
This scenario simulates pod failures by terminating specified pods to test application resiliency and recovery mechanisms.

## Risk Level
**Medium** - This will cause actual pod termination and service disruption.

## Target
Kubernetes Pods

## Usage

### Basic Usage
```bash
krkn run-template pod-failure
```

### With Custom Parameters
```bash
krkn run-template pod-failure \
  --param name_pattern="^nginx-.*$" \
  --param namespace_pattern="^production$" \
  --param kill=2 \
  --param krkn_pod_recovery_time=180
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name_pattern` | string | `^app-.*$` | Regex pattern to match pod names |
| `namespace_pattern` | string | `^default$` | Regex pattern to match namespace names |
| `kill` | integer | `1` | Number of pods to terminate |
| `krkn_pod_recovery_time` | integer | `120` | Time to wait for pod recovery in seconds |

## What Happens
1. KRKN identifies pods matching the name and namespace patterns
2. Terminates the specified number of pods
3. Monitors pod recovery for the specified duration
4. Reports on the success of pod recreation

## Prerequisites
- Target pods must exist
- Sufficient permissions to terminate pods
- ReplicaSet or Deployment should be configured to recreate terminated pods

## Cleanup
No manual cleanup required - terminated pods should be automatically recreated by their controllers.

## Example Output
```
✓ Found 3 pods matching pattern ^app-.*$ in namespace default
✓ Terminated pod app-pod-1
✓ Waiting 120 seconds for pod recovery...
✓ Pod app-pod-1 successfully recreated
✓ All pods recovered successfully
```
