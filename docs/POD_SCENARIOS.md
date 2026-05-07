# Pod Scenarios in Krkn

Pod scenarios let you kill pods and see what happens. It's that simple. You pick which pods to target, Krkn kills them, and then watches to see if they come back up properly.

This is useful for testing whether your apps can actually handle pod failures in production, or if everything falls apart the moment something goes wrong.

## How to Set It Up

### Main Config File

In your main Krkn config (usually `config.yaml`), you point to the scenario files you want to run:

```yaml
kraken:
  chaos_scenarios:
    - pod_disruption_scenarios:
        - scenarios/openshift/etcd.yml
        - scenarios/kube/pod.yml
```

That's it. Just list the scenario files, and Krkn will run them.

### Scenario Files

Each scenario file tells Krkn which pods to kill and how long to wait for them to recover:

```yaml
# yaml-language-server: $schema=../plugin.schema.json
- id: kill-pods
  config:
    namespace_pattern: ^kube-system$
    label_selector: k8s-app=kube-scheduler
    krkn_pod_recovery_time: 120
```

Breaking this down:
- `id: kill-pods` - Just a name for this test
- `namespace_pattern` - A regex to match which namespace(s) to target
- `label_selector` - Pick pods with specific labels (optional, but useful)
- `krkn_pod_recovery_time: 120` - Wait up to 120 seconds for pods to come back. If they don't, the test fails.

## What You Can Configure

### Picking Which Pods to Kill

You need to tell Krkn which pods to target. You can use any combination of these:

**namespace_pattern** - Regex to match namespaces
```yaml
namespace_pattern: ^kube-system$        # Just kube-system
namespace_pattern: ^openshift-.*$       # All openshift-* namespaces
namespace_pattern: .*                   # Everything (careful with this one)
```

**name_pattern** - Regex to match pod names
```yaml
name_pattern: ^nginx-.*$    # All pods starting with "nginx-"
name_pattern: ^etcd-.*$     # All etcd pods
```

**label_selector** - Standard Kubernetes label selector
```yaml
label_selector: k8s-app=kube-scheduler              # Single label
label_selector: app=nginx,tier=frontend             # Multiple labels
```

### Recovery Time

**krkn_pod_recovery_time** - How long to wait (in seconds) for pods to recover

```yaml
krkn_pod_recovery_time: 120    # Wait 2 minutes
```

If your app takes a while to start up, increase this. If pods don't recover in time, Krkn marks the test as failed.

## Examples

### Kill etcd Pods

```yaml
- id: kill-pods
  config:
    namespace_pattern: ^openshift-etcd$
    label_selector: app=etcd
    krkn_pod_recovery_time: 180
```

Kills etcd pods in the openshift-etcd namespace. Waits 3 minutes for them to recover.

### Kill the Scheduler

```yaml
- id: kill-pods
  config:
    namespace_pattern: ^kube-system$
    label_selector: k8s-app=kube-scheduler
    krkn_pod_recovery_time: 120
```

Targets the kube-scheduler. Good for testing if your cluster can handle scheduler failures.

### Kill Nginx Pods

```yaml
- id: kill-pods
  config:
    name_pattern: ^nginx-.*$
    krkn_pod_recovery_time: 60
```

Kills any pod with a name starting with "nginx-". Works across all namespaces.

### Kill Everything in OpenShift Namespaces

```yaml
- id: kill-pods
  config:
    namespace_pattern: ^openshift-.*$
    krkn_pod_recovery_time: 150
```

This one's aggressive - it'll kill pods in any namespace starting with "openshift-". Use with caution.

## What Actually Happens

1. Krkn finds pods matching your criteria
2. Kills them
3. Watches to see if they come back
4. If they recover within the timeout, test passes. If not, it fails.

Pretty straightforward.

## Tips

- **Start small**: Don't immediately kill critical pods. Test with something less important first.
- **Set realistic timeouts**: If your app takes 5 minutes to start, don't set recovery time to 30 seconds.
- **Be specific**: `namespace_pattern: .*` will target everything. That's probably not what you want.
- **Test in dev first**: Obviously.
- **Watch what happens**: Use Cerberus or similar tools to monitor cluster health during tests.

## When Things Go Wrong

**Pods aren't recovering**
- Check if they have proper restart policies set
- Make sure the cluster has enough resources (CPU/memory)
- Look at pod events: `kubectl describe pod <pod-name>`
- Maybe increase the recovery timeout

**No pods are being killed**
- Double-check your namespace exists: `kubectl get namespaces`
- Test your label selector: `kubectl get pods -l <label-selector>`
- Your regex might be wrong - test it carefully
- Check Krkn logs to see what it's actually selecting

**Tests keep failing**
- Are the pods actually getting killed? Check Krkn logs
- Does the cluster have capacity to reschedule them?
- Check node status - maybe nodes are down
- Look for resource quotas that might be blocking pod creation

## More Info

- [Krkn Documentation](https://krkn-chaos.dev/docs/)
- [Example Scenarios](../scenarios/)
- [Config Examples](../config/)
