# Container Restart Chaos Scenario

## Description
This scenario restarts specific containers within pods to test container-level recovery mechanisms. Unlike pod kill which terminates the entire pod, container restart only affects individual containers within pods.

## Use Cases
- Test container restart policies
- Verify multi-container pod resilience
- Test sidecar container recovery
- Validate container startup procedures

## Risk Level
**Low** - Container restarts are less disruptive than pod termination but still cause temporary service interruption.

## Prerequisites
- Target pods should be running
- Container restart policies should be configured
- Applications should handle container restarts gracefully

## Usage

### Basic Usage
```bash
krkn run-template container-restart
```

### Restart Specific Container
```bash
krkn run-template container-restart \
  --param container_name="app-container" \
  --param name_pattern="^frontend-.*$" \
  --param namespace_pattern="^production$"
```

### Multiple Container Restarts
```bash
krkn run-template container-restart \
  --param restart_count=2 \
  --param krkn_pod_recovery_time=180
```

## Expected Behavior
1. KRKN identifies pods matching specified patterns
2. Locates target containers within the pods
3. Restarts the configured number of containers
4. Monitors container recovery and readiness
5. Reports success/failure based on recovery

## Difference from Pod Kill
- **Container Restart**: Only affects specific containers
- **Pod Kill**: Terminates entire pod
- **Container Restart**: Faster recovery, less disruption
- **Pod Kill**: Full pod recreation cycle

## Multi-Container Pod Benefits
- Test sidecar container resilience
- Verify main application container recovery
- Test inter-container communication
- Validate shared volume handling

## Customization
You can customize this scenario by modifying:
- `container_name`: Target specific container
- `name_pattern`: Target specific pod naming conventions
- `namespace_pattern`: Target specific namespaces
- `restart_count`: Number of containers to restart
- `krkn_pod_recovery_time`: Recovery monitoring duration

## Application Requirements
- Containers should handle restarts gracefully
- Implement proper startup sequences
- Configure appropriate health checks
- Design for stateless operation when possible

## Troubleshooting
- Check container restart policies
- Verify container health checks
- Monitor container logs during restart
- Check resource constraints preventing restart

## Best Practices
- Test with different container configurations
- Monitor application metrics during restart
- Ensure proper readiness probes configured
- Document expected recovery times

## Related Scenarios
- [Pod Kill](../pod-kill/)
- [Pod Failure](../pod-failure/)
- [Node Failure](../node-failure/)
