#### Kubernetes cluster shut down scenario
Scenario to shut down all the nodes including the masters and restart them after specified duration. Cluster shut down scenario can be injected by placing the shut_down config file under cluster_shut_down_scenario option in the kraken config. Refer to [cluster_shut_down_scenario](https://github.com/krkn-chaos/krkn/blob/main/scenarios/cluster_shut_down_scenario.yml) config file.

Refer to [cloud setup](cloud_setup.md) to configure your cli properly for the cloud provider of the cluster you want to shut down.

Current accepted cloud types:
* [Azure](cloud_setup.md#azure)
* [GCP](cloud_setup.md#gcp)
* [AWS](cloud_setup.md#aws)
* [Openstack](cloud_setup.md#openstack)


```
cluster_shut_down_scenario:                          # Scenario to stop all the nodes for specified duration and restart the nodes.
  runs: 1                                            # Number of times to execute the cluster_shut_down scenario.
  shut_down_duration: 120                            # Duration in seconds to shut down the cluster.
  cloud_type: aws                                    # Cloud type on which Kubernetes/OpenShift runs.
```
