# Krkn aka Kraken
![Workflow-Status](https://github.com/krkn-chaos/krkn/actions/workflows/docker-image.yml/badge.svg)
![coverage](https://krkn-chaos.github.io/krkn-lib-docs/coverage_badge_krkn.svg)
![action](https://github.com/krkn-chaos/krkn/actions/workflows/tests.yml/badge.svg)

![Krkn logo](media/logo.png)

Chaos and resiliency testing tool for Kubernetes.
Kraken injects deliberate failures into Kubernetes clusters to check if it is resilient to turbulent conditions.


### Workflow
![Kraken workflow](media/kraken-workflow.png)

### Demo
[![Kraken demo](media/KrakenStarting.png)](https://youtu.be/LN-fZywp_mo "Kraken Demo - Click to Watch!")


### Chaos Testing Guide
[Guide](docs/index.md) encapsulates:
- Test methodology that needs to be embraced.
- Best practices that an Kubernetes cluster, platform and applications running on top of it should take into account for best user experience, performance, resilience and reliability.
- Tooling.
- Scenarios supported.
- Test environment recommendations as to how and where to run chaos tests.
- Chaos testing in practice.

The guide is hosted at https://krkn-chaos.github.io/krkn.


### How to Get Started
Instructions on how to setup, configure and run Kraken can be found at [Installation](docs/installation.md).

You may consider utilizing the chaos recommendation tool prior to initiating the chaos runs to profile the application service(s) under test. This tool discovers a list of Krkn scenarios with a high probability of causing failures or disruptions to your application service(s). The tool can be accessed at [Chaos-Recommender](utils/chaos_recommender/README.md).

See the [getting started doc](docs/getting_started.md) on support on how to get started with your own custom scenario or editing current scenarios for your specific usage.

After installation, refer back to the below sections for supported scenarios and how to tweak the kraken config to load them on your cluster.


#### Running Kraken with minimal configuration tweaks
For cases where you want to run Kraken with minimal configuration changes, refer to [krkn-hub](https://github.com/krkn-chaos/krkn-hub). One use case is CI integration where you do not want to carry around different configuration files for the scenarios.


### Config
Instructions on how to setup the config and the options supported can be found at [Config](docs/config.md).


### Kubernetes chaos scenarios supported

Scenario type               | Kubernetes    
--------------------------- | ------------- | 
[Pod Scenarios](docs/pod_scenarios.md) | :heavy_check_mark: |
[Pod Network Scenarios](docs/pod_network_scenarios.md) | :x: |
[Container Scenarios](docs/container_scenarios.md) | :heavy_check_mark: |
[Node Scenarios](docs/node_scenarios.md) | :heavy_check_mark: |
[Time Scenarios](docs/time_scenarios.md) | :heavy_check_mark: |
[Hog Scenarios: CPU, Memory](docs/hog_scenarios.md) | :heavy_check_mark: |
[Cluster Shut Down Scenarios](docs/cluster_shut_down_scenarios.md) | :heavy_check_mark: |
[Service Disruption Scenarios](docs/service_disruption_scenarios.md.md) | :heavy_check_mark: |
[Zone Outage Scenarios](docs/zone_outage.md) | :heavy_check_mark: |
[Application_outages](docs/application_outages.md) | :heavy_check_mark: |
[PVC scenario](docs/pvc_scenario.md) | :heavy_check_mark: |
[Network_Chaos](docs/network_chaos.md) | :heavy_check_mark: |
[ManagedCluster Scenarios](docs/managedcluster_scenarios.md) | :heavy_check_mark: |
[Service Hijacking Scenarios](docs/service_hijacking_scenarios.md) | :heavy_check_mark: |
[SYN Flood Scenarios](docs/syn_flood_scenarios.md) | :heavy_check_mark: |


### Kraken scenario pass/fail criteria and report
It is important to make sure to check if the targeted component recovered from the chaos injection and also if the Kubernetes cluster is healthy as failures in one component can have an adverse impact on other components. Kraken does this by:
- Having built in checks for pod and node based scenarios to ensure the expected number of replicas and nodes are up. It also supports running custom scripts with the checks.
- Leveraging [Cerberus](https://github.com/krkn-chaos/cerberus) to monitor the cluster under test and consuming the aggregated go/no-go signal to determine pass/fail post chaos. It is highly recommended to turn on the Cerberus health check feature available in Kraken. Instructions on installing and setting up Cerberus can be found [here](https://github.com/openshift-scale/cerberus#installation) or can be installed from Kraken using the [instructions](https://github.com/krkn-chaos/krkn#setting-up-infrastructure-dependencies). Once Cerberus is up and running, set cerberus_enabled to True and cerberus_url to the url where Cerberus publishes go/no-go signal in the Kraken config file. Cerberus can monitor [application routes](https://github.com/redhat-chaos/cerberus/blob/main/docs/config.md#watch-routes) during the chaos and fails the run if it encounters downtime as it is a potential downtime in a customers, or users environment as well. It is especially important during the control plane chaos scenarios including the API server, Etcd, Ingress etc. It can be enabled by setting `check_applicaton_routes: True` in the [Kraken config](https://github.com/redhat-chaos/krkn/blob/main/config/config.yaml) provided application routes are being monitored in the [cerberus config](https://github.com/redhat-chaos/krkn/blob/main/config/cerberus.yaml).
- Leveraging built-in alert collection feature to fail the runs in case of critical alerts.
- Utilizing health check endpoints to observe application behavior during chaos injection [Health checks](docs/health_checks.md)

### Signaling
In CI runs or any external job it is useful to stop Kraken once a certain test or state gets reached. We created a way to signal to kraken to pause the chaos or stop it completely using a signal posted to a port of your choice.

For example if we have a test run loading the cluster running and kraken separately running; we want to be able to know when to start/stop the kraken run based on when the test run completes or gets to a certain loaded state.

More detailed information on enabling and leveraging this feature can be found [here](docs/signal.md).


### Performance monitoring
Monitoring the Kubernetes/OpenShift cluster to observe the impact of Kraken chaos scenarios on various components is key to find out the bottlenecks as it is important to make sure the cluster is healthy in terms if both recovery as well as performance during/after the failure has been injected. Instructions on enabling it can be found [here](docs/performance_dashboards.md).


### SLOs validation during and post chaos
- In addition to checking the recovery and health of the cluster and components under test, Kraken takes in a profile with the Prometheus expressions to validate and alerts, exits with a non-zero return code depending on the severity set. This feature can be used to determine pass/fail or alert on abnormalities observed in the cluster based on the metrics. 
- Kraken also provides ability to check if any critical alerts are firing in the cluster post chaos and pass/fail's. 

Information on enabling and leveraging this feature can be found [here](docs/SLOs_validation.md)


### OCM / ACM integration

Kraken supports injecting faults into [Open Cluster Management (OCM)](https://open-cluster-management.io/) and [Red Hat Advanced Cluster Management for Kubernetes (ACM)](https://www.krkn.com/en/technologies/management/advanced-cluster-management) managed clusters through [ManagedCluster Scenarios](docs/managedcluster_scenarios.md).


### Blogs and other useful resources
- Blog post on introduction to Kraken: https://www.openshift.com/blog/introduction-to-kraken-a-chaos-tool-for-openshift/kubernetes
- Discussion and demo on how Kraken can be leveraged to ensure OpenShift is reliable, performant and scalable: https://www.youtube.com/watch?v=s1PvupI5sD0&ab_channel=OpenShift
- Blog post emphasizing the importance of making Chaos part of Performance and Scale runs to mimic the production environments: https://www.openshift.com/blog/making-chaos-part-of-kubernetes/openshift-performance-and-scalability-tests
- Blog post on findings from Chaos test runs: https://cloud.redhat.com/blog/openshift/kubernetes-chaos-stories
- Discussion with CNCF TAG App Delivery on Krkn workflow, features and addition to CNCF sandbox: [Github](https://github.com/cncf/sandbox/issues/44), [Tracker](https://github.com/cncf/tag-app-delivery/issues/465), [recording](https://www.youtube.com/watch?v=nXQkBFK_MWc&t=722s)
- Blog post on supercharging chaos testing using AI integration in Krkn: https://www.redhat.com/en/blog/supercharging-chaos-testing-using-ai
- Blog post announcing Krkn joining CNCF Sandbox: https://www.redhat.com/en/blog/krknchaos-joining-cncf-sandbox

### Roadmap
Enhancements being planned can be found in the [roadmap](ROADMAP.md).


### Contributions
We are always looking for more enhancements, fixes to make it better, any contributions are most welcome. Feel free to report or work on the issues filed on github.

[More information on how to Contribute](docs/contribute.md)

If adding a new scenario or tweaking the main config, be sure to add in updates into the CI to be sure the CI is up to date.
Please read [this file]((CI/README.md#adding-a-test-case)) for more information on updates.


### Scenario Plugin Development

If you're gearing up to develop new scenarios, take a moment to review our 
[Scenario Plugin API Documentation](docs/scenario_plugin_api.md). 
It’s the perfect starting point to tap into your chaotic creativity!

### Community
Key Members(slack_usernames/full name): paigerube14/Paige Rubendall, mffiedler/Mike Fiedler, tsebasti/Tullio Sebastiani, yogi/Yogananth Subramanian, sahil/Sahil Shah, pradeep/Pradeep Surisetty and ravielluri/Naga Ravi Chaitanya Elluri.
* [**#krkn on Kubernetes Slack**](https://kubernetes.slack.com/messages/C05SFMHRWK1)

The Linux Foundation® (TLF) has registered trademarks and uses trademarks. For a list of TLF trademarks, see [Trademark Usage](https://www.linuxfoundation.org/legal/trademark-usage).
