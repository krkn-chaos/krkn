# Pod Kill Chaos Scenario

## Description
This scenario forcefully terminates pods to test application recovery mechanisms and restart policies. Unlike pod failure which simulates crashes, pod kill directly terminates pods to test graceful shutdown handling.

## Use Cases
- Test pod restart policies
- Verify graceful shutdown behavior
- Test application startup procedures
- Validate deployment recovery

## Risk Level
**Medium** - This will forcefully terminate running pods, causing immediate service disruption.

## Prerequisites
- Target pods should have proper restart policies
- Applications should handle SIGTERM/SIGKILL signals
- Ensure sufficient pod replicas are running

## Usage

### Basic Usage
```bash
krkn run-template pod-kill
```

### With Custom Parameters
```bash
krkn run-template pod-kill \
  --param name_pattern="^frontend-.*$" \
  --param namespace_pattern="^production$" \
  --param kill=2 \
  --param force=true
```

### Target Specific Application
```bash
krkn run-template pod-kill \
  --param name_pattern="^nginx-deployment-.*$" \
  --param krkn_pod_recovery_time=180
```

## Expected Behavior
1. KRKN identifies pods matching specified patterns
2. Forcefully terminates the configured number of pods
3. Monitors pod recreation and recovery
4. Waits for pods to become ready again
5. Reports success/failure based on recovery

## Difference from Pod Failure
- **Pod Kill**: Forceful termination with SIGKILL
- **Pod Failure**: Simulates application crash
- **Pod Kill** tests graceful shutdown and restart
- **Pod Failure** tests crash recovery

## Customization
You can customize this scenario by modifying:
- `name_pattern`: Target specific pod naming conventions
- `namespace_pattern`: Target specific namespaces
- `kill`: Number of pods to terminate
- `force`: Force kill without grace period
- `krkn_pod_recovery_time`: Recovery monitoring duration

## Application Requirements
- Handle SIGTERM for graceful shutdown
- Implement proper startup procedures
- Configure appropriate restart policies
- Design for stateless operation when possible

## Troubleshooting
- Check pod restart policies
- Verify application signal handling
- Monitor pod logs during termination
- Check resource constraints preventing restart

## Best Practices
- Test with different restart policies
- Monitor application metrics during restart
- Ensure proper health checks configured
- Document expected recovery times

## Related Scenarios
- [Pod Failure](../pod-failure/)
- [Container Restart](../container-restart/)
- [Node Failure](../node-failure/)
