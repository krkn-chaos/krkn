# Pod Failure Chaos Scenario

## Description
This scenario simulates pod failures by terminating pods that match specified patterns. It helps test your application's ability to recover from pod crashes and maintain availability.

## Use Cases
- Test application restart policies
- Verify pod disruption budgets
- Validate self-healing mechanisms
- Test load balancer failover

## Risk Level
**Medium** - This will terminate running pods, which may cause temporary service disruption.

## Prerequisites
- Target pods should have proper restart policies
- Applications should be designed to handle pod restarts
- Ensure sufficient pod replicas are running

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
  --param kill=2
```

### Using Configuration File
```bash
krkn run-template pod-failure --config custom-config.yaml
```

## Expected Behavior
1. KRKN identifies pods matching the specified patterns
2. Terminates the configured number of pods
3. Monitors pod recovery for the specified duration
4. Reports success/failure based on recovery

## Customization
You can customize this scenario by modifying:
- `name_pattern`: Target specific pod naming conventions
- `namespace_pattern`: Target specific namespaces
- `kill`: Number of pods to terminate
- `krkn_pod_recovery_time`: Recovery monitoring duration

## Troubleshooting
- Ensure pods have proper restart policies
- Check if pod disruption budgets are preventing termination
- Verify namespace and pod name patterns are correct
- Monitor pod logs during recovery

## Related Scenarios
- [Container Restart](../container-restart/)
- [Node Failure](../node-failure/)
- [Network Latency](../network-latency/)
