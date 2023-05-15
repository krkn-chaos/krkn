# Memory Hog
This scenario is based on the arcaflow [arcaflow-plugin-stressng](https://github.com/arcalot/arcaflow-plugin-stressng) plugin. 
The purpose of this scenario is to create Virtual Memory pressure on a particular node of the Kubernetes/OpenShift cluster for a time span.
To enable this plugin add the pointer to the scenario input file `scenarios/arcaflow/memory-hog/input.yaml` as described in the 
Usage section.
This scenario takes a list of objects named `input_list` with the following properties:

- **kubeconfig :** *string* the kubeconfig needed by the deployer to deploy the sysbench plugin in the target cluster
- **namespace :** *string* the namespace where the scenario container will be deployed
**Note:** this parameter will be automatically filled by kraken if the `kubeconfig_path` property is correctly set
- **node_selector :** *key-value map* the node label that will be used as `nodeSelector` by the pod to target a specific cluster node
- **duration :** *string* stop  stress  test  after  N  seconds.  One  can  also specify the units of time in seconds, minutes, hours, days or years with the suffix s, m, h, d or y.
- **vm_bytes :** *string* N bytes per vm process or percentage of memory used (using the % symbol). The size can be expressed in units of Bytes, KBytes, MBytes and GBytes using the suffix b, k, m or g.
- **vm_workers :** *int* Number of VM stressors to be run (0 means 1 stressor per CPU)

To perform several load tests in the same run simultaneously (eg. stress two or more nodes in the same run) add another item
to the `input_list` with the same properties (and eventually different values eg. different node_selectors 
to schedule the pod on different nodes). To reduce (or increase) the parallelism change the value `parallelism` in `workload.yaml` file 