### Config
Set the scenarios to inject and the tunings like duration to wait between each scenario in the config file located at config/config.yaml. A sample config looks like:

```
kraken:
    kubeconfig_path: /root/.kube/config                    # Path to kubeconfig
    exit_on_failure: False                                 # Exit when a post action scenario fails
    chaos_scenarios:                                         # List of policies/chaos scenarios to load
        -   pod_scenarios:                                 # List of chaos pod scenarios to load
            - -    scenarios/etcd.yml
            - -    scenarios/regex_openshift_pod_kill.yml
              -    scenarios/post_action_regex.py
        -   node_scenarios:                                # List of chaos node scenarios to load
            -   scenarios/node_scenarios_example.yml
        -   pod_scenarios:
            - -    scenarios/openshift-apiserver.yml
            - -    scenarios/openshift-kube-apiserver.yml
        -   time_scenarios:                                # List of chaos time scenarios to load
            - scenarios/time_scenarios_example.yml

cerberus:
    cerberus_enabled: False                                # Enable it when cerberus is previously installed
    cerberus_url:                                          # When cerberus_enabled is set to True, provide the url where cerberus publishes go/no-go signal

performance_monitoring:
    deploy_dashboards: False                              # Install a mutable grafana and load the performance dashboards. Enable this only when running on OpenShift
    repo: "https://github.com/cloud-bulldozer/performance-dashboards.git"

tunings:
    wait_duration: 60                                      # Duration to wait between each chaos scenario
    iterations: 1                                          # Number of times to execute the scenarios
    daemon_mode: False                                     # Iterations are set to infinity which means that the kraken will cause chaos forever
```
