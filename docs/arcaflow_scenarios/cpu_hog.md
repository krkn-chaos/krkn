# CPU Hog
This scenario is based on the arcaflow [arcaflow-plugin-stressng](https://github.com/arcalot/arcaflow-plugin-stressng) plugin. 
The purpose of this scenario is to create cpu pressure on a particular node of the Kubernetes/OpenShift cluster for a time span.
To enable this plugin add the pointer to the scenario input file `scenarios/arcaflow/cpu-hog/input.yaml` as described in the 
Usage section.
This scenario takes the following input parameters:

- **kubeconfig :** *string* the kubeconfig needed by the deployer to deploy the sysbench plugin in the target cluster
**Note:** this parameter will be automatically filled by kraken if the `kubeconfig_path` property is correctly set
- **node_selector :** *key-value map* the node label that will be used as `nodeSelector` by the pod to target a specific cluster node
- **timeout :** *string* the number of seconds to wait before shutting down the benchmark after the defined run time. You can also specify the units of time in seconds, minutes, hours, days or years with the suffix s, m, h, d or y
- **cpu_count :** *int* the number of CPU cores to be used (0 means all)
- **cpu_method :** *string* a fine-grained control of which cpu stressors to use (ackermann, cfloat etc. see [manpage](https://manpages.org/sysbench) for all the cpu_method options)
- **cpu_load_percentage :** *int* the CPU load by percentage