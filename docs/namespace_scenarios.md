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
