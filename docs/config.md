### Config
Set the scenarios to inject and the tunings like duration to wait between each scenario in the config file located at config/config.yaml. A sample config looks like:

```
kraken:
    kubeconfig_path: /root/.kube/config                    # Path to kubeconfig
    scenarios:                                             # List of policies/chaos scenarios to load
        -    scenarios/etcd.yml
        -    scenarios/openshift-kube-apiserver.yml
        -    scenarios/openshift-apiserver.yml
    node_scenarios:                                        # List of chaos node scenarios to load
        -    scenarios/node_scenarios_example.yml

cerberus:
    cerberus_enabled: False                                # Enable it when cerberus is previously installed
    cerberus_url:                                          # When cerberus_enabled is set to True, provide the url where cerberus publishes go/no-go signal

tunings:
    wait_duration: 60                                      # Duration to wait between each chaos scenario
    iterations: 1                                          # Number of times to execute the scenarios
    daemon_mode: False                                     # Iterations are set to infinity which means that the kraken will cause chaos forever
