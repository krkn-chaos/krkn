### Network chaos
Scenario to introduce network latency, packet loss, and bandwidth restriction in the Node's host network interface. The purpose of this scenario is to observe faults caused by random variations in the network.

##### Sample scenario config for egress traffic shaping
```
network_chaos:                                    # Scenario to create an outage by simulating random variations in the network.
  duration: 300                                   # In seconds - duration network chaos will be applied.
  node_name:                                      # Comma separated node names on which scenario has to be injected.
  label_selector: node-role.kubernetes.io/master  # When node_name is not specified, a node with matching label_selector is selected for running the scenario.
  instance_count: 1                               # Number of nodes in which to execute network chaos.
  interfaces:                                     # List of interface on which to apply the network restriction.
  - "ens5"                                        # Interface name would be the Kernel host network interface name.
  execution: serial|parallel                      # Execute each of the egress options as a single scenario(parallel) or as separate scenario(serial).
  egress:
    latency: 500ms
    loss: 50%                                    # percentage
    bandwidth: 10mbit
```

##### Sample scenario config for ingress traffic shaping (using a plugin)
'''
- id: network_chaos
  config:
    node_interface_name:                            # Dictionary with key as node name(s) and value as a list of its interfaces to test
      ip-10-0-128-153.us-west-2.compute.internal:
        - ens5
        - genev_sys_6081
    label_selector: node-role.kubernetes.io/master  # When node_interface_name is not specified, nodes with matching label_selector is selected for node chaos scenario injection
    instance_count: 1                               # Number of nodes to perform action/select that match the label selector
    kubeconfig_path: ~/.kube/config                 # Path to kubernetes config file. If not specified, it defaults to ~/.kube/config
    execution_type: parallel                        # Execute each of the ingress options as a single scenario(parallel) or as separate scenario(serial).
    network_params:
        latency: 500ms
        loss: '50%'
        bandwidth: 10mbit
    wait_duration: 120
    test_duration: 60
  '''

  Note: For ingress traffic shaping, ensure that your node doesn't have any [IFB](https://wiki.linuxfoundation.org/networking/ifb) interfaces already present. The scenario relies on creating IFBs to do the shaping, and they are deleted at the end of the scenario.


##### Steps
 - Pick the nodes to introduce the network anomaly either from node_name or label_selector.
 - Verify interface list in one of the nodes or use the interface with a default route, as test interface, if no interface is specified by the user.
 - Set traffic shaping config on node's interface using tc and netem.
 - Wait for the duration time.
 - Remove traffic shaping config on node's interface.
 - Remove the job that spawned the pod.
