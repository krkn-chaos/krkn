# VM Outage Chaos Scenario

## Description
This scenario simulates VM outages in OpenShift Virtualization environments to test virtual machine resiliency and recovery mechanisms.

## Risk Level
**High** - This will cause actual VM downtime and service disruption.

## Target
OpenShift Virtual Machines (KubeVirt)

## Usage

### Basic Usage
```bash
krkn run-template vm-outage
```

### With Custom Parameters
```bash
krkn run-template vm-outage \
  --param vm_name_pattern="^web-vm-.*$" \
  --param outage_type="stop" \
  --param outage_duration=600 \
  --param vm_count=2
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `vm_name_pattern` | string | `^vm-.*$` | Regex pattern to match VM names |
| `namespace_pattern` | string | `^default$` | Regex pattern to match namespace names |
| `outage_type` | string | `"stop"` | Outage type: stop, pause, or force-stop |
| `outage_duration` | integer | `300` | Duration of VM outage in seconds |
| `vm_count` | integer | `1` | Number of VMs to impact |

## Outage Types

- **stop**: Graceful VM shutdown
- **pause**: Pauses VM execution (preserves memory state)
- **force-stop**: Immediate VM power off without graceful shutdown

## What Happens
1. KRKN identifies VMs matching the name and namespace patterns
2. Applies the specified outage type to target VMs
3. Monitors VM status during outage
4. Restarts VMs after the specified duration
5. Monitors VM recovery and service availability
6. Reports on VM resiliency and recovery success

## Prerequisites
- OpenShift Virtualization (KubeVirt) must be installed
- Target VMs must exist and be running
- Sufficient permissions to manage VMs
- Proper VM backup and recovery strategies should be in place

## Cleanup
VMs are automatically restarted after the specified outage duration.

## Example Output
```
✓ Found 2 VMs matching pattern ^vm-.*$ in namespace default
✓ Stopping VM web-vm-1
✓ VM outage active for 300 seconds...
✓ Restarting VM web-vm-1
✓ VM successfully restarted and running
✓ All VMs recovered successfully
```
