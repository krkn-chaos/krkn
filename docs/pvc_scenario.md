### PVC scenario
Scenario to fill up a given PersistenVolumeClaim by creating a temp file of a given size from a pod that has the volume mounted in the given path. The purpose of this scenario is to fill up a volume to understand faults cause by the application using this volume. 

##### Sample scenario config
```
pvc_scenario:                        # Scenario to stop all the nodes for specified duration and restart the nodes
  pod_name: pod_name                 # Name of the pod with the PVC linked to
  namespace: namespace_name          # Namespace where the pod is
  mount_path: /path/to/pvc           # Path to the PVC in the default container pod
  file_size: 1024                    # Size of the file to be created in the PVC (block size is 1K)
  duration: 60                       # Duration in seconds for the fault
```

##### Steps
 - Connect to the `pod_name`
 - Change directory to the `mount_path`
 - Create a temp file `kraken.tmp` with random on the `mount_path`:
    - `dd bs=1024 count=$file_size </dev/urandom >kraken.tmp`
 - Wait for the `duration` time
 - Remove the temp file created:
    - `rm kraken.tmp`
