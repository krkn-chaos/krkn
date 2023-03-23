# Kill Pod
This scenario is based on the arcaflow [kill-pod](https://github.com/redhat-chaos/arcaflow-plugin-kill-pod) plugin.
The purpose of this scenario is to kill one or more pods in one or more namespaces matching pod name and namespace regular expressions.
To enable this plugin add the pointer to the scenario input file `scenarios/arcaflow/kill-pod/input.yaml` as described in the Usage section
This scenario takes the following input parameters:

- **kubeconfig :** *string* the kubeconfig needed by the deployer to deploy the sysbench plugin in the target cluster
- **name_pattern :** *string* regular expression representing the name of the pod(s) that must be targeted
- **label_selector :** *string* pod label selector of the pod(s) that must be targeted.
- **namespace_pattern :** *string* regular expression representing the namespace(s) that contains the pod(s) that must be targeted
- **kill :** *int* the number of pods to kill. Note that if this value is greater than the number of pods filtered by the name_pattern and namespace_pattern regular expression the scenario will fail.
- **backoff :** *int* how many seconds to wait between checks for the target pod status
- **timeout :** *int* timeout to wait for the target pod(s) to be removed in seconds

*Note:* `name_pattern` and `label_selector` can be used separately or in conjunction depending on the user needs:

## only `name_pattern` active:
```
label_selector: ''
name_pattern: '$my-pattern-.*'
```
## only `label_selector` active:
```
label_selector: my_selector
name_pattern: '.*' 
```
## both active (pods will be first filtered by `node_selector` and then by `name_pattern`):
```
label_selector: my_selector
name_pattern: '$my-pattern-.*'

```