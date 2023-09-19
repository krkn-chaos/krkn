## Arcaflow Scenarios
Arcaflow is a workflow engine in development which provides the ability to execute workflow steps in sequence, in parallel, repeatedly, etc. The main difference to competitors such as Netflix Conductor is the ability to run ad-hoc workflows without an infrastructure setup required.

The engine uses containers to execute plugins and runs them either locally in Docker/Podman or remotely on a Kubernetes cluster. The workflow system is strongly typed and allows for generating JSON schema and OpenAPI documents for all data formats involved.

### Available Scenarios
#### Hog scenarios:
- [CPU Hog](arcaflow_scenarios/cpu_hog.md)
- [Memory Hog](arcaflow_scenarios/memory_hog.md)
- [I/O Hog](arcaflow_scenarios/io_hog.md)


### Prequisites
Arcaflow supports three deployment technologies:
- Docker
- Podman
- Kubernetes

#### Docker
In order to run Arcaflow Scenarios with the Docker deployer, be sure that:
- Docker is correctly installed in your Operating System (to find instructions on how to install docker please refer to [Docker Documentation](https://www.docker.com/))
- The Docker daemon is running

#### Podman
The podman deployer is built around the podman CLI and doesn't need necessarily to be run along with the podman daemon.
To run Arcaflow Scenarios in your Operating system be sure that:
- podman is correctly installed in your Operating System (to find instructions on how to install podman refer to [Podman Documentation](https://podman.io/))
- the podman CLI is in your shell PATH

#### Kubernetes
The kubernetes deployer integrates directly the Kubernetes API Client and needs only a valid kubeconfig file and a reachable Kubernetes/OpenShift Cluster.

### Usage

To enable arcaflow scenarios edit the kraken config file, go to the section `kraken -> chaos_scenarios` of the yaml structure
and add a new element to the list named `arcaflow_scenarios` then add the desired scenario
pointing to the `input.yaml` file.
```
kraken:
    ...
    chaos_scenarios:
        - arcaflow_scenarios:
            - scenarios/arcaflow/cpu-hog/input.yaml
```

#### input.yaml
The implemented scenarios can be found in *scenarios/arcaflow/<scenario_name>* folder.
The entrypoint of each scenario is the *input.yaml* file. 
In this file there are all the options to set up the scenario accordingly to the desired target 
### config.yaml
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
### workflow.yaml
This file contains the steps that will be executed to perform the scenario against the target.
Each step is represented by a container that will be executed from the deployer and its options.
Note that we provide the scenarios as a template, but they can be manipulated to define more complex workflows.
To have more details regarding the arcaflow workflows architecture and syntax it is suggested to refer to the [Arcaflow Documentation](https://arcalot.io/arcaflow/).

This edit is no longer in quay image
Working on fix in ticket: https://issues.redhat.com/browse/CHAOS-494
This will effect all versions 4.12 and higher of OpenShift