### Hog Scenarios

Hog Scenarios are designed to push the limits of memory, CPU, or I/O on one or more nodes in your cluster. 
They also serve to evaluate whether your cluster can withstand rogue pods that excessively consume resources 
without any limits.

These scenarios involve deploying one or more workloads in the cluster. Based on the specific configuration, 
these workloads will use a predetermined amount of resources for a specified duration.

#### Common options

| Option  | Type                                                                                                                                                                                                                                                                                                                                                    | Description                                                                                                                                                                                                                                                                                                                           |
|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|`duration`| number                                                                                                                                                                                                                                                                                                                                                  | the duration of the stress test in seconds                                                                                                                                                                                                                                                                                            |
|`workers`| number (Optional)                                                                                                                                                                                                                                                                                                                                       | the number of threads instantiated by stress-ng, if left empty the number of workers will match the number of available cores in the node.                                                                                                                                                                                            |
|`hog-type`| string (Enum)                                                                                                                                                                                                                                                                                                                                           | can be cpu, memory or io.                                                                                                                                                                                                                                                                                                             |
|`image`| string                                                                                                                                                                                                                                                                                                                                                  | the container image of the stress workload                                                                                                                                                                                                                                                                                            |
|`namespace`| string                                                                                                                                                                                                                                                                                                                                                  | the namespace where the stress workload will be deployed                                                                                                                                                                                                                                                                              |
|`node-selector`| string (Optional) | defines the node selector for choosing target nodes. If not specified, one schedulable node in the cluster will be chosen at random. If multiple nodes match the selector, all of them will be subjected to stress. If number-of-nodes is specified, that many nodes will be randomly selected from those identified by the selector. |
|`number-of-nodes`| number (Optional) | restricts the number of selected nodes by the selector|
|`taints`| list (Optional) default [] | list of taints for which tolerations need to created. Example: ["node-role.kubernetes.io/master:NoSchedule"]|



#### `cpu-hog` options

| Option  | Type   |Description|
|---|--------|---|
|`cpu-load-percentage`| number | the amount of cpu that will be consumed by the hog|
|`cpu-method`| string | reflects the cpu load strategy adopted by stress-ng, please refer to the stress-ng documentation for all the available options|




#### `io-hog` options

| Option                | Type   | Description                                                                                                                                                                                                  |
|-----------------------|--------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `io-block-size`       |string| the block size written by the stressor                                                                                                                                                                       |
| `io-write-bytes`      |string| the total amount of data that will be written by the stressor. The size can be specified as % of free space on the file system or in units of Bytes, KBytes, MBytes and GBytes using the suffix b, k, m or g |
| `io-target-pod-folder` |string| the folder where the volume will be mounted in the pod                                                                                                                                                       |
| `io-target-pod-volume`| dictionary | the pod volume definition that will be stressed by the scenario.                                                                                                                                             |

> [!CAUTION]
> Modifying the structure of `io-target-pod-volume` might alter how the hog operates, potentially rendering it ineffective.

#### `memory-hog` options

| Option                | Type   |Description|
|-----------------------|--------|---|
|`memory-vm-bytes`| string | the amount of memory that the scenario will try to hog.The size can be specified as % of free space on the file system or in units of Bytes, KBytes, MBytes and GBytes using the suffix b, k, m or g | 