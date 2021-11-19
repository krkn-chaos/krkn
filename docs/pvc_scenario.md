### PVC scenario
Scenario to fill up a given PersistenVolumeClaim by creating a temp file on the PVC from a pod associated with it. The purpose of this scenario is to fill up a volume to understand faults cause by the application using this volume.

##### Sample scenario config
```
pvc_scenario:
  pvc_name: <pvc_name>          # Name of the target PVC
  namespace: <namespace_name>   # Namespace where the PVC is
  fill_percentage: 50           # Target percentage to fill up the cluster, value must be higher than current percentage, valid values are between 0 and 99
  duration: 60                  # Duration in seconds for the fault
```

##### Steps
 - Get the `pod_name` where the PVC is mounted
 - Get the `mount_path` where the PVC is mounted in the pod
 - Get the PVC capacity and current used capacity
 - Calculate file size to fill the PVC to the target `fill_percentage`
 - Connect to the `pod_name`
 - Create a temp file `kraken.tmp` with random data on the `mount_path`:
    - `dd bs=1024 count=$file_size </dev/urandom > /mount_path/kraken.tmp`
 - Wait for the `duration` time
 - Remove the temp file created:
    - `rm kraken.tmp`
