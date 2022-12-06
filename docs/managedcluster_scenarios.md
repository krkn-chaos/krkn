### ManagedCluster Scenarios

[ManagedCluster](https://open-cluster-management.io/concepts/managedcluster/) scenarios provide a way to integrate kraken with [Open Cluster Management (OCM)](https://open-cluster-management.io/) and [Red Hat Advanced Cluster Management for Kubernetes (ACM)](https://www.redhat.com/en/technologies/management/advanced-cluster-management).

ManagedCluster scenarios leverage [ManifestWorks](https://open-cluster-management.io/concepts/manifestwork/) to inject faults into the ManagedClusters.

The following ManagedCluster chaos scenarios are supported:

1. **managedcluster_start_scenario**: Scenario to start the ManagedCluster instance.
2. **managedcluster_stop_scenario**: Scenario to stop the ManagedCluster instance.
3. **managedcluster_stop_start_scenario**: Scenario to stop and then start the ManagedCluster instance.
4. **start_klusterlet_scenario**: Scenario to start the klusterlet of the ManagedCluster instance.
5. **stop_klusterlet_scenario**: Scenario to stop the klusterlet of the ManagedCluster instance.
6. **stop_start_klusterlet_scenario**: Scenario to stop and start the klusterlet of the ManagedCluster instance.

ManagedCluster scenarios can be injected by placing the ManagedCluster scenarios config files under `managedcluster_scenarios` option in the Kraken config. Refer to [managedcluster_scenarios_example](https://github.com/redhat-chaos/krkn/blob/main/scenarios/kube/managedcluster_scenarios_example.yml) config file.

```
managedcluster_scenarios:
  - actions:                                                        # ManagedCluster chaos scenarios to be injected
    - managedcluster_stop_start_scenario
    managedcluster_name: cluster1                                   # ManagedCluster on which scenario has to be injected; can set multiple names separated by comma
    # label_selector:                                               # When managedcluster_name is not specified, a ManagedCluster with matching label_selector is selected for ManagedCluster chaos scenario injection
    instance_count: 1                                               # Number of managedcluster to perform action/select that match the label selector
    runs: 1                                                         # Number of times to inject each scenario under actions (will perform on same ManagedCluster each time)
    timeout: 420                                                    # Duration to wait for completion of ManagedCluster scenario injection
                                                                    # For OCM to detect a ManagedCluster as unavailable, have to wait 5*leaseDurationSeconds
                                                                    # (default leaseDurationSeconds = 60 sec)
  - actions:
    - stop_start_klusterlet_scenario
    managedcluster_name: cluster1
    # label_selector:
    instance_count: 1
    runs: 1
    timeout: 60
```
