# OpenShift Shenanigans

## Workflow Description

Given a target OpenShift cluster, this workflow executes a 
[kube-burner plugin](https://github.com/redhat-performance/arcaflow-plugin-kube-burner) 
workflow to place a load on the cluster, repeatedly removes a targeted pod at a given time frequency with the [kill-pod plugin](https://github.com/krkn-chaos/arcaflow-plugin-kill-pod),
and runs a [stress-ng](https://github.com/ColinIanKing/stress-ng) CPU workload on the cluster. 
Target your OpenShift cluster with the appropriate `kubeconfig` file, and add its file path as 
the value for `kubernetes_target.kubeconfig_path`, in the input file. Any combination of subworkflows can be disabled in the input file by setting either `cpu_hog_enabled`, `pod_chaos_enabled`, or `kubeburner_enabled` to `false`. 


## Files

- [`workflow.yaml`](workflow.yaml) -- Defines the workflow input schema, the plugins to run
  and their data relationships, and the output to present to the user
- [`input.yaml`](input.yaml) -- The input parameters that the user provides for running
  the workflow
- [`config.yaml`](config.yaml) -- Global config parameters that are passed to the Arcaflow
  engine
- [`cpu-hog.yaml`](subworkflows/cpu-hog.yaml) -- The StressNG workload on the CPU.
- [`kubeburner.yaml`](subworkflows/kubeburner.yaml) -- The KubeBurner workload for the Kubernetes Cluster API.
- [`pod-chaos.yaml`](subworkflows/pod-chaos.yaml) -- The Kill Pod workflow for the Kubernetes infrastructure pods.
                     
## Running the Workflow

### Workflow Dependencies

Install Python, at least `3.9`.

First, add the path to your Python interpreter to `config.yaml` as the value 
for `pythonPath` as shown here. A common choice for users working in 
distributions of Linux operating systems is `usr/bin/python`. Second, add a 
directory to which your Arcaflow process will have write access as the 
value for `workdir`, `/tmp` is a common choice because your process will likely be able to write to it.

```yaml
deployers:
  python:
    pythonPath: /usr/bin/python
    workdir: /tmp
```

To use this Python interpreter with our `kill-pod` plugin, go to the `deploy` section of the `kill_pod` step in [`pod-chaos.yaml`](subworkflows/pod-chaos.yaml). You can use the same `pythonPath` and `workdir` that you used in 
your `config.yaml`.

```yaml
deploy:
  deployer_name: python
  modulePullPolicy: Always
  pythonPath: /usr/bin/python
  workdir: /tmp
```

Download a Go binary of the latest version of the Arcaflow engine from: https://github.com/arcalot/arcaflow-engine/releases.

#### OpenShift Target

Target your desired OpenShift cluster by setting the `kubeconfig_path` variable for each subworkflow's parameter list in [`input.yaml`](input.yaml).

#### Kube-Burner Plugin

The `kube-burner` plugin generates and reports the UUID to which the 
`kube-burner` data is associated in your search database. The `uuidgen` 
workflow step uses the `arcaflow-plugin-utilities` `uuid` plugin step to 
randomly generate a UUID for you.

### Workflow Execution

Run the workflow:
```
$ export WFPATH=<path to this workflow directory>
$ arcaflow --context ${WFPATH} --input input.yaml --config config.yaml --workflow workflow.yaml
```

## Workflow Diagram
This diagram shows the complete end-to-end workflow logic.

### Main Workflow

```mermaid
%% Mermaid markdown workflow
flowchart LR
%% Success path
input-->steps.cpu_hog_wf.enabling
input-->steps.cpu_hog_wf.execute
input-->steps.kubeburner_wf.enabling
input-->steps.kubeburner_wf.execute
input-->steps.pod_chaos_wf.enabling
input-->steps.pod_chaos_wf.execute
outputs.workflow_success.cpu_hog-->outputs.workflow_success
outputs.workflow_success.cpu_hog.disabled-->outputs.workflow_success.cpu_hog
outputs.workflow_success.cpu_hog.enabled-->outputs.workflow_success.cpu_hog
outputs.workflow_success.kubeburner-->outputs.workflow_success
outputs.workflow_success.kubeburner.disabled-->outputs.workflow_success.kubeburner
outputs.workflow_success.kubeburner.enabled-->outputs.workflow_success.kubeburner
outputs.workflow_success.pod_chaos-->outputs.workflow_success
outputs.workflow_success.pod_chaos.disabled-->outputs.workflow_success.pod_chaos
outputs.workflow_success.pod_chaos.enabled-->outputs.workflow_success.pod_chaos
steps.cpu_hog_wf.closed-->steps.cpu_hog_wf.closed.result
steps.cpu_hog_wf.disabled-->steps.cpu_hog_wf.disabled.output
steps.cpu_hog_wf.disabled.output-->outputs.workflow_success.cpu_hog.disabled
steps.cpu_hog_wf.enabling-->steps.cpu_hog_wf.closed
steps.cpu_hog_wf.enabling-->steps.cpu_hog_wf.disabled
steps.cpu_hog_wf.enabling-->steps.cpu_hog_wf.enabling.resolved
steps.cpu_hog_wf.enabling-->steps.cpu_hog_wf.execute
steps.cpu_hog_wf.execute-->steps.cpu_hog_wf.outputs
steps.cpu_hog_wf.outputs-->steps.cpu_hog_wf.outputs.success
steps.cpu_hog_wf.outputs.success-->outputs.workflow_success.cpu_hog.enabled
steps.kubeburner_wf.closed-->steps.kubeburner_wf.closed.result
steps.kubeburner_wf.disabled-->steps.kubeburner_wf.disabled.output
steps.kubeburner_wf.disabled.output-->outputs.workflow_success.kubeburner.disabled
steps.kubeburner_wf.enabling-->steps.kubeburner_wf.closed
steps.kubeburner_wf.enabling-->steps.kubeburner_wf.disabled
steps.kubeburner_wf.enabling-->steps.kubeburner_wf.enabling.resolved
steps.kubeburner_wf.enabling-->steps.kubeburner_wf.execute
steps.kubeburner_wf.execute-->steps.kubeburner_wf.outputs
steps.kubeburner_wf.outputs-->steps.kubeburner_wf.outputs.success
steps.kubeburner_wf.outputs.success-->outputs.workflow_success.kubeburner.enabled
steps.pod_chaos_wf.closed-->steps.pod_chaos_wf.closed.result
steps.pod_chaos_wf.disabled-->steps.pod_chaos_wf.disabled.output
steps.pod_chaos_wf.disabled.output-->outputs.workflow_success.pod_chaos.disabled
steps.pod_chaos_wf.enabling-->steps.pod_chaos_wf.closed
steps.pod_chaos_wf.enabling-->steps.pod_chaos_wf.disabled
steps.pod_chaos_wf.enabling-->steps.pod_chaos_wf.enabling.resolved
steps.pod_chaos_wf.enabling-->steps.pod_chaos_wf.execute
steps.pod_chaos_wf.execute-->steps.pod_chaos_wf.outputs
steps.pod_chaos_wf.outputs-->steps.pod_chaos_wf.outputs.success
steps.pod_chaos_wf.outputs.success-->outputs.workflow_success.pod_chaos.enabled
%% Error path
steps.cpu_hog_wf.execute-->steps.cpu_hog_wf.failed
steps.cpu_hog_wf.failed-->steps.cpu_hog_wf.failed.error
steps.kubeburner_wf.execute-->steps.kubeburner_wf.failed
steps.kubeburner_wf.failed-->steps.kubeburner_wf.failed.error
steps.pod_chaos_wf.execute-->steps.pod_chaos_wf.failed
steps.pod_chaos_wf.failed-->steps.pod_chaos_wf.failed.error
%% Mermaid end
```

### Pod Chaos Workflow

```mermaid
%% Mermaid markdown workflow
flowchart LR
%% Success path
input-->steps.kill_pod.starting
steps.kill_pod.cancelled-->steps.kill_pod.closed
steps.kill_pod.cancelled-->steps.kill_pod.outputs
steps.kill_pod.closed-->steps.kill_pod.closed.result
steps.kill_pod.deploy-->steps.kill_pod.closed
steps.kill_pod.deploy-->steps.kill_pod.starting
steps.kill_pod.disabled-->steps.kill_pod.disabled.output
steps.kill_pod.enabling-->steps.kill_pod.closed
steps.kill_pod.enabling-->steps.kill_pod.disabled
steps.kill_pod.enabling-->steps.kill_pod.enabling.resolved
steps.kill_pod.enabling-->steps.kill_pod.starting
steps.kill_pod.outputs-->steps.kill_pod.outputs.success
steps.kill_pod.outputs.success-->outputs.success
steps.kill_pod.running-->steps.kill_pod.closed
steps.kill_pod.running-->steps.kill_pod.outputs
steps.kill_pod.starting-->steps.kill_pod.closed
steps.kill_pod.starting-->steps.kill_pod.running
steps.kill_pod.starting-->steps.kill_pod.starting.started
%% Error path
steps.kill_pod.cancelled-->steps.kill_pod.crashed
steps.kill_pod.cancelled-->steps.kill_pod.deploy_failed
steps.kill_pod.crashed-->steps.kill_pod.crashed.error
steps.kill_pod.deploy-->steps.kill_pod.deploy_failed
steps.kill_pod.deploy_failed-->steps.kill_pod.deploy_failed.error
steps.kill_pod.enabling-->steps.kill_pod.crashed
steps.kill_pod.outputs-->steps.kill_pod.outputs.error
steps.kill_pod.running-->steps.kill_pod.crashed
steps.kill_pod.starting-->steps.kill_pod.crashed
%% Mermaid end
```

### StressNG (CPU Hog) Workflow

```mermaid
%% Mermaid markdown workflow
flowchart LR
%% Success path
input-->steps.kubeconfig.starting
input-->steps.stressng.deploy
input-->steps.stressng.starting
steps.kubeconfig.cancelled-->steps.kubeconfig.closed
steps.kubeconfig.cancelled-->steps.kubeconfig.outputs
steps.kubeconfig.closed-->steps.kubeconfig.closed.result
steps.kubeconfig.deploy-->steps.kubeconfig.closed
steps.kubeconfig.deploy-->steps.kubeconfig.starting
steps.kubeconfig.disabled-->steps.kubeconfig.disabled.output
steps.kubeconfig.enabling-->steps.kubeconfig.closed
steps.kubeconfig.enabling-->steps.kubeconfig.disabled
steps.kubeconfig.enabling-->steps.kubeconfig.enabling.resolved
steps.kubeconfig.enabling-->steps.kubeconfig.starting
steps.kubeconfig.outputs-->steps.kubeconfig.outputs.success
steps.kubeconfig.outputs.success-->steps.stressng.deploy
steps.kubeconfig.running-->steps.kubeconfig.closed
steps.kubeconfig.running-->steps.kubeconfig.outputs
steps.kubeconfig.starting-->steps.kubeconfig.closed
steps.kubeconfig.starting-->steps.kubeconfig.running
steps.kubeconfig.starting-->steps.kubeconfig.starting.started
steps.stressng.cancelled-->steps.stressng.closed
steps.stressng.cancelled-->steps.stressng.outputs
steps.stressng.closed-->steps.stressng.closed.result
steps.stressng.deploy-->steps.stressng.closed
steps.stressng.deploy-->steps.stressng.starting
steps.stressng.disabled-->steps.stressng.disabled.output
steps.stressng.enabling-->steps.stressng.closed
steps.stressng.enabling-->steps.stressng.disabled
steps.stressng.enabling-->steps.stressng.enabling.resolved
steps.stressng.enabling-->steps.stressng.starting
steps.stressng.outputs-->steps.stressng.outputs.success
steps.stressng.outputs.success-->outputs.success
steps.stressng.running-->steps.stressng.closed
steps.stressng.running-->steps.stressng.outputs
steps.stressng.starting-->steps.stressng.closed
steps.stressng.starting-->steps.stressng.running
steps.stressng.starting-->steps.stressng.starting.started
%% Error path
steps.kubeconfig.cancelled-->steps.kubeconfig.crashed
steps.kubeconfig.cancelled-->steps.kubeconfig.deploy_failed
steps.kubeconfig.crashed-->steps.kubeconfig.crashed.error
steps.kubeconfig.deploy-->steps.kubeconfig.deploy_failed
steps.kubeconfig.deploy_failed-->steps.kubeconfig.deploy_failed.error
steps.kubeconfig.enabling-->steps.kubeconfig.crashed
steps.kubeconfig.outputs-->steps.kubeconfig.outputs.error
steps.kubeconfig.running-->steps.kubeconfig.crashed
steps.kubeconfig.starting-->steps.kubeconfig.crashed
steps.stressng.cancelled-->steps.stressng.crashed
steps.stressng.cancelled-->steps.stressng.deploy_failed
steps.stressng.crashed-->steps.stressng.crashed.error
steps.stressng.deploy-->steps.stressng.deploy_failed
steps.stressng.deploy_failed-->steps.stressng.deploy_failed.error
steps.stressng.enabling-->steps.stressng.crashed
steps.stressng.outputs-->steps.stressng.outputs.error
steps.stressng.running-->steps.stressng.crashed
steps.stressng.starting-->steps.stressng.crashed
%% Mermaid end
```

### Kube-Burner Workflow

```mermaid
%% Mermaid markdown workflow
flowchart LR
%% Success path
input-->steps.kubeburner.starting
steps.kubeburner.cancelled-->steps.kubeburner.closed
steps.kubeburner.cancelled-->steps.kubeburner.outputs
steps.kubeburner.closed-->steps.kubeburner.closed.result
steps.kubeburner.deploy-->steps.kubeburner.closed
steps.kubeburner.deploy-->steps.kubeburner.starting
steps.kubeburner.disabled-->steps.kubeburner.disabled.output
steps.kubeburner.enabling-->steps.kubeburner.closed
steps.kubeburner.enabling-->steps.kubeburner.disabled
steps.kubeburner.enabling-->steps.kubeburner.enabling.resolved
steps.kubeburner.enabling-->steps.kubeburner.starting
steps.kubeburner.outputs-->steps.kubeburner.outputs.success
steps.kubeburner.outputs.success-->outputs.success
steps.kubeburner.running-->steps.kubeburner.closed
steps.kubeburner.running-->steps.kubeburner.outputs
steps.kubeburner.starting-->steps.kubeburner.closed
steps.kubeburner.starting-->steps.kubeburner.running
steps.kubeburner.starting-->steps.kubeburner.starting.started
steps.uuidgen.cancelled-->steps.uuidgen.closed
steps.uuidgen.cancelled-->steps.uuidgen.outputs
steps.uuidgen.closed-->steps.uuidgen.closed.result
steps.uuidgen.deploy-->steps.uuidgen.closed
steps.uuidgen.deploy-->steps.uuidgen.starting
steps.uuidgen.disabled-->steps.uuidgen.disabled.output
steps.uuidgen.enabling-->steps.uuidgen.closed
steps.uuidgen.enabling-->steps.uuidgen.disabled
steps.uuidgen.enabling-->steps.uuidgen.enabling.resolved
steps.uuidgen.enabling-->steps.uuidgen.starting
steps.uuidgen.outputs-->steps.uuidgen.outputs.success
steps.uuidgen.outputs.success-->steps.kubeburner.starting
steps.uuidgen.running-->steps.uuidgen.closed
steps.uuidgen.running-->steps.uuidgen.outputs
steps.uuidgen.starting-->steps.uuidgen.closed
steps.uuidgen.starting-->steps.uuidgen.running
steps.uuidgen.starting-->steps.uuidgen.starting.started
%% Error path
steps.kubeburner.cancelled-->steps.kubeburner.crashed
steps.kubeburner.cancelled-->steps.kubeburner.deploy_failed
steps.kubeburner.crashed-->steps.kubeburner.crashed.error
steps.kubeburner.deploy-->steps.kubeburner.deploy_failed
steps.kubeburner.deploy_failed-->steps.kubeburner.deploy_failed.error
steps.kubeburner.enabling-->steps.kubeburner.crashed
steps.kubeburner.outputs-->steps.kubeburner.outputs.error
steps.kubeburner.running-->steps.kubeburner.crashed
steps.kubeburner.starting-->steps.kubeburner.crashed
steps.uuidgen.cancelled-->steps.uuidgen.crashed
steps.uuidgen.cancelled-->steps.uuidgen.deploy_failed
steps.uuidgen.crashed-->steps.uuidgen.crashed.error
steps.uuidgen.deploy-->steps.uuidgen.deploy_failed
steps.uuidgen.deploy_failed-->steps.uuidgen.deploy_failed.error
steps.uuidgen.enabling-->steps.uuidgen.crashed
steps.uuidgen.outputs-->steps.uuidgen.outputs.error
steps.uuidgen.running-->steps.uuidgen.crashed
steps.uuidgen.starting-->steps.uuidgen.crashed
%% Mermaid end
```

