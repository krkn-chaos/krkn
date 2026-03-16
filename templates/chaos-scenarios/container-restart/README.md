# Container Restart Chaos Scenario

## Description
This scenario restarts containers within pods to test application resiliency and recovery mechanisms at the container level.

## Risk Level
**Medium** - This will cause container restarts and temporary service disruption.

## Target
Kubernetes Containers

## Usage

### Basic Usage
```bash
krkn run-template container-restart
```

### With Custom Parameters
```bash
krkn run-template container-restart \
  --param name_pattern="^nginx-.*$" \
  --param container_name="nginx" \
  --param restart_count=2 \
  --param wait_between_restarts=60
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name_pattern` | string | `^app-.*$` | Regex pattern to match pod names |
| `namespace_pattern` | string | `^default$` | Regex pattern to match namespace names |
| `container_name` | string | `""` | Specific container name (empty for all containers) |
| `restart_count` | integer | `1` | Number of restarts to perform |
| `wait_between_restarts` | integer | `30` | Wait time between restarts in seconds |
| `krkn_container_recovery_time` | integer | `120` | Time to wait for container recovery in seconds |

## What Happens
1. KRKN identifies pods matching the name and namespace patterns
2. Identifies target containers within those pods
3. Restarts containers using Kubernetes API
4. Waits for specified time between restarts (if multiple)
5. Monitors container recovery for the specified duration
6. Reports on the success of container recreation

## Prerequisites
- Target pods must exist and be running
- Sufficient permissions to restart containers
- Pod should have proper restart policies configured
- Application should handle container restarts gracefully

## Cleanup
No manual cleanup required - restarted containers are automatically managed by Kubernetes.

## Example Output
```
✓ Found 2 pods matching pattern ^app-.*$ in namespace default
✓ Found 3 containers in pod app-pod-1
✓ Restarting container app-container
✓ Waiting 120 seconds for container recovery...
✓ Container successfully restarted and running
✓ All containers recovered successfully
```
