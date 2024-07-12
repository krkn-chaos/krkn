# OpenShift Shenanigans

## Workflow Description

Given a target OpenShift cluster, this workflow executes a [kube-burner plugin](https://github.com/redhat-performance/arcaflow-plugin-kube-burner) workflow to place a load on the cluster, repeatedly removes a targeted pod at a given time frequency with the [kill-pod plugin](https://github.com/krkn-chaos/arcaflow-plugin-kill-pod), and runs a [stress-ng](https://github.com/ColinIanKing/stress-ng) CPU workload on the cluster.


## Files

- [`workflow.yaml`](workflow.yaml) -- Defines the workflow input schema, the plugins to run
  and their data relationships, and the output to present to the user
- [`input.yaml`](input.yaml) -- The input parameters that the user provides for running
  the workflow
- [`config.yaml`](config.yaml) -- Global config parameters that are passed to the Arcaflow
  engine
- [`cpu-hog.yaml`](subworkflows/cpu-hog.yaml)
- [`kubeburner.yaml`](subworkflows/kubeburner.yaml)
- [`pod-chaos.yaml`](subworkflows/pod-chaos.yaml)
                     
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
steps.kubeburner_wf.outputs-->steps.kubeburner_wf.outputs.success
steps.kubeburner_wf.outputs.success-->outputs.success
input-->steps.pod_chaos_wf.execute
input-->steps.hog_cpu_wf.execute
input-->steps.kubeburner_wf.execute
steps.kubeburner_wf.execute-->steps.kubeburner_wf.outputs
steps.pod_chaos_wf.outputs-->steps.pod_chaos_wf.outputs.success
steps.pod_chaos_wf.execute-->steps.pod_chaos_wf.outputs
steps.pod_chaos_wf.outputs.success-->outputs.success
steps.hog_cpu_wf.execute-->steps.hog_cpu_wf.outputs
steps.hog_cpu_wf.outputs.success-->outputs.success
steps.hog_cpu_wf.outputs-->steps.hog_cpu_wf.outputs.success
%% Error path
steps.kubeburner_wf.failed-->steps.kubeburner_wf.failed.error
steps.hog_cpu_wf.failed-->steps.hog_cpu_wf.failed.error
steps.kubeburner_wf.execute-->steps.kubeburner_wf.failed
steps.pod_chaos_wf.execute-->steps.pod_chaos_wf.failed
steps.pod_chaos_wf.failed-->steps.pod_chaos_wf.failed.error
steps.hog_cpu_wf.execute-->steps.hog_cpu_wf.failed
%% Mermaid end
```

### Pod Chaos Workflow

```mermaid
%% Mermaid markdown workflow
flowchart LR
%% Success path
steps.kill_pod.enabling-->steps.kill_pod.disabled
steps.kill_pod.enabling-->steps.kill_pod.enabling.resolved
steps.kill_pod.enabling-->steps.kill_pod.starting
input-->steps.kill_pod.starting
steps.kill_pod.running-->steps.kill_pod.outputs
steps.kill_pod.starting-->steps.kill_pod.starting.started
steps.kill_pod.starting-->steps.kill_pod.running
steps.kill_pod.cancelled-->steps.kill_pod.outputs
steps.kill_pod.disabled-->steps.kill_pod.disabled.output
steps.kill_pod.outputs.success-->outputs.success
steps.kill_pod.deploy-->steps.kill_pod.starting
steps.kill_pod.outputs-->steps.kill_pod.outputs.success
%% Error path
steps.kill_pod.enabling-->steps.kill_pod.crashed
steps.kill_pod.crashed-->steps.kill_pod.crashed.error
steps.kill_pod.running-->steps.kill_pod.crashed
steps.kill_pod.starting-->steps.kill_pod.crashed
steps.kill_pod.cancelled-->steps.kill_pod.crashed
steps.kill_pod.cancelled-->steps.kill_pod.deploy_failed
steps.kill_pod.deploy_failed-->steps.kill_pod.deploy_failed.error
steps.kill_pod.deploy-->steps.kill_pod.deploy_failed
steps.kill_pod.outputs-->steps.kill_pod.outputs.error
%% Mermaid end
```

### StressNG (CPU Hog) Workflow

```mermaid
%% Mermaid markdown workflow
flowchart LR
%% Success path
steps.kubeconfig.outputs-->steps.kubeconfig.outputs.success
steps.kubeconfig.deploy-->steps.kubeconfig.starting
steps.kubeconfig.starting-->steps.kubeconfig.starting.started
steps.kubeconfig.starting-->steps.kubeconfig.running
steps.stressng.enabling-->steps.stressng.enabling.resolved
steps.stressng.enabling-->steps.stressng.starting
steps.stressng.enabling-->steps.stressng.disabled
steps.stressng.running-->steps.stressng.outputs
steps.stressng.deploy-->steps.stressng.starting
steps.stressng.outputs-->steps.stressng.outputs.success
steps.stressng.disabled-->steps.stressng.disabled.output
steps.stressng.cancelled-->steps.stressng.outputs
input-->steps.kubeconfig.starting
input-->steps.stressng.deploy
input-->steps.stressng.starting
steps.kubeconfig.running-->steps.kubeconfig.outputs
steps.stressng.outputs.success-->outputs.success
steps.kubeconfig.outputs.success-->steps.stressng.deploy
steps.kubeconfig.cancelled-->steps.kubeconfig.outputs
steps.kubeconfig.disabled-->steps.kubeconfig.disabled.output
steps.stressng.starting-->steps.stressng.running
steps.stressng.starting-->steps.stressng.starting.started
steps.kubeconfig.enabling-->steps.kubeconfig.enabling.resolved
steps.kubeconfig.enabling-->steps.kubeconfig.starting
steps.kubeconfig.enabling-->steps.kubeconfig.disabled
%% Error path
steps.kubeconfig.outputs-->steps.kubeconfig.outputs.error
steps.kubeconfig.deploy-->steps.kubeconfig.deploy_failed
steps.kubeconfig.starting-->steps.kubeconfig.crashed
steps.kubeconfig.crashed-->steps.kubeconfig.crashed.error
steps.stressng.deploy_failed-->steps.stressng.deploy_failed.error
steps.stressng.enabling-->steps.stressng.crashed
steps.stressng.running-->steps.stressng.crashed
steps.stressng.deploy-->steps.stressng.deploy_failed
steps.stressng.outputs-->steps.stressng.outputs.error
steps.stressng.cancelled-->steps.stressng.crashed
steps.stressng.cancelled-->steps.stressng.deploy_failed
steps.kubeconfig.deploy_failed-->steps.kubeconfig.deploy_failed.error
steps.kubeconfig.running-->steps.kubeconfig.crashed
steps.kubeconfig.cancelled-->steps.kubeconfig.deploy_failed
steps.kubeconfig.cancelled-->steps.kubeconfig.crashed
steps.stressng.crashed-->steps.stressng.crashed.error
steps.stressng.starting-->steps.stressng.crashed
steps.kubeconfig.enabling-->steps.kubeconfig.crashed
%% Mermaid end
```

### Kube-Burner Workflow

```mermaid
%% Mermaid markdown workflow
flowchart LR
%% Success path
steps.uuidgen.running-->steps.uuidgen.outputs
steps.kubeburner.outputs-->steps.kubeburner.outputs.success
steps.kubeburner.running-->steps.kubeburner.outputs
steps.uuidgen.starting-->steps.uuidgen.starting.started
steps.uuidgen.starting-->steps.uuidgen.running
steps.uuidgen.outputs-->steps.uuidgen.outputs.success
steps.uuidgen.cancelled-->steps.uuidgen.outputs
steps.kubeburner.disabled-->steps.kubeburner.disabled.output
steps.kubeburner.starting-->steps.kubeburner.starting.started
steps.kubeburner.starting-->steps.kubeburner.running
steps.uuidgen.disabled-->steps.uuidgen.disabled.output
steps.kubeburner.enabling-->steps.kubeburner.enabling.resolved
steps.kubeburner.enabling-->steps.kubeburner.starting
steps.kubeburner.enabling-->steps.kubeburner.disabled
input-->steps.kubeburner.starting
steps.kubeburner.deploy-->steps.kubeburner.starting
steps.kubeburner.outputs.success-->outputs.success
steps.uuidgen.outputs.success-->steps.kubeburner.starting
steps.kubeburner.cancelled-->steps.kubeburner.outputs
steps.uuidgen.deploy-->steps.uuidgen.starting
steps.uuidgen.enabling-->steps.uuidgen.enabling.resolved
steps.uuidgen.enabling-->steps.uuidgen.starting
steps.uuidgen.enabling-->steps.uuidgen.disabled
%% Error path
steps.uuidgen.running-->steps.uuidgen.crashed
steps.kubeburner.outputs-->steps.kubeburner.outputs.error
steps.kubeburner.running-->steps.kubeburner.crashed
steps.uuidgen.starting-->steps.uuidgen.crashed
steps.uuidgen.outputs-->steps.uuidgen.outputs.error
steps.uuidgen.cancelled-->steps.uuidgen.crashed
steps.uuidgen.cancelled-->steps.uuidgen.deploy_failed
steps.uuidgen.deploy_failed-->steps.uuidgen.deploy_failed.error
steps.kubeburner.starting-->steps.kubeburner.crashed
steps.uuidgen.crashed-->steps.uuidgen.crashed.error
steps.kubeburner.enabling-->steps.kubeburner.crashed
steps.kubeburner.deploy_failed-->steps.kubeburner.deploy_failed.error
steps.kubeburner.deploy-->steps.kubeburner.deploy_failed
steps.kubeburner.cancelled-->steps.kubeburner.crashed
steps.kubeburner.cancelled-->steps.kubeburner.deploy_failed
steps.kubeburner.crashed-->steps.kubeburner.crashed.error
steps.uuidgen.deploy-->steps.uuidgen.deploy_failed
steps.uuidgen.enabling-->steps.uuidgen.crashed
%% Mermaid end
```

