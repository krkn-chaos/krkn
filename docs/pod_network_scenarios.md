## Pod network Scenarios

### Pod outage
Scenario to block the traffic ( Ingress/Egress ) of a pod matching the labels for the specified duration of time to understand the behavior of the service/other services which depend on it during downtime. This helps with planning the requirements accordingly, be it improving the timeouts or tweaking the alerts etc.
With the current network policies, it is not possible to explicitly block ports which are enabled by allowed network policy rule. This chaos scenario addresses this issue by using OVS flow rules to block ports related to the pod. It supports OpenShiftSDN and OVNKubernetes based networks.

##### Sample scenario config (using a plugin)
```
- id: pod_network_outage
  config:
    namespace: openshift-console   # Required - Namespace of the pod to which filter need to be applied
    direction:                     # Optioinal - List of directions to apply filters
        - ingress                  # Blocks ingress traffic, Default both egress and ingress
    ingress_ports:                 # Optional - List of ports to block traffic on
        - 8443                     # Blocks 8443, Default [], i.e. all ports.
    label_selector: 'component=ui' # Blocks access to openshift console
```
### Pod Network shaping
Scenario to introduce network latency, packet loss, and bandwidth restriction in the Pod's network interface. The purpose of this scenario is to observe faults caused by random variations in the network.

##### Sample scenario config for egress traffic shaping (using plugin)
```
- id: pod_egress_shaping
  config:
    namespace: openshift-console   # Required - Namespace of the pod to which filter need to be applied.
    label_selector: 'component=ui' # Applies traffic shaping to access openshift console.
    network_params:
        latency: 500ms             # Add 500ms latency to egress traffic from the pod.
```
##### Sample scenario config for ingress traffic shaping (using plugin)
```
- id: pod_ingress_shaping
  config:
    namespace: openshift-console   # Required - Namespace of the pod to which filter need to be applied.
    label_selector: 'component=ui' # Applies traffic shaping to access openshift console.
    network_params:
        latency: 500ms             # Add 500ms latency to egress traffic from the pod.
```

##### Steps
 - Pick the pods to introduce the network anomaly either from label_selector or pod_name.
 - Identify the pod interface name on the node.
 - Set traffic shaping config on pod's interface using tc and netem.
 - Wait for the duration time.
 - Remove traffic shaping config on pod's interface.
 - Remove the job that spawned the pod.
