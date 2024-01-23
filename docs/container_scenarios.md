### Container Scenarios
Kraken uses the `oc exec` command to `kill` specific containers in a pod.
This can be based on the pods namespace or labels. If you know the exact object you want to kill, you can also specify the specific container name or pod name in the scenario yaml file.
These scenarios are in a simple yaml format that you can manipulate to run your specific tests or use the pre-existing scenarios to see how it works.

####  Example Config
The following are the components of Kubernetes for which a basic chaos scenario config exists today.

```
scenarios:
- name: "<name of scenario>"
  namespace: "<specific namespace>" # can specify "*" if you want to find in all namespaces
  label_selector: "<label of pod(s)>"
  container_name: "<specific container name>"  # This is optional, can take out and will kill all containers in all pods found under namespace and label
  pod_names:  # This is optional, can take out and will select all pods with given namespace and label
  - <pod_name>
  count: <number of containers to disrupt, default=1>
  action: <kill signal to run. For example 1 ( hang up ) or 9. Default is set to 1>
  expected_recovery_time: <number of seconds to wait for container to be running again> (defaults to 120seconds)
```

#### Post Action
In all scenarios we do a post chaos check to wait and verify the specific component.

Here there are two options:
1. Pass a custom script in the main config scenario list that will run before the chaos and verify the output matches post chaos scenario.

See [scenarios/post_action_etcd_container.py](https://github.com/krkn-chaos/krkn/blob/main/scenarios/post_action_etcd_container.py) for an example.
```
-   container_scenarios:                                 # List of chaos pod scenarios to load.
            - -    scenarios/container_etcd.yml
              -    scenarios/post_action_etcd_container.py
```

2. Allow kraken to wait and check the killed containers until they become ready again. Kraken keeps a list of the specific
containers that were killed as well as the namespaces and pods to verify all containers that were affected recover properly.

```
expected_recovery_time: <seconds to wait for container to recover>
```
