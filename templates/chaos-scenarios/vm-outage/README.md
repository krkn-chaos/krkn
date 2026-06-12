# VM Outage Chaos Scenario

## Description
This scenario simulates VM outages for OpenShift Virtualization environments to test VM resilience and recovery mechanisms. It supports various VM actions including stop, restart, and pause operations.

## Use Cases
- Test VM recovery procedures
- Verify VM high availability
- Test virtualization platform resilience
- Validate VM backup and restore

## Risk Level
**High** - VM outages can cause significant service disruption and data loss if not properly managed.

## Prerequisites
- OpenShift Virtualization or KubeVirt installed
- Sufficient VM resources available
- Proper VM backup procedures in place
- Appropriate RBAC permissions for VM management

## Usage

### Basic Usage
```bash
krkn run-template vm-outage
```

### With Custom Action
```bash
krkn run-template vm-outage \
  --param action="restart" \
  --param vm_name_pattern="^production-vm-.*$" \
  --param timeout=600
```

### Target Specific Namespace
```bash
krkn run-template vm-outage \
  --param namespace_pattern="^vm-workspace$" \
  --param action="pause" \
  --param recovery_time=300
```

## Expected Behavior
1. KRKN identifies VMs matching specified patterns
2. Executes the configured VM action (stop/restart/pause)
3. Monitors VM status during the action
4. Waits for VM recovery or timeout
5. Reports success/failure based on recovery

## VM Actions
- **stop**: Powers down the VM gracefully or forcefully
- **restart**: Reboots the VM
- **pause**: Pauses VM execution (freezes state)

## Platform Requirements
- OpenShift 4.8+ with Virtualization enabled
- KubeVirt v0.45+ for non-OpenShift environments
- Sufficient compute and storage resources
- Proper network configuration

## Customization
You can customize this scenario by modifying:
- `vm_name_pattern`: Target specific VM naming conventions
- `namespace_pattern`: Target specific namespaces
- `action`: Type of VM operation to perform
- `timeout`: Action timeout duration
- `recovery_time`: Recovery monitoring duration

## Safety Considerations
- Ensure VM backups are current
- Test in non-production environments first
- Monitor VM health during execution
- Have rollback procedures ready
- Consider data persistence requirements

## Monitoring Recommendations
- Monitor VM status and health
- Watch for VM migration events
- Check storage and network connectivity
- Monitor application performance within VMs

## Troubleshooting
- Check OpenShift Virtualization operator status
- Verify VM permissions and RBAC
- Monitor VM logs and events
- Check storage class availability

## Best Practices
- Document VM recovery procedures
- Test different VM configurations
- Monitor resource utilization
- Ensure proper VM sizing

## Related Scenarios
- [Node Failure](../node-failure/)
- [Pod Failure](../pod-failure/)
- [Disk Stress](../disk-stress/)
