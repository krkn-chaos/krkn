# Network Latency Chaos Scenario

## Description
This scenario introduces network latency, jitter, and bandwidth limitations to test application performance under degraded network conditions.

## Risk Level
**Medium** - This will affect network performance and may cause service degradation.

## Target
Kubernetes Network

## Usage

### Basic Usage
```bash
krkn run-template network-latency
```

### With Custom Parameters
```bash
krkn run-template network-latency \
  --param latency="200ms" \
  --param jitter="20ms" \
  --param bandwidth="5mbit" \
  --param duration=120 \
  --param name_pattern="^microservice-.*$"
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `latency` | string | `"100ms"` | Network latency to introduce |
| `jitter` | string | `"10ms"` | Latency variation |
| `bandwidth` | string | `"10mbit"` | Bandwidth limit |
| `target` | string | `"pod"` | Target type: pod, node, or service |
| `namespace_pattern` | string | `"^default$"` | Target namespace pattern |
| `name_pattern` | string | `"^app-.*$"` | Target pod/service name pattern |
| `duration` | integer | `60` | Duration of network chaos in seconds |

## What Happens
1. KRKN identifies target pods/services based on patterns
2. Injects network latency using tc (traffic control)
3. Applies bandwidth limitations and jitter
4. Monitors application behavior during chaos
5. Removes network chaos after specified duration
6. Reports on application resilience

## Prerequisites
- Sufficient permissions to modify network settings
- Target pods must be running
- Network policies must allow chaos injection

## Cleanup
Network chaos is automatically removed after the specified duration.

## Example Output
```
✓ Found 2 pods matching pattern ^app-.*$ in namespace default
✓ Injecting 100ms latency with 10ms jitter
✓ Limiting bandwidth to 10mbit
✓ Network chaos active for 60 seconds...
✓ Network chaos removed successfully
✓ Application recovered to normal performance
```
