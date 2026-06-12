# Network Latency Chaos Scenario

## Description
This scenario introduces network latency to test how applications perform under poor network conditions. It helps identify timeout issues, performance bottlenecks, and resilience problems.

## Use Cases
- Test application timeout configurations
- Verify retry mechanisms
- Validate circuit breaker patterns
- Test user experience under poor network

## Risk Level
**Low** - This temporarily degrades network performance but doesn't cause service failures.

## Prerequisites
- Network chaos injection capabilities
- Appropriate RBAC permissions
- Target applications should be running

## Usage

### Basic Usage
```bash
krkn run-template network-latency
```

### With Custom Latency
```bash
krkn run-template network-latency \
  --param latency="200ms" \
  --param jitter="20ms" \
  --param duration=120
```

### Target Specific Application
```bash
krkn run-template network-latency \
  --param target_pods="label_selector=app=frontend,namespace=production"
```

## Expected Behavior
1. KRKN identifies target pods/services
2. Injects network latency using network chaos engine
3. Maintains latency for specified duration
4. Monitors application behavior
5. Removes latency injection and reports results

## Performance Impact
- Increased response times
- Potential timeout errors
- Reduced throughput
- User experience degradation

## Customization
You can customize this scenario by modifying:
- `latency`: Amount of delay to introduce
- `jitter`: Variation in latency
- `duration`: How long latency persists
- `target_pods`: Specific applications to target
- `egress/ingress`: Direction of traffic affected

## Monitoring Recommendations
- Monitor application response times
- Check error rates and timeouts
- Watch for retry storms
- Monitor user experience metrics

## Troubleshooting
- Verify network chaos engine is running
- Check RBAC permissions
- Ensure target pods are accessible
- Monitor network interface status

## Best Practices
- Start with low latency values
- Gradually increase intensity
- Monitor application health
- Have rollback procedures ready

## Related Scenarios
- [Pod Network Chaos](../pod-network-chaos/)
- [Node Network Chaos](../node-network-chaos/)
- [CPU Stress](../cpu-stress/)
