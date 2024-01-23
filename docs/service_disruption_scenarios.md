###  Service Disruption Scenarios (Previously Delete Namespace Scenario)

Using this type of scenario configuration one is able to delete crucial objects in a specific namespace, or a namespace matching a certain regex string.

Configuration Options:

**namespace:** Specific namespace or regex style namespace of what you want to delete. Gets all namespaces if not specified; set to "" if you want to use the label_selector field.

Set to '^.*$' and label_selector to "" to randomly select any namespace in your cluster.

**label_selector:** Label on the namespace you want to delete. Set to "" if you are using the namespace variable.

**delete_count:** Number of namespaces to kill in each run. Based on matching namespace and label specified, default is 1.

**runs:** Number of runs/iterations to kill namespaces, default is 1.

**sleep:** Number of seconds to wait between each iteration/count of killing namespaces. Defaults to 10 seconds if not set

Refer to [namespace_scenarios_example](https://github.com/krkn-chaos/krkn/blob/main/scenarios/regex_namespace.yaml) config file.

```
scenarios:
- namespace: "^.*$"
  runs: 1
- namespace: "^.*ingress.*$"
  runs: 1
  sleep: 15
```


### Steps

This scenario will select a namespace (or multiple) dependent on the configuration and will kill all of the below object types in that namespace and will wait for them to be Running in the post action 
1. Services 
2. Daemonsets
3. Statefulsets
4. Replicasets
5. Deployments 


#### Post Action

We do a post chaos check to wait and verify the specific objects in each namespace are Ready

Here there are two options:

1. Pass a custom script in the main config scenario list that will run before the chaos and verify the output matches post chaos scenario.

See [scenarios/post_action_namespace.py](https://github.com/cloud-bulldozer/kraken/tree/master/scenarios/post_action_namespace.py) for an example

```
-   namespace_scenarios:
     - -    scenarios/regex_namespace.yaml
       -    scenarios/post_action_namespace.py
```


1. Allow kraken to wait and check all killed objects in the namespaces become 'Running' again. Kraken keeps a list of the specific
objects in namespaces that were killed to verify all that were affected recover properly.

```
wait_time: <seconds to wait for namespace to recover>
```
