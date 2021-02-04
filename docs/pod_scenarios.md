### Pod Scenarios
Kraken consumes [Powerfulseal](https://github.com/powerfulseal/powerfulseal) under the hood to run the pod scenarios. 


#### Pod chaos scenarios
Following are the components of Kubernetes/OpenShift for which a basic chaos scenario config exists today. Adding a new pod based scenario is as simple as adding a new config under scenarios directory and defining it in the config.
For example, for adding a pod level scenario for a custom application, refer to the sample scenario provided in the scenarios directory (scenarios/customapp_pod.yaml).

Component                | Description                                                                                        | Working
------------------------ | ---------------------------------------------------------------------------------------------------| ------------------------- |
Etcd                     | Kills a single/multiple etcd replicas for the specified number of times in a loop                  | :heavy_check_mark:        |
Kube ApiServer           | Kills a single/multiple kube-apiserver replicas for the specified number of times in a loop        | :heavy_check_mark:        |
ApiServer                | Kills a single/multiple apiserver replicas for the specified number of times in a loop             | :heavy_check_mark:        |
Prometheus               | Kills a single/multiple prometheus replicas for the specified number of times in a loop            | :heavy_check_mark:        |
OpenShift System Pods    | kills random pods running in the OpenShift system namespaces                                       | :heavy_check_mark:        |

**NOTE**: [Writing policies](https://powerfulseal.github.io/powerfulseal/policies) can be referred for more information on how to write new scenarios.
