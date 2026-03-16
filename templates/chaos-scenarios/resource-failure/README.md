# Resource Failure Chaos Scenario

## Description
This scenario simulates Kubernetes resource failures by deleting, modifying, or corrupting various Kubernetes resources to test cluster resiliency and recovery mechanisms.

## Risk Level
**Medium** - This will cause resource unavailability and service disruption.

## Target
Kubernetes Resources

## Usage

### Basic Usage
```bash
krkn run-template resource-failure
```

### With Custom Parameters
```bash
krkn run-template resource-failure \
  --param resource_type="service" \
  --param name_pattern="^web-service-.*$" \
  --param failure_action="delete" \
  --param failure_duration=600
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_type` | string | `"deployment"` | Resource type: deployment, service, configmap, secret, etc. |
| `name_pattern` | string | `^app-.*$` | Regex pattern to match resource names |
| `namespace_pattern` | string | `^default$` | Regex pattern to match namespace names |
| `failure_action` | string | `"delete"` | Failure action: delete, modify, or corrupt |
| `failure_duration` | integer | `300` | Duration of resource failure in seconds |
| `resource_count` | integer | `1` | Number of resources to impact |

## Failure Actions

- **delete**: Completely removes the resource
- **modify**: Changes resource configuration (e.g., set replicas to 0)
- **corrupt**: Introduces invalid configuration to test error handling

## What Happens
1. KRKN identifies resources matching the type, name, and namespace patterns
2. Applies the specified failure action to target resources
3. Monitors resource status during failure
4. Restores resources after the specified duration (if applicable)
5. Monitors resource recovery and service availability
6. Reports on resource resiliency and recovery success

## Prerequisites
- Target resources must exist
- Sufficient permissions to manage specified resource types
- Backup and recovery strategies should be in place
- Applications should handle resource unavailability gracefully

## Cleanup
Resources are automatically restored after the specified duration (for modify/corrupt actions). Deleted resources may require manual recreation.

## Example Output
```
✓ Found 2 deployments matching pattern ^app-.*$ in namespace default
✓ Deleting deployment app-deployment-1
✓ Resource failure active for 300 seconds...
✓ Restoring deployment app-deployment-1
✓ Deployment successfully restored
✓ All resources recovered successfully
```
