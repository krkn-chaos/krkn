### Network chaos
Scenario to introduce network latency, packet loss, and bandwidth restriction in the Node's host network interface. The purpose of this scenario is to observe faults caused by random variations in the network.

##### Sample scenario config
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
    latency: 50ms
    loss: 0.02                                    # percentage
    bandwidth: 100mbit
```

##### Steps
 - Pick the nodes to introduce the network anomaly either from node_name or label_selector.
 - Verify interface list in one of the nodes or use the interface with a default route, as test interface, if no interface is specified by the user.
 - Set traffic shaping config on node's interface using tc and netem.
 - Wait for the duration time.
 - Remove traffic shaping config on node's interface.
 - Remove the job that spawned the pod.
