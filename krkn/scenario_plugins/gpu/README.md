# GPU scenarios

Krkn injects GPU faults through temporary privileged pods with host GPU access. It selects the target devices, coordinates the start across workers, and releases worker resources before deleting the pods.

## VRAM pressure (`vram-pressure`)

Allocate and hold GPU device memory. Select this fault with `fault-type: vram-pressure` or `GPU_FAULT_TYPE=vram-pressure`.

### Configuration

Requires NVIDIA drivers and toolkit, full GPUs in CUDA `DEFAULT` mode, and an existing namespace that allows privileged helper pods. MIG, MPS, and vGPU are unsupported.

```yaml
fault-type: vram-pressure
image: quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-gpu
namespace: krkn-gpu-test
node-selector: "kubernetes.io/hostname=gpu-node"
number-of-nodes: 1
gpu-ids: "all"
gpu-vram: "20%"
duration: 60
```

Register the scenario file in the main Krkn configuration:

```yaml
kraken:
  chaos_scenarios:
    - gpu_scenarios:
        - scenarios/kube/gpu-vram.yml
```

See the [example scenario](../../../scenarios/kube/gpu-vram.yml) for optional settings.

### Parameters

- `duration` / `GPU_DURATION`: hold time in seconds after all workers are ready.
- `memory-reserve` / `GPU_MEMORY_RESERVE`: free-memory safety reserve; default `64Mi`.
- `setup-timeout` / `GPU_SETUP_TIMEOUT`: setup timeout; default 120 seconds.
- `recovery-timeout` / `GPU_RECOVERY_TIMEOUT`: cleanup timeout; default 30 seconds.

#### Targeting

- **Node targeting:** Set `node-selector` to target the GPUs on the selected nodes. Use `gpu-ids` to narrow the selection.
- **Application targeting:** Use `pod-label-selector` and `target-namespace` as shown below. Krkn uses kubelet's PodResources API to find the GPUs assigned to matching pods and targets each shared GPU once.

```yaml
pod-label-selector: "app=my-inference-service"
target-namespace: krkn-gpu-test
```

Choose one targeting mode. `namespace` controls injector placement; `target-namespace` locates the application. Set `number-of-nodes` to limit the run to a subset of matching nodes.

#### GPU memory allocation

| `gpu-ids` | `gpu-vram` | Behavior |
| --- | --- | --- |
| `"all"` | `"20%"` | Hold 20% of each eligible GPU's total memory |
| `"all"` | `"2Gi"` | Hold 2 GiB on each eligible GPU |
| `"0,1,2"` | `"20%,30%,2Gi"` | Pair host indices and allocations in the supplied order |
| `"GPU-<uuid-a>,GPU-<uuid-b>"` | `"1Gi,30%"` | Target specific physical GPU UUIDs |
| `"all"` | `"20%,30%,20%"` | Pair values with exactly three eligible GPUs, sorted by numeric host index |

One memory value applies to all selected GPUs; a list must match the selected GPU count on each node. GPU indices are host indices and can change after reboot. Use UUIDs for persistent device identity. Percentages use total usable GPU memory and are applied on top of existing allocations. Absolute sizes accept `Ki`, `Mi`, `Gi`, and `Ti`.

#### Environment overrides

Environment variables override YAML, for example:

```bash
export GPU_IDS="0,1"
export GPU_VRAM="20%,2Gi"
export GPU_DURATION=60
```

`GPU_IMAGE`, `NODE_SELECTOR`, `POD_LABEL_SELECTOR`, `TARGET_NAMESPACE`, and `NAMESPACE` also override their corresponding settings. Unset stale overrides when switching targeting modes.

### Runtime and results

Krkn automatically selects RuntimeClass `nvidia` when available and uses the cluster default otherwise. Set `runtime-class-name` to override this selection. Automatic lookup requires `get` permission on `node.k8s.io/runtimeclasses` for `nvidia`.

Workers report GPU UUIDs, requested and actual allocations, free and used memory, and release and probe results. The default safety reserve is `64Mi`. Krkn fails the scenario if the injector cannot reach its target. Cleanup runs on failure or interruption, with a worker deadline as a backstop.

Holding VRAM reduces the memory available for future allocations. A preallocated inference server may show little change. Application OOM can be an intended effect; injector allocation or cleanup failure is a scenario failure. Measure application throughput and latency separately.

## Compute pressure (`compute-pressure`)

Krkn runs short FP32 multiply-add batches on each selected GPU. `gpu-compute-duty-cycle` sets the pace by controlling how long the worker waits between batches.

```yaml
fault-type: compute-pressure
image: quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-gpu
namespace: krkn-gpu-test
pod-label-selector: "app=vllm-demo"
target-namespace: krkn-gpu-test
gpu-ids: "all"
gpu-compute-duty-cycle: "20%"
duration: 60
```

Register the [example scenario](../../../scenarios/kube/gpu-compute.yml) under `gpu_scenarios`. For node targeting, replace the two pod-targeting fields with `node-selector`.

### How the duty cycle works

For each GPU, the worker repeats this loop until `duration` expires:

```text
batch_ms = run_fp32_batch_and_wait()  # wall-clock time from launch to completion
pause_ms = batch_ms × (100 - duty_cycle) / duty_cycle
wait(pause_ms)
```

At `20%`, if a batch takes `10 ms`, the worker waits `10 × (100 - 20) / 20 = 40 ms` before launching the next batch. Higher percentages shorten the pause so more batches can run in the same duration. At `100%`, there is no pause. This controls injector pacing, not device-wide GPU utilization.

Set `gpu-compute-duty-cycle` (or `GPU_COMPUTE_DUTY_CYCLE`) to a whole percentage from `1` to `100`, with an optional `%`. One value applies to all selected GPUs. To set them individually, pair `gpu-ids: "1,0"` with `gpu-compute-duty-cycle: "20%,30%"`; `all` pairs values in ascending host-index order. A list must match the selected GPU count on each node.
