# I/O Hog
This scenario is based on the arcaflow [arcaflow-plugin-stressng](https://github.com/arcalot/arcaflow-plugin-stressng) plugin. 
The purpose of this scenario is to create disk pressure on a particular node of the Kubernetes/OpenShift cluster for a time span.
The scenario allows to attach a node path to the pod as a `hostPath` volume.
To enable this plugin add the pointer to the scenario input file `scenarios/arcaflow/io-hog/input.yaml` as described in the 
Usage section.
This scenario takes the following input parameters:

- **kubeconfig :** *string* the kubeconfig needed by the deployer to deploy the sysbench plugin in the target cluster
**Note:** this parameter will be automatically filled by kraken if the `kubeconfig_path` property is correctly set
- **node_selector :** *key-value map* the node label that will be used as `nodeSelector` by the pod to target a specific cluster node
- **duration :** *string* stop  stress  test  after  N  seconds.  One  can  also specify the units of time in seconds, minutes, hours, days or years with the suffix s, m, h, d or y.
- **target_pod_folder :** *string* the path in the pod where the volume is mounted
- **target_pod_volume :** *object* the `hostPath` volume definition in the [Kubernetes/OpenShift](https://docs.openshift.com/container-platform/3.11/install_config/persistent_storage/using_hostpath.html) format, that will be attached to the pod as a volume
- **io_write_bytes :** *string* writes N bytes for each hdd process. The size can be expressed as % of free space on the file system or in units of Bytes, KBytes, MBytes and GBytes using the suffix b, k, m or g
- **io_block_size :** *string* size of each write in bytes. Size can be from 1 byte to 4m.