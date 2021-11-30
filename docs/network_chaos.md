### Network chaos
Scenario to introduce network latency, packet loss, bandwidth restriction in the Node's hostnework interface. The purpose of this scenario is to observe faults caused by random variations in the network.

##### Sample scenario config
```
network_chaos:                                    # Scenario to create an outage by simulating random variations in the network.
  duration: 300                                   # in seconds - during with network chaos will be applied.
  node_name:                                      # comma separated node names on which scenario has to be injected.
  label_selector: node-role.kubernetes.io/master  # when node_name is not specified, a node with matching label_selector is selected for running the scenario.
  instance_count: 1                               # Number of nodes to execute network chaos in.
  interfaces:                                     # List of interface on which to apply the network restriction.
  - "ens5"                                        # Interface name would be the Kernel host network interface name.
  execution: serial|parallel                      # Execute each of the egress option as a single scenario(parallel) or as separate scenario(serial).
  egress:
    latency: 50ms
    loss: 0.02                                    # percentage
    bandwidth: 100mbit
```

##### Steps
 - Pick the nodes to introduce the network anomly either from node_name or label_selector.
 - Verify interface list in one of the node or use the interface with default route, as test interface, if no interface is specified by the user.
 - Set traffic shaping config on node's interface using tc and netem.
 - Wait for the duration time.
 - Remove traffic shaping config on node's interface.
 - Remove the job that spawned the pod.
