# GPU scenarios

Krkn injects GPU faults through temporary privileged pods with host GPU access. It selects the target devices, coordinates the start across workers, and releases worker resources before deleting the pods.

## Examples

- [VRAM pressure](../../../scenarios/kube/gpu-vram.yml)
- [Compute pressure](../../../scenarios/kube/gpu-compute.yml)
- [SM clock limit](../../../scenarios/kube/gpu-clock.yml)
- [GPU power limit](../../../scenarios/kube/gpu-power.yml)

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

### GPU observations and telemetry

Krkn uses `krkn-lib` for node and pod resource lookups. The worker still resolves
workload GPU assignments on the target node through kubelet PodResources; it
does not exec into application pods.

Each `workload-krkn-gpu` worker uses the shared `krkn-lib` observer on its
assigned node. No controller-local flag or workload pod exec is needed. GPU
telemetry records a baseline, the latest holding sample, and a post-release
sample for selected devices when available. It is not a complete time series.
Compute batch counters measure injector work; GPU utilization is a separate
device-wide observation. Unavailable optional measurements do not change the
fault outcome. VRAM allocation and recovery checks still require devices to be
observable.

The worker environment must include a `krkn-lib` release with
`snapshot_local_gpus`.

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

For node targeting, replace the two pod-targeting fields with `node-selector`.

### How the duty cycle works

For each GPU, the worker repeats this loop until `duration` expires:

```text
batch_ms = run_fp32_batch_and_wait()  # wall-clock time from launch to completion
pause_ms = batch_ms × (100 - duty_cycle) / duty_cycle
wait(pause_ms)
```

At `20%`, if a batch takes `10 ms`, the worker waits `10 × (100 - 20) / 20 = 40 ms` before launching the next batch. Higher percentages shorten the pause so more batches can run in the same duration. At `100%`, there is no pause. This controls injector pacing, not device-wide GPU utilization.

Set `gpu-compute-duty-cycle` (or `GPU_COMPUTE_DUTY_CYCLE`) to a whole percentage from `1` to `100`, with an optional `%`. One value applies to all selected GPUs. To set them individually, pair `gpu-ids: "1,0"` with `gpu-compute-duty-cycle: "20%,30%"`; `all` pairs values in ascending host-index order. A list must match the selected GPU count on each node.

## SM clock limit (`clock-limit`)

Locks the NVIDIA graphics/SM clock without issuing CUDA work or changing memory-clock or power-limit settings. Set `gpu-clock-mhz` (`GPU_CLOCK_MHZ`) to a positive whole MHz ceiling or a comma-separated list. One value applies to every selected GPU. A list pairs with explicit IDs in input order, or with `all` in ascending host index order on each selected node. For each GPU, the worker queries NVML and picks the highest supported clock at or below the request (for example, 1,400 MHz can resolve to 1,395 MHz). If a request exceeds a device's maximum or no supported value fits, the worker fails before applying any lock on that node.

```yaml
fault-type: clock-limit
image: quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-gpu
namespace: krkn-gpu-test
node-selector: "kubernetes.io/hostname=gpu-node"
gpu-ids: "all"
gpu-clock-mhz: 1800
duration: 30
```

Clock policy affects the whole physical device. Reserve the GPUs for the test and disable GPU sharing. Use GPUs that start with NVIDIA's default SM clock policy: cleanup resets to driver defaults and does not preserve an existing custom clock lock. The baseline MHz reading is a measurement, not a saved clock policy.

**Do not overlap clock-limit runs on the same physical GPU.** Krkn does not enforce this. One worker's reset can clear another's active limit. Runs on different GPUs can share a node.

The watchdog in each worker resets the SM policy at expiry or cancellation. Per-GPU execution stats record `requested_sm_clock_mhz`, `max_sm_clock_mhz`, and `applied_sm_clock_mhz` (the value the driver accepted). Measured `sm_clock_mhz` lives in the phase snapshots; reset outcomes are separate. Do not force-delete a live clock worker. If the worker is lost or reset is unconfirmed, the lock may still be active. Have the node operator restore the known default policy before targeting that GPU again.

Choose a ceiling below the workload's normal SM clock. The worker reports an ineffective lock if it never observes the applied clock on a selected GPU. Use the same workload before, during, and after; a lower clock need not reduce application throughput.

## GPU power limit (`power-limit`)

Lowers the enforced power cap on dedicated physical NVIDIA GPUs without launching CUDA work. Set `gpu-power-limit-w` (`GPU_POWER_LIMIT_W`) to a positive whole number of watts or a comma-separated list. A scalar applies to all selected GPUs. A list follows the order of explicit `gpu-ids`, or ascending host index when `gpu-ids` is `all`. Each value must be within its GPU's supported range and below its current configured and enforced limits.

```yaml
fault-type: power-limit
image: quay.io/krkn-chaos/krkn-hub-multiarch:workload-krkn-gpu
node-selector: "kubernetes.io/hostname=gpu-node"
gpu-ids: "0"
gpu-power-limit-w: 65
duration: 30
```

Use the same node or pod targeting as `clock-limit`. The cap affects every workload on the physical GPU. **Operators must not overlap runs or change the target's power or clock policies during the test.** Krkn does not enforce run exclusivity.

After setting each cap once, the worker polls NVML for up to five seconds per GPU, bounded by `setup-timeout`. The hold starts only when the configured and enforced values both match on all targets. If verification fails, the worker reports the last readback and restores any caps it attempted to change.

The privileged worker keeps the original cap in memory, verifies the applied cap, and restores and verifies the original setting on completion or cancellation. The worker can restore the cap if the Krkn runner exits, but not if the worker itself is lost. Record the original cap before the run; if restoration is unverified, have the node operator restore and verify it before reusing that GPU.

An applied cap does not guarantee throttling. `power_throttle_observed` records whether the driver reported software power capping in any hold sample; it is absent when that signal is unavailable. Compare the same workload before, during, and after the cap.
