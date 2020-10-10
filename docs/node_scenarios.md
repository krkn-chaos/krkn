### Node Scenarios

Following node chaos scenarios are supported:

1. **node_start_scenario**: scenario to stop the node instance.
2. **node_stop_scenario**: scenario to stop the node instance.
3. **node_stop_start_scenario**: scenario to stop and then start the node instance.
4. **node_termination_scenario**: scenario to terminate the node instance.
5. **node_reboot_scenario**: scenario to reboot the node instance.
6. **stop_kubelet_scenario**: scenario to stop the kubelet of the node instance.
7. **stop_start_kubelet_scenario**: scenario to stop and start the kubelet of the node instance.
8. **node_crash_scenario**: scenario to crash the node instance.

**NOTE**: If the node doesn't recover from the node_crash_scenario injection, reboot the node to get it back to Ready state.

**NOTE**: node_start_scenario, node_stop_scenario, node_stop_start_scenario, node_termination_scenario, node_reboot_scenario and stop_start_kubelet_scenario are supported only on AWS as of now.

**NOTE**: AWS is the only cloud platform supported as of today but we are looking into adding more. Make sure [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) is installed.

**NOTE**: The `stop_start_kubelet_scenario` and `node_crash_scenario` scenarios are supported as they are independent of the cloud platform.


Node scenarios can be injected by placing the node scenarios config files under node_scenarios option in the kraken config. Refer to [node_scenarios_example](https://github.com/openshift-scale/kraken/blob/master/scenarios/node_scenarios_example.yml) config file.

```
node_scenarios:
  - actions:                                                        # node chaos scenarios to be injected
    - node_stop_start_scenario
    - stop_start_kubelet_scenario
    - node_crash_scenario
    node_name:                                                      # node on which scenario has to be injected
    label_selector: node-role.kubernetes.io/worker                  # when node_name is not specified, a node with matching label_selector is selected for node chaos scenario injection
    instance_kill_count: 1                                          # number of times to inject each scenario under actions
    timeout: 120                                                    # duration to wait for completion of node scenario injection
    cloud_type: aws                                                 # cloud type on which Kubernetes/OpenShift runs
  - actions:
    - node_reboot_scenario
    node_name:
    label_selector: node-role.kubernetes.io/infra
    instance_kill_count: 1
    timeout: 120
    cloud_type: aws
```
