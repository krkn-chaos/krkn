# Disk Stress Chaos Scenario

## Description
This scenario applies disk I/O stress to test application performance under high disk load conditions. It helps identify storage bottlenecks, I/O performance issues, and storage-related problems.

## Use Cases
- Test application performance under I/O load
- Verify storage performance characteristics
- Identify disk bottlenecks
- Test storage class performance

## Risk Level
**Medium** - High disk I/O may affect application performance and node responsiveness.

## Prerequisites
- Sufficient disk space available
- Target nodes should have available I/O capacity
- Appropriate storage configurations

## Usage

### Basic Usage
```bash
krkn run-template disk-stress
```

### With Custom I/O Parameters
```bash
krkn run-template disk-stress \
  --param io-size="2G" \
  --param block-size="8k" \
  --param io-type="randread" \
  --param duration=120
```

### Target Multiple Nodes
```bash
krkn run-template disk-stress \
  --param number-of-nodes=2 \
  --param workers=8
```

## Expected Behavior
1. KRKN deploys disk stress pods on target nodes
2. Stress pods generate I/O load according to configuration
3. Maintains load for specified duration
4. Monitors system and application performance
5. Cleans up stress pods and reports results

## Performance Impact
- Increased disk I/O utilization
- Potential application response time degradation
- Reduced storage performance
- Possible storage-related timeouts

## Customization
You can customize this scenario by modifying:
- `io-size`: Amount of data to read/write
- `block-size`: Size of I/O operations
- `io-type`: Type of I/O (read/write/random)
- `workers`: Number of concurrent I/O operations
- `duration`: How long stress persists

## Monitoring Recommendations
- Monitor disk I/O metrics
- Watch application response times
- Check for storage-related errors
- Monitor node disk utilization

## Safety Considerations
- Ensure sufficient disk space
- Monitor disk health during execution
- Avoid running on nodes with critical workloads
- Have rollback procedures ready

## Troubleshooting
- Check if stress pods are running
- Verify disk space availability
- Monitor pod logs for I/O errors
- Check storage class configurations

## Best Practices
- Test in non-production environments first
- Start with lower I/O intensities
- Monitor storage performance metrics
- Document baseline storage performance

## Related Scenarios
- [CPU Stress](../cpu-stress/)
- [Memory Stress](../memory-stress/)
- [Network Latency](../network-latency/)
