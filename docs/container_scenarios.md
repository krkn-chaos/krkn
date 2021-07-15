### Container Scenarios
Kraken uses the `oc exec` command to `kill` specific containers in a pod.
This can be based on the pods namespace or labels. If you know the exact object you want to kill, you can also specify the specific container name or pod name in the scenario yaml file.
These scenarios are in a simple yaml format that you can manipulate to run your specific tests or use the pre-existing scenarios to see how it works

####  Example Config
The following are the components of Kubernetes/OpenShift for which a basic chaos scenario config exists today.

```
scenarios:
- name: "<Name of scenario>"
  namespace: "<specific namespace>" # can specify "*" if you want to find in all namespaces
  label_selector: "<label of pod(s)>"
  container_name: "<specific container name>"  # This is optional, can take out and will kill all containers in all pods found under namespace and label
  pod_names:  # This is optional, can take out and will select all pods with given namespace and label
  - <pod_name>
```
