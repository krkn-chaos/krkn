# KubeVirt VM Outage Scenario

This scenario enables the simulation of VM-level disruptions in clusters where KubeVirt or OpenShift Containerized Network Virtualization (CNV) is installed. It allows users to delete a Virtual Machine Instance (VMI) to simulate a VM crash and test recovery capabilities.

## Purpose

The `kubevirt_vm_outage` scenario deletes a specific KubeVirt Virtual Machine Instance (VMI) to simulate a VM crash or outage. This helps users:

- Test the resilience of applications running inside VMs
- Verify that VM monitoring and recovery mechanisms work as expected
- Validate high availability configurations for VM workloads
- Understand the impact of sudden VM failures on workloads and the overall system

## Prerequisites

Before using this scenario, ensure the following:

1. KubeVirt or OpenShift CNV is installed in your cluster
2. The target VMI exists and is running in the specified namespace
3. You have the kubevirt Python client installed (included in krkn requirements.txt)
4. Your cluster credentials have sufficient permissions to delete and create VMIs

## Parameters

The scenario supports the following parameters:

| Parameter | Description | Required | Default |
|-----------|-------------|----------|---------|
| vm_name | The name of the VMI to delete | Yes | N/A |
| namespace | The namespace where the VMI is located | No | "default" |
| duration | How long to wait (in seconds) before attempting recovery | No | 60 |

## Expected Behavior

When executed, the scenario will:

1. Validate that KubeVirt is installed and the target VMI exists
2. Save the initial state of the VMI
3. Delete the VMI using the KubeVirt API
4. Wait for the specified duration
5. Attempt to recover the VMI:
   - If the VMI is managed by a VirtualMachine resource with runStrategy: Always, it will automatically recover
   - If automatic recovery doesn't occur, the plugin will manually recreate the VMI using the saved state
6. Validate that the VMI is running again

> ⚠️ **Note**: If the VM is managed by a VirtualMachine resource with `runStrategy: Always`, KubeVirt will automatically try to recreate the VMI after deletion. In this case, the scenario will wait for this automatic recovery to complete.

## Sample Configuration

Here's an example configuration for using the `kubevirt_vm_outage` scenario:

```yaml
scenarios:
  - name: "kubevirt outage test"
    scenario: kubevirt_vm_outage
    parameters:
      vm_name: my-vm
      namespace: kubevirt
      duration: 60
```

For multiple VMs in different namespaces:

```yaml
scenarios:
  - name: "kubevirt outage test - app VM"
    scenario: kubevirt_vm_outage
    parameters:
      vm_name: app-vm
      namespace: application
      duration: 120
  
  - name: "kubevirt outage test - database VM"
    scenario: kubevirt_vm_outage
    parameters:
      vm_name: db-vm
      namespace: database
      duration: 180
```

## Recovery Strategies

The plugin implements two recovery strategies:

1. **Automated Recovery**: If the VM is managed by a VirtualMachine resource with `runStrategy: Always`, the plugin will wait for KubeVirt's controller to automatically recreate the VMI.

2. **Manual Recovery**: If automatic recovery doesn't occur within the timeout period, the plugin will attempt to manually recreate the VMI using the saved state from before the deletion.

## Limitations

- The scenario currently supports deleting a single VMI at a time
- If VM spec changes during the outage window, the manual recovery may not reflect those changes
- The scenario doesn't simulate partial VM failures (e.g., VM freezing) - only complete VM outage

## Troubleshooting

If the scenario fails, check the following:

1. Ensure KubeVirt/CNV is properly installed in your cluster
2. Verify that the target VMI exists and is running
3. Check that your credentials have sufficient permissions to delete and create VMIs
4. Examine the logs for specific error messages
