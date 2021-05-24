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
9. **stop_start_helper_node_scenario**: scenario to stop and start the helper node and check service status.

**NOTE**: If the node doesn't recover from the node_crash_scenario injection, reboot the node to get it back to Ready state.

**NOTE**: node_start_scenario, node_stop_scenario, node_stop_start_scenario, node_termination_scenario, node_reboot_scenario and stop_start_kubelet_scenario are supported only on AWS and GCP as of now.

#### AWS

How to set up AWS cli to run node scenarios is defined [here](cloud_setup.md#aws)

#### Baremetal
**NOTE**: Baremetal requires setting the IPMI user and password to power on, off, and reboot nodes, using the config options `bm_user` and `bm_password`.

It currently assumes that all nodes have the same user and password, and that the cluster stores the IPMI address of each node. That is not always the case depending on how the cluster is created.

**NOTE**: Baremetal requires oc (openshift client) be installed on the machine running Kraken.

#### GCP
How to set up GCP cli to run node scenarios is defined [here](cloud_setup.md#gcp)

#### Openstack

How to set up Openstack cli to run node scenarios is defined [here](cloud_setup.md#openstack)

The supported node level chaos scenarios on an OPENSTACK cloud are `node_stop_start_scenario`, `stop_start_kubelet_scenario` and `node_reboot_scenario`.

**NOTE**: For `stop_start_helper_node_scenario`,  visit [here](https://github.com/RedHatOfficial/ocp4-helpernode) to learn more about the helper node and its usage.

To execute the scenario, ensure the value for `ssh_private_key` in the node scenarios config file is set with the correct private key file path for ssh connection to the helper node. Ensure passwordless ssh is configured on the host running Kraken and the helper node to avoid connection errors.


#### Azure

How to set up Azure cli to run node scenarios is defined [here](cloud_setup.md#azure)


**NOTE**: The `node_crash_scenario` and `stop_kubelet_scenario` scenario is supported independent of the cloud platform.

Use 'generic' or do not add the 'cloud_type' key to your scenario if your cluster is not set up using one of the current supported cloud types

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
    cloud_type: azure
  - actions:
    - node_crash_scenario
    node_name:
    label_selector: node-role.kubernetes.io/infra
    instance_kill_count: 1
    timeout: 120
  - actions:
    - stop_start_helper_node_scenario                               # node chaos scenario for helper node
    instance_kill_count: 1
    timeout: 120
    helper_node_ip:                                                 # ip address of the helper node
    service:                                                        # check status of the services on the helper node
      - haproxy
      - dhcpd
      - named
    ssh_private_key: /root/.ssh/id_rsa                              # ssh key to access the helper node
    cloud_type: openstack
```
