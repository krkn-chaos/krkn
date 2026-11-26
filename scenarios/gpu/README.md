# GPU scenarios

Example scenarios for GPU-accelerated clusters. They use existing krkn plugins;
no new krkn code.

## GPU telemetry blackout (NVIDIA DCGM exporter)

Disrupts the NVIDIA DCGM exporter, the component that turns GPU state into
Prometheus metrics, and checks that the loss of GPU telemetry is detected and
that telemetry recovers afterwards.

| File | What it does | krkn plugin |
|---|---|---|
| `dcgm_exporter_pod_disruption.yaml` | Deletes an exporter pod; checks the DaemonSet recreates it and every GPU reports again (recovery) | `pod_disruption_scenarios` |
| `dcgm_exporter_outage.yaml` | Blocks scrapes to the exporters for `duration`; checks the alert fires, then that telemetry returns and the alert clears (detection and recovery) | `application_outages_scenarios` |
| `dcgm_exporter_alert_rules.yaml` | `PrometheusRule` defining `GPUTelemetryMissing`, the alert the checks look for | none, apply with `kubectl` |

Checks used with them:

| File | Used by |
|---|---|
| `config/alerts_gpu_dcgm_telemetry.yaml` | pod disruption: telemetry back, every GPU back, alert not firing at the end |
| `config/alerts_gpu_dcgm_telemetry_outage.yaml` | outage: the same, plus "the alert fired during the run" |
| `config/resiliency_gpu_dcgm_telemetry.yaml` | both: the recovery checks as resiliency SLOs |

`GPUTelemetryMissing` is defined by this example. Neither the GPU Operator nor
dcgm-exporter ships a default alert for a missing exporter. To use an alert you
already run, change the `alertname` in the two alert profiles and recompute the
outage `duration` from its `for:`.

### Run

1. Apply the alert: `kubectl apply -f scenarios/gpu/dcgm_exporter_alert_rules.yaml`.
2. Copy the "Use with" block from the scenario file into your krkn config
   (alert profile, resiliency file, the post-scenario `object_state_checks`,
   `wait_duration`).
3. Run each scenario in its own krkn run, so the run window is that
   scenario's window.

The defaults (namespace `gpu-operator`, label `app=nvidia-dcgm-exporter`)
match the upstream GPU Operator Helm install. The alert's job
`nvidia-dcgm-exporter` is the operator's Service name, which a ServiceMonitor
uses as the job by default; check it against your scrape config. Check each
scenario file's notes for OpenShift and other installs. The utilization
checks match both `DCGM_FI_DEV_GPU_UTIL` and `DCGM_FI_DEV_GPU_UTIL_RATIO`
(the dcgm-exporter 4.9.0 name).

Tested on kind with NVIDIA
[k8s-test-infra](https://github.com/NVIDIA/k8s-test-infra) (mock NVML, real GPU
Operator and dcgm-exporter). Not yet run on real GPUs.
