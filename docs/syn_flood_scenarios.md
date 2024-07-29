### SYN Flood Scenarios

This scenario generates a substantial amount of TCP traffic directed at one or more Kubernetes services within 
the cluster to test the server's resiliency under extreme traffic conditions. 
It can also target hosts outside the cluster by specifying a reachable IP address or hostname. 
This scenario leverages the distributed nature of Kubernetes clusters to instantiate multiple instances 
of the same pod against a single host, significantly increasing the effectiveness of the attack. 
The configuration also allows for the specification of multiple node selectors, enabling Kubernetes to schedule 
the attacker pods on a user-defined subset of nodes to make the test more realistic.

 ```yaml
packet-size: 120 # hping3 packet size
window-size: 64 # hping 3 TCP window size
duration: 10 # chaos scenario duration
namespace: default # namespace where the target service(s) are deployed
target-service: target-svc # target service name (if set target-service-label must be empty)
target-port: 80 # target service TCP port
target-service-label : "" # target service label, can be used to target multiple target at the same time
                          # if they have the same label set (if set target-service must be empty)
number-of-pods: 2 # number of attacker pod instantiated per each target
image: quay.io/krkn-chaos/krkn-syn-flood # syn flood attacker container image
attacker-nodes: # this will set the node affinity to schedule the attacker node. Per each node label selector
                # can be specified multiple values in this way the kube scheduler will schedule the attacker pods
                # in the best way possible based on the provided labels. Multiple labels can be specified
  kubernetes.io/hostname:
    - host_1
    - host_2
  kubernetes.io/os:
    - linux

 ```

The attacker container source code is available [here](https://github.com/krkn-chaos/krkn-syn-flood).