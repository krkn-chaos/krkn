###  Time/Date Skew Scenarios

Using this type of scenario configuration, one is able to change the time and/or date of the system for pods or nodes

Configuration Options:

**action:** skew_time or skew_date

**object_type:** pod or node

**namespace:** namespace of the pods you want to skew, need to be set if setting a specific pod name

**label_selector:** label on the nodes or pods you want to skew

**object_name:** list of the names of pods or nodes you want to skew

Refer to [time_scenarios_example](https://github.com/openshift-scale/kraken/blob/master/scenarios/time_scenarios_example.yml) config file.

```
time_scenarios:
  - action: skew_time
    object_type: pod
    object_name:
      - apiserver-868595fcbb-6qnsc
      - apiserver-868595fcbb-mb9j5
    namespace: openshift-apiserver
  - action: skew_date
    object_type: node
    label_selector: node-role.kubernetes.io/worker
```
