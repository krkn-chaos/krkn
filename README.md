# Kraken
Chaos and resiliency testing tool for Kubernetes and OpenShift.
Kraken injects deliberate failures into Kubernetes/OpenShift clusters to check if it is resilient to turbulent conditions.


### Workflow
![Kraken workflow](media/kraken-workflow.png)


### Installation and usage
Instructions on how to setup, configure and run Kraken can be found at [Installation](docs/installation.md).


### Config
Instructions on how to setup the config and the options supported can be found at [Config](docs/config.md).


### Kubernetes/OpenShift chaos scenarios supported
Kraken supports pod, node and time/date based scenarios.

- [Pod Scenarios](docs/pod_scenarios.md)

- [Node Scenarios](docs/node_scenarios.md)

- [Time Scenarios](docs/time_scenarios.md)


### Kraken scenario pass/fail criteria and report
It's important to make sure to check if the targeted component recovered from the chaos injection and also if the Kubernetes/OpenShift cluster is healthy as failures in one component can have an adverse impact on other components. Kraken does this by:
- Having built in checks for pod and node based scenarios to ensure the expected number of replicas and nodes are up. It also supports running custom scripts with the checks.
- Leveraging [Cerberus](https://github.com/openshift-scale/cerberus) to monitor the cluster under test and consuming the aggregated go/no-go signal to determine pass/fail. It is highly recommended to turn on the Cerberus health check feature avaliable in Kraken. Instructions on installing and setting up Cerberus can be found [here](https://github.com/openshift-scale/cerberus#installation). Once Cerberus is up and running, set cerberus_enabled to True and cerberus_url to the url where Cerberus publishes go/no-go signal in the Kraken config file.


### Performance monitoring
Monitoring the Kubernetes/OpenShift cluster to observe the impact of Kraken chaos scenarios on various components is key to find out the bottlenecks as it's important to make sure the cluster is healthy in terms if both recovery as well as performance during/after the failure has been injected. Instructions on enabling it can be found [here](docs/performance_dasboards.md).

### Blogs and other useful resources
- Blog post on introduction to Kraken: https://www.openshift.com/blog/introduction-to-kraken-a-chaos-tool-for-openshift/kubernetes
- Discussion and demo on how Kraken can be leveraged to ensure OpenShift is reliable, performant and scalable: https://www.youtube.com/watch?v=s1PvupI5sD0&ab_channel=OpenShift


### Contributions
We are always looking for more enhancements, fixes to make it better, any contributions are most welcome. Feel free to report or work on the issues filed on github. 

[More information on how to Contribute](docs/contribute.md)

### Community
Key Members(slack_usernames): paigerube14, rook, mffiedler, mohit, dry923, rsevilla, ravi
* [**#sig-scalability on Kubernetes Slack**](https://kubernetes.slack.com)
* [**#forum-perfscale on CoreOS Slack**](https://coreos.slack.com)
