# CPU Stress Chaos Scenario

## Description
This scenario applies CPU stress to test application performance under high CPU load conditions. It helps identify performance bottlenecks, scaling issues, and resource contention problems.

## Use Cases
- Test application performance under load
- Verify auto-scaling configurations
- Identify CPU bottlenecks
- Test resource limits and requests

## Risk Level
**Medium** - High CPU usage may affect application performance and cluster responsiveness.

## Prerequisites
- Sufficient cluster resources
- Target nodes should have available CPU capacity
- Appropriate resource limits configured

## Usage

### Basic Usage
```bash
krkn run-template cpu-stress
```

### With Custom Load
```bash
krkn run-template cpu-stress \
  --param cpu-load-percentage=90 \
  --param duration=120 \
  --param number-of-nodes=2
```

### Target Specific Nodes
```bash
krkn run-template cpu-stress \
  --param node-selector="node-role.kubernetes.io/app=" \
  --param workers="4"
```

## Expected Behavior
1. KRKN deploys CPU stress pods on target nodes
2. Stress pods generate CPU load according to configuration
3. Maintains load for specified duration
4. Monitors system and application performance
5. Cleans up stress pods and reports results

## Performance Impact
- Increased CPU utilization on target nodes
- Potential application response time degradation
- Reduced cluster responsiveness
- Possible pod eviction if resources exceeded

## Customization
You can customize this scenario by modifying:
- `cpu-load-percentage`: Target CPU load (0-100)
- `duration`: How long stress persists
- `workers`: Number of stress processes
- `number-of-nodes`: Nodes to stress
- `node-selector`: Target specific node types

## Monitoring Recommendations
- Monitor CPU utilization metrics
- Watch application response times
- Check for pod evictions
- Monitor node health status

## Safety Considerations
- Start with lower CPU percentages
- Monitor cluster health during execution
- Ensure sufficient headroom in cluster capacity
- Have rollback procedures ready

## Troubleshooting
- Check if stress pods are running
- Verify node resource availability
- Monitor pod logs for errors
- Check RBAC permissions

## Best Practices
- Test in non-production environments first
- Gradually increase stress levels
- Monitor application performance metrics
- Document baseline performance

## Related Scenarios
- [Memory Stress](../memory-stress/)
- [Disk Stress](../disk-stress/)
- [Network Latency](../network-latency/)
