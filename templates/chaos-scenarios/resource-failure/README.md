# Resource Failure Chaos Scenario

## Description
This scenario simulates failures for various Kubernetes resources including deployments, services, configmaps, and secrets. It tests the cluster's ability to handle resource-level failures and recover appropriately.

## Use Cases
- Test deployment recovery mechanisms
- Verify service discovery resilience
- Test configuration management
- Validate resource recreation procedures

## Risk Level
**Medium** - Resource failures can cause service disruption depending on the resource type and availability.

## Prerequisites
- Target resources should be properly configured
- Backup procedures for critical resources
- Appropriate RBAC permissions for resource management

## Usage

### Basic Usage
```bash
krkn run-template resource-failure
```

### Target Different Resource Type
```bash
krkn run-template resource-failure \
  --param resource_type="service" \
  --param resource_name_pattern="^.*-service-.*$" \
  --param action="delete"
```

### Scale to Zero Instead of Delete
```bash
krkn run-template resource-failure \
  --param resource_type="deployment" \
  --param action="scale-to-zero" \
  --param recovery_time=180
```

### Edit Resource Configuration
```bash
krkn run-template resource-failure \
  --param resource_type="deployment" \
  --param action="edit" \
  --param resource_name_pattern="^frontend-.*$"
```

## Expected Behavior
1. KRKN identifies resources matching specified patterns
2. Executes the configured action (delete/scale/edit)
3. Monitors resource status during the action
4. Waits for resource recovery or timeout
5. Reports success/failure based on recovery

## Resource Types and Actions

### Deployments
- **delete**: Removes the deployment
- **scale-to-zero**: Sets replicas to 0
- **edit**: Modifies deployment configuration

### Services
- **delete**: Removes the service
- **edit**: Modifies service configuration

### ConfigMaps/Secrets
- **delete**: Removes the resource
- **edit**: Modifies resource content

## Customization
You can customize this scenario by modifying:
- `resource_type`: Type of Kubernetes resource
- `resource_name_pattern`: Target specific naming conventions
- `namespace_pattern`: Target specific namespaces
- `action`: Type of operation to perform
- `recovery_time`: Recovery monitoring duration

## Safety Considerations
- Test in non-production environments first
- Ensure resource backups are available
- Monitor application dependencies
- Have rollback procedures ready

## Monitoring Recommendations
- Monitor resource status and health
- Watch for application errors
- Check service discovery updates
- Monitor configuration reloads

## Troubleshooting
- Check resource permissions and RBAC
- Verify resource configurations
- Monitor controller logs
- Check for resource dependencies

## Best Practices
- Document resource recovery procedures
- Test different resource configurations
- Monitor application behavior
- Ensure proper resource sizing

## Related Scenarios
- [Pod Failure](../pod-failure/)
- [Node Failure](../node-failure/)
- [Container Restart](../container-restart/)
