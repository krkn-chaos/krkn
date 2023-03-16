### Arcaflow Scenarios
Arcaflow is a workflow engine in development which provides the ability to execute workflow steps in sequence, in parallel, repeatedly, etc. The main difference to competitors such as Netflix Conductor is the ability to run ad-hoc workflows without an infrastructure setup required.

The engine uses containers to execute plugins and runs them either locally in Docker/Podman or remotely on a Kubernetes cluster. The workflow system is strongly typed and allows for generating JSON schema and OpenAPI documents for all data formats involved.
#### Prequisites
Arcaflow supports three deployment technologies:
- Docker
- Podman
- Kubernetes

##### Docker
In order to run Arcaflow Scenarios with the Docker deployer, be sure that:
- Docker is correctly installed in your Operating System (to find instructions on how to install docker please refer to [Docker Documentation](https://www.docker.com/))
- The Docker daemon is running

##### Podman
The podman deployer is built around the podman CLI and doesn't need necessarily to be run along with the podman daemon.
To run Arcaflow Scenarios in your Operating system be sure that:
- podman is correctly installed in your Operating System (to find instructions on how to install podman refer to [Podman Documentation](https://podman.io/))
- the podman CLI is in your shell PATH

##### Kubernetes
The kubernetes deployer integrates directly the Kubernetes API Client and needs only a valid kubeconfig file and a reachable Kubernetes/OpenShift Cluster.

#### Usage

To enable arcaflow scenarios edit the kraken config file, go to the section `kraken -> chaos_scenarios` of the yaml structure
and add a new element to the list named `arcaflow_scenarios` then add the desired scenario
pointing to the `input.yaml` file.
```
kraken:
    ...
    chaos_scenarios:
        - arcaflow_scenarios:
            - scenarios/arcaflow/sysbench-cpu-hog/input.yaml
```

##### input.yaml
The implemented scenarios can be found in *scenarios/arcaflow/<scenario_name>* folder.
The entrypoint of each scenario is the *input.yaml* file. 
In this file there are all the options to set up the scenario accordingly to the desired target 
#### config.yaml
The arcaflow config file. Here you can set the arcaflow deployer and the arcaflow log level.
The supported deployers are:
- Docker
- Podman (podman daemon not needed, suggested option)
- Kubernetes

The supported log levels are:
- debug
- info
- warning
- error
#### workflow.yaml
This file contains the steps that will be executed to perform the scenario against the target.
Each step is represented by a container that will be executed from the deployer and its options.
Note that we provide the scenarios as a template, but they can be manipulated to define more complex workflows.
To have more details regarding the arcaflow workflows architecture and syntax it is suggested to refer to the [Arcaflow Documentation](https://arcalot.io/arcaflow/).

#### Scenarios
##### sysbench-cpu-hog
This scenario is based on the arcaflow [sysbench](https://github.com/akopytov/sysbench) plugin. 
The purpose of this scenario is to create cpu pressure on a particular node of the Kubernetes/OpenShift cluster for a time span.
To enable this plugin add the pointer to the scenario input file `scenarios/arcaflow/sysbench-cpu-hog/input.yaml` as described in the 
Usage section.
This scenario takes the following input parameters:

- **kubeconfig :** *string* the kubeconfig needed by the deployer to deploy the sysbench plugin in the target cluster
**Note:** this parameter will be automatically filled by kraken if the `kubeconfig_path` property is correctly set
- **node_selector :**  *key-value map* the node label that will be used as `nodeSelector` by the pod to target a specific cluster node
- **sysbench_cpumaxprime :** *int* the highest prime number during the test. Higher this value is, higher will be the time to find all the prime numbers
- **sysbench_events :** *int* the maximum number of events that will be performed by sysbench, 0 removes the limit
- **sysbench_runtime :** *int* number of seconds the test will be run
- **sysbench_forced_shutdown_time :** *int* the number of seconds to wait before shutting down the benchmark after the defined run time
- **sysbench_threads :** *int* the number of threads on which the test will run

##### kill-pod
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

###### only `name_pattern` active:
```
label_selector: ''
name_pattern: '$my-pattern-.*'
```
###### only `label_selector` active:
```
label_selector: my_selector
name_pattern: '.*' 
```
###### both active (pods will be first filtered by `node_selector` and then by `name_pattern`):
```
label_selector: my_selector
name_pattern: '$my-pattern-.*'
```