# Memory Hog
This scenario is based on the arcaflow [arcaflow-plugin-stressng](https://github.com/arcalot/arcaflow-plugin-stressng) plugin. 
The purpose of this scenario is to create Virtual Memory pressure on a particular node of the Kubernetes/OpenShift cluster for a time span.
To enable this plugin add the pointer to the scenario input file `scenarios/arcaflow/memory-hog/input.yaml` as described in the 
Usage section.
This scenario takes the following input parameters:

- **kubeconfig :** *string* the kubeconfig needed by the deployer to deploy the sysbench plugin in the target cluster
**Note:** this parameter will be automatically filled by kraken if the `kubeconfig_path` property is correctly set
- **node_selector :** *key-value map* the node label that will be used as `nodeSelector` by the pod to target a specific cluster node
- **timeout :** *string* the number of seconds to wait before shutting down the benchmark after the defined run time. You can also specify the units of time in seconds, minutes, hours, days or years with the suffix s, m, h, d or y
- **vm_bytes :** *string* N bytes per vm process. The size can be expressed in units of Bytes, KBytes, MBytes and GBytes using the suffix b, k, m or g.
- **vm_workers :** *int* Number of VM stressors to be run (0 means 1 stressor per CPU)