# Node Failure Chaos Scenario

## Description
This scenario simulates node failures by stopping/terminating nodes in the cluster. It tests the cluster's ability to handle node loss, redistribute workloads, and maintain service availability.

## Use Cases
- Test cluster self-healing capabilities
- Verify pod eviction and rescheduling
- Validate node replacement procedures
- Test load balancer reconfiguration

## Risk Level
**High** - This will cause complete node failure, potentially affecting multiple pods and services.

## Prerequisites
- Sufficient cluster capacity to handle node loss
- Proper pod disruption budgets configured
- Cluster autoscaler enabled (recommended)
- Cloud provider credentials configured

## Usage

### Basic Usage
```bash
krkn run-template node-failure
```

### With Custom Parameters
```bash
krkn run-template node-failure \
  --param instance_count=1 \
  --param label_selector="node-role.kubernetes.io/worker=" \
  --param timeout=600
```

### Target Specific Node
```bash
krkn run-template node-failure \
  --param node_name="worker-node-3"
```

## Expected Behavior
1. KRKN identifies target nodes based on configuration
2. Initiates node failure (stop/terminate based on platform)
3. Monitors pod eviction and rescheduling
4. Waits for node recovery or timeout
5. Reports cluster status and recovery success

## Cluster Requirements
- Minimum 3 worker nodes for production testing
- Sufficient resource capacity for pod redistribution
- Proper networking configuration for pod migration

## Customization
You can customize this scenario by modifying:
- `instance_count`: Number of nodes to fail
- `node_name`: Target specific node
- `label_selector`: Filter nodes by labels
- `timeout`: Recovery monitoring duration

## Safety Considerations
- Never run on single-node clusters
- Ensure proper backup procedures
- Monitor cluster health during execution
- Have rollback procedures ready

## Troubleshooting
- Check cloud provider credentials
- Verify node permissions
- Monitor cluster resource utilization
- Check pod disruption budget status

## Related Scenarios
- [Pod Failure](../pod-failure/)
- [Network Latency](../network-latency/)
- [Disk Stress](../disk-stress/)
