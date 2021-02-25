### Pod Scenarios
Kraken consumes [Powerfulseal](https://github.com/powerfulseal/powerfulseal) under the hood to run the pod scenarios.
These scenarios are in a simple yaml format that you can manipulate to run your specific tests or use the pre-existing scenarios to see how it works

#### Pod chaos scenarios
The following are the components of Kubernetes/OpenShift for which a basic chaos scenario config exists today.

Component                | Description                                                                                        | Working
------------------------ | ---------------------------------------------------------------------------------------------------| ------------------------- |
[Etcd](https://github.com/cloud-bulldozer/kraken/blob/master/scenarios/etcd.yml)                     | Kills a single/multiple etcd replicas for the specified number of times in a loop                  | :heavy_check_mark:        |
[Kube ApiServer](https://github.com/cloud-bulldozer/kraken/blob/master/scenarios/openshift-kube-apiserver.yml)           | Kills a single/multiple kube-apiserver replicas for the specified number of times in a loop        | :heavy_check_mark:        |
[ApiServer](https://github.com/cloud-bulldozer/kraken/blob/master/scenarios/openshift-apiserver.yml)              | Kills a single/multiple apiserver replicas for the specified number of times in a loop             | :heavy_check_mark:        |
[Prometheus](https://github.com/cloud-bulldozer/kraken/blob/master/scenarios/prometheus.yml)               | Kills a single/multiple prometheus replicas for the specified number of times in a loop            | :heavy_check_mark:        |
[OpenShift System Pods](https://github.com/cloud-bulldozer/kraken/blob/master/scenarios/regex_openshift_pod_kill.yml)    | Kills random pods running in the OpenShift system namespaces                                       | :heavy_check_mark:        |
