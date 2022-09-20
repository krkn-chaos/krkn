### Zone outage scenario
Scenario to create outage in a targeted zone in the public cloud to understand the impact on both Kubernetes/OpenShift control plane as well as applications running on the worker nodes in that zone. It tweaks the network acl of the zone to simulate the failure and that in turn will stop both ingress and egress traffic from all the nodes in a particular zone for the specified duration and reverts it back to the previous state. Zone outage can be injected by placing the zone_outage config file under zone_outages option in the [kraken config](https://github.com/redhat-chaos/krkn/blob/main/config/config.yaml). Refer to [zone_outage_scenario](https://github.com/redhat-chaos/krkn/blob/main/scenarios/zone_outage.yaml) config file for the parameters that need to be defined.

Refer to [cloud setup](cloud_setup.md) to configure your cli properly for the cloud provider of the cluster you want to shut down.

##### Current accepted cloud types:
* [AWS](cloud_setup.md#aws)

##### Sample scenario config
```
zone_outage:                                         # Scenario to create an outage of a zone by tweaking network ACL.
  cloud_type: aws                                    # Cloud type on which Kubernetes/OpenShift runs. aws is the only platform supported currently for this scenario.
  duration: 600                                      # Duration in seconds after which the zone will be back online.
  vpc_id:                                            # Cluster virtual private network to target.
  subnet_id: [subnet1, subnet2]                      # List of subnet-id's to deny both ingress and egress traffic.
```

**NOTE**: vpc_id and subnet_id can be obtained from the cloud web console by selecting one of the instances in the targeted zone ( us-west-2a for example ).
**NOTE**: Multiple zones will experience downtime in case of targeting multiple subnets which might have an impact on the cluster health especially if the zones have control plane components deployed.

##### Debugging steps in case of failures
In case of failures during the steps which revert back the network acl to allow traffic and bring back the cluster nodes in the zone, the nodes in the particular zone will be in `NotReady` condition. Here is how to fix it:
- OpenShift by default deploys the nodes in different zones for fault tolerance, for example us-west-2a, us-west-2b, us-west-2c. The cluster is associated with a virtual private network and each zone has its own subnet with a network acl which defines the ingress and egress traffic rules at the zone level unlike security groups which are at an instance level.
- From the cloud web console, select one of the instances in the zone which is down and go to the subnet_id specified in the config.
- Look at the network acl associated with the subnet and you will see both ingress and egress traffic being denied which is expected as Kraken deliberately injects it.
- Kraken just switches the network acl while still keeping the original or default network acl around, switching to the default network acl from the drop-down menu will get back the nodes in the targeted zone into Ready state.
