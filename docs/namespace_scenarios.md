###  Delete Namespace Scenarios

Using this type of scenario configuration, one is able to delete specific namespace or namespace matching a certain regex string

Configuration Options:

**action:** default is `delete`

**namespace:** specific namespace or regex style namespace of what you want to delete, gets all namespaces if not specified

**label_selector:** label on the namespace you want to delete

**runs:** number of runs to kill namespaces, based on matching namespace and label specified, default is 1

**sleep:** number of seconds to wait between each iteration/count of killing namespaces. Defaults to 10 seconds if not set

Refer to [namespace_scenarios_example](https://github.com/openshift-scale/kraken/blob/master/scenarios/regex_namespace) config file.

```
scenarios:
- action: delete
  namespace: "^.*$"
  runs: 1
- action: delete
  namespace: "^.*ingress.*$"
  runs: 1
  sleep: 15
```

**NOTE:** Many openshift namespaces have finalizers built that protect the namespace from being fully deleted: see documentation [here](https://kubernetes.io/blog/2021/05/14/using-finalizers-to-control-deletion/)
The namespaces that do have finalizers enabled will be in left in a terminating state but all the pods running on that namespace will get deleted

#### Post Action

In all scenarios we do a post chaos check to wait and verify the specific component

Here there are two options:

1. Pass a custom script in the main config scenario list, that will run before the chaos and verify the output matches post chaos scenario

See [scenarios/post_action_namespace.py](https://github.com/cloud-bulldozer/kraken/tree/master/scenarios/post_action_namespace.py) for an example

```
-   namespace_scenarios:
     - -    scenarios/regex_namespace.yaml
       -    scenarios/post_action_namespace.py
```


2. Allow kraken to wait and check the killed namespaces become 'Active' again. Kraken keeps a list of the specific
namespaces that were killed to verify all that were affected recover properly

```
wait_time: <seconds to wait for namespace to recover>
```
