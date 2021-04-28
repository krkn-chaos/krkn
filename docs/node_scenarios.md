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

**NOTE**: For clusters with AWS make sure [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) is installed and properly [configured](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html) using an AWS account

#### GCP
**NOTE**: For clusters with GCP make sure [GCP CLI](https://cloud.google.com/sdk/docs/install#linux) is installed.

A google service account is required to give proper authentication to GCP for node actions. See [here](https://cloud.google.com/docs/authentication/getting-started) for how to create a service account.

**NOTE**: A user with 'resourcemanager.projects.setIamPolicy' permission is required to grant project-level permissions to the service account.

After creating the service account you'll need to enable the account using the following: ```export GOOGLE_APPLICATION_CREDENTIALS="<serviceaccount.json>"```

#### OPENSTACK

**NOTE**: For clusters with OPENSTACK Cloud, ensure to create and source the [OPENSTACK RC file](https://docs.openstack.org/newton/user-guide/common/cli-set-environment-variables-using-openstack-rc.html) to set the OPENSTACK environment variables from the server where Kraken runs.

The supported node level chaos scenarios on an OPENSTACK cloud are `node_stop_start_scenario`, `stop_start_kubelet_scenario` and `node_reboot_scenario`.

**NOTE**: For `stop_start_helper_node_scenario`,  visit [here](https://github.com/RedHatOfficial/ocp4-helpernode) to learn more about the helper node and its usage.

To execute the scenario, ensure the value for `ssh_private_key` in the node scenarios config file is set with the correct private key file path for ssh connection to the helper node. Ensure passwordless ssh is configured on the host running Kraken and the helper node to avoid connection errors.

#### Azure

**NOTE**: For Azure node killing scenarios, make sure [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli?view=azure-cli-latest) is installed

You will also need to create a service principal and give it the correct access, see [here](https://docs.openshift.com/container-platform/4.5/installing/installing_azure/installing-azure-account.html) for creating the service principal and setting the proper permissions

To properly run the service principal requires “Azure Active Directory Graph/Application.ReadWrite.OwnedBy” api permission granted and “User Access Administrator”

Before running you'll need to set the following:
1. Login using ```az login```

2. ```export AZURE_TENANT_ID=<tenant_id>```

3. ```export AZURE_CLIENT_SECRET=<client secret>```

4. ```export AZURE_CLIENT_ID=<client id>```


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
