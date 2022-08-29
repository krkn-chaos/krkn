### Pod Scenarios

Krkn recently replaced PowerfulSeal with its own internal pod scenarios using a plugin system. You can run pod scenarios by adding the following config to Krkn:

```yaml
kraken:
  chaos_scenarios:
    - plugin_scenarios:
      - path/to/scenario.yaml
```

You can then create the scenario file with the following contents:

```yaml
# yaml-language-server: $schema=../plugin.schema.json
- id: kill-pods
  config:
    namespace_pattern: ^kube-system$
    label_selector: k8s-app=kube-scheduler
- id: wait-for-pods
  config:
    namespace_pattern: ^kube-system$
    label_selector: k8s-app=kube-scheduler
    count: 3
```

Please adjust the schema reference to point to the [schema file](../scenarios/plugin.schema.json). This file will give you code completion and documentation for the available options in your IDE.

#### Pod Chaos Scenarios

The following are the components of Kubernetes/OpenShift for which a basic chaos scenario config exists today.

| Component                | Description | Working  |
| ------------------------ |-------------| -------- |
| [Basic pod scenario](../scenarios/kube/pod.yml) | Kill a pod. | :heavy_check_mark: |
| [Etcd](../scenarios/openshift/etcd.yml) | Kills a single/multiple etcd replicas. | :heavy_check_mark: |
| [Kube ApiServer](../scenarios/openshift/openshift-kube-apiserver.yml)| Kills a single/multiple kube-apiserver replicas. | :heavy_check_mark: |
| [ApiServer](../scenarios/openshift/openshift-apiserver.yml) | Kills a single/multiple apiserver replicas. | :heavy_check_mark: |
| [Prometheus](../scenarios/openshift/prometheus.yml) | Kills a single/multiple prometheus replicas. | :heavy_check_mark: |
| [OpenShift System Pods](../scenarios/openshift/regex_openshift_pod_kill.yml) | Kills random pods running in the OpenShift system namespaces. | :heavy_check_mark: |
