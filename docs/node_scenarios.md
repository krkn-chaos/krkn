### Node Scenarios

The following node chaos scenarios are supported:

1. **node_start_scenario**: Scenario to stop the node instance.
2. **node_stop_scenario**: Scenario to stop the node instance.
3. **node_stop_start_scenario**: Scenario to stop and then start the node instance. Not supported on VMware.
4. **node_termination_scenario**: Scenario to terminate the node instance.
5. **node_reboot_scenario**: Scenario to reboot the node instance.
6. **stop_kubelet_scenario**: Scenario to stop the kubelet of the node instance.
7. **stop_start_kubelet_scenario**: Scenario to stop and start the kubelet of the node instance.
8. **restart_kubelet_scenario**: Scenario to restart the kubelet of the node instance.
9. **node_crash_scenario**: Scenario to crash the node instance.
10. **stop_start_helper_node_scenario**: Scenario to stop and start the helper node and check service status.


**NOTE**: If the node does not recover from the node_crash_scenario injection, reboot the node to get it back to Ready state.

**NOTE**: node_start_scenario, node_stop_scenario, node_stop_start_scenario, node_termination_scenario
, node_reboot_scenario and stop_start_kubelet_scenario are supported on AWS, Azure, OpenStack, BareMetal, GCP
, VMware and Alibaba.


#### AWS

Cloud setup instructions can be found [here](cloud_setup.md#aws). Sample scenario config can be found [here](https://github.com/krkn-chaos/krkn/blob/main/scenarios/openshift/aws_node_scenarios.yml).



#### Baremetal

Sample scenario config can be found [here](https://github.com/krkn-chaos/krkn/blob/main/scenarios/openshift/baremetal_node_scenarios.yml).

**NOTE**: Baremetal requires setting the IPMI user and password to power on, off, and reboot nodes, using the config options `bm_user` and `bm_password`. It can either be set in the root of the entry in the scenarios config, or it can be set per machine.

If no per-machine addresses are specified, kraken attempts to use the BMC value in the BareMetalHost object. To list them, you can do 'oc get bmh -o wide --all-namespaces'. If the BMC values are blank, you must specify them per-machine using the config option 'bmc_addr' as specified below.

For per-machine settings, add a "bmc_info" section to the entry in the scenarios config. Inside there, add a configuration section using the node name. In that, add per-machine settings. Valid settings are 'bmc_user', 'bmc_password', and 'bmc_addr'.
See the example node scenario or the example below.

**NOTE**: Baremetal requires oc (openshift client) be installed on the machine running Kraken.

**NOTE**: Baremetal machines are fragile. Some node actions can occasionally corrupt the filesystem if it does not shut down properly, and sometimes the kubelet does not start properly.



#### Docker

The Docker provider can be used to run node scenarios against kind clusters.

[kind](https://kind.sigs.k8s.io/) is a tool for running local Kubernetes clusters using Docker container "nodes".

kind was primarily designed for testing Kubernetes itself, but may be used for local development or CI.



#### GCP
Cloud setup instructions can be found [here](cloud_setup.md#gcp). Sample scenario config can be found [here](https://github.com/krkn-chaos/krkn/blob/main/scenarios/openshift/gcp_node_scenarios.yml).


#### Openstack

How to set up Openstack cli to run node scenarios is defined [here](cloud_setup.md#openstack).

The supported node level chaos scenarios on an OPENSTACK cloud are `node_stop_start_scenario`, `stop_start_kubelet_scenario` and `node_reboot_scenario`.

**NOTE**: For `stop_start_helper_node_scenario`,  visit [here](https://github.com/redhat-cop/ocp4-helpernode) to learn more about the helper node and its usage.

To execute the scenario, ensure the value for `ssh_private_key` in the node scenarios config file is set with the correct private key file path for ssh connection to the helper node. Ensure passwordless ssh is configured on the host running Kraken and the helper node to avoid connection errors.



#### Azure

Cloud setup instructions can be found [here](cloud_setup.md#azure). Sample scenario config can be found [here](https://github.com/krkn-chaos/krkn/blob/main/scenarios/openshift/azure_node_scenarios.yml).



#### Alibaba

How to set up Alibaba cli to run node scenarios is defined [here](cloud_setup.md#alibaba).

**NOTE**: There is no "terminating" idea in Alibaba, so any scenario with terminating will "release" the node
. Releasing a node is 2 steps, stopping the node and then releasing it.



#### VMware
How to set up VMware vSphere to run node scenarios is defined [here](cloud_setup.md#vmware)

This cloud type uses a different configuration style, see actions below and [example config file](../scenarios/openshift/vmware_node_scenarios.yml)

- vmware-node-terminate
- vmware-node-reboot
- vmware-node-stop
- vmware-node-start



#### IBMCloud
How to set up IBMCloud to run node scenarios is defined [here](cloud_setup.md#ibmcloud)

This cloud type uses a different configuration style, see actions below and [example config file](../scenarios/openshift/ibmcloud_node_scenarios.yml)

- ibmcloud-node-terminate
- ibmcloud-node-reboot
- ibmcloud-node-stop
- ibmcloud-node-start



#### General

**NOTE**: The `node_crash_scenario` and `stop_kubelet_scenario` scenario is supported independent of the cloud platform.

Use 'generic' or do not add the 'cloud_type' key to your scenario if your cluster is not set up using one of the current supported cloud types.
