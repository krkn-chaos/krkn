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
