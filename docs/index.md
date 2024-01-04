## Chaos Testing Guide


### Table of Contents
* [Introduction](#introduction)
* [Test Stratagies and Methodology](#test-strategies-and-methodology)
* [Best Practices](#best-practices)
* [Tooling](#tooling)
  * [Workflow](#workflow)
  * [Cluster recovery checks, metrics evaluation and pass/fail criteria](#cluster-recovery-checks-metrics-evaluation-and-passfail-criteria)
* [Scenarios](#scenarios)
* [Test Environment Recommendations - how and where to run chaos tests](#test-environment-recommendations---how-and-where-to-run-chaos-tests)
* [Chaos testing in Practice](#chaos-testing-in-practice)
  * [OpenShift oraganization](#openshift-organization)
  * [startx-lab](#startx-lab)


### Introduction
There are a couple of false assumptions that users might have when operating and running their applications in distributed systems:

The network is reliable.
There is zero latency.
Bandwidth is infinite.
The network is secure.
Topology never changes.
The network is homogeneous.
Consistent resource usage with no spikes.
All shared resources are available from all places.

Various assumptions led to a number of outages in production environments in the past.  The services suffered from poor performance or were inaccessible to the customers, leading to missing Service Level Agreement uptime promises, revenue loss, and a degradation in the perceived reliability of said services.

How can we best avoid this from happening? This is where Chaos testing can add value.



### Test Strategies and Methodology
Failures in production are costly. To help mitigate risk to service health, consider the following strategies and approaches to service testing:

- Be proactive vs reactive. We have different types of test suites in place - unit, integration and end-to-end - that help expose bugs in code in a controlled environment.  Through implementation of a chaos engineering strategy, we can discover potential causes of service degradation. We need to understand the systems' behavior under unpredictable conditions in order to find the areas to harden, and use performance data points to size the clusters to handle failures in order to keep downtime to a minimum.

- Test the resiliency of a system under turbulent conditions by running tests that are designed to disrupt while monitoring the systems adaptability and performance:
  - Establish and define your steady state and metrics - understand the behavior and performance under stable conditions and define the metrics that will be used to evaluate the system’s behavior.  Then decide on acceptable outcomes before injecting chaos.
  - Analyze the statuses and metrics of all components during the chaos test runs.
  - Improve the areas that are not resilient and performant by comparing the key metrics and Service Level Objectives (SLOs) to the stable conditions before the chaos.
  For example: evaluating the API server latency or application uptime to see if the key performance indicators and service level indicators are still within acceptable limits.




### Best Practices
Now that we understand the test methodology, let us take a look at the best practices for an Kubernetes cluster.  On that platform there are user applications and cluster workloads that need to be designed for stability and to provide the best user experience possible:

- Alerts with appropriate severity should get fired.
  - Alerts are key to identify when a component starts degrading, and can help focus the investigation effort on affected system components.
  - Alerts should have proper severity, description, notification policy, escalation policy, and SOP in order to reduce MTTR for responding SRE or Ops resources.
  - Detailed information on the alerts consistency can be found [here](https://github.com/openshift/enhancements/blob/master/enhancements/monitoring/alerting-consistency.md).

- Minimal performance impact - Network, CPU, Memory, Disk, Throughput etc.
  - The system, as well as the applications, should be designed to have minimal performance impact during disruptions to ensure stability and also to avoid hogging resources that other applications can use.
We want to look at this in terms of CPU, Memory, Disk, Throughput, Network etc.
  - We want to look at this in terms of CPU, Memory, Disk, Throughput, Network etc.

- Appropriate CPU/Memory limits set to avoid performance throttling and OOM kills.
  - There might be rogue applications hogging resources ( CPU/Memory ) on the nodes which might lead to applications underperforming or worse getting OOM killed. It is important to ensure that applications and system components have reserved resources for the kube-scheduler to take into consideration in order to keep them performing at the expected levels.

- Services dependent on the system under test need to handle the failure gracefully to avoid performance degradation and downtime - appropriate timeouts.
  - In a distributed system, services deployed coordinate with each other and might have external dependencies. Each of the services deployed as a deployment, pod, or container, need to handle the downtime of other dependent services gracefully instead of crashing due to not having appropriate timeouts, fallback logic etc.

- Proper node sizing to avoid cascading failures and ensure cluster stability especially when the cluster is large and dense
  - The platform needs to be sized taking into account the resource usage spikes that might occur during chaotic events. For example, if one of the main nodes goes down, the other two main nodes need to have enough resources to handle the load. The resource usage depends on the load or number of objects that are running being managed by the Control Plane ( Api Server, Etcd, Controller and Scheduler ). As such, it’s critical to test such conditions, understand the behavior, and leverage the data to size the platform appropriately. This can help keep the applications stable during unplanned events without the control plane undergoing cascading failures which can potentially bring down the entire cluster.

- Proper node sizing to avoid application failures and maintain stability.
  - An application pod might use more resources during reinitialization after a crash, so it is important to take that into account for sizing the nodes in the cluster to accommodate it. For example, monitoring solutions like Prometheus need high amounts of memory to replay the write ahead log ( WAL ) when it restarts. As such, it’s critical to test such conditions, understand the behavior, and leverage the data to size the platform appropriately. This can help keep the application stable during unplanned events without undergoing degradation in performance or even worse hog the resources on the node which can impact other applications and system pods.


- Minimal initialization time and fast recovery logic.
  - The controller watching the component should recognize a failure as soon as possible. The component needs to have minimal initialization time to avoid extended downtime or overloading the replicas if it is a highly available configuration. The cause of failure can be because of issues with the infrastructure on top of which it is running, application failures, or because of service failures that it depends on.

- High Availability deployment strategy.
  - There should be multiple replicas ( both Kubernetes and application control planes ) running preferably in different availability zones to survive outages while still serving the user/system requests. Avoid single points of failure.
- Backed by persistent storage
  - It is important to have the system/application backed by persistent storage. This is especially important in cases where the application is a database or a stateful application given that a node, pod, or container failure will wipe off the data.

- There should be fallback routes to the backend in case of using CDN, for example, Akamai in case of console.redhat.com - a managed service deployed on top of Kubernetes dedicated:
  - Content delivery networks (CDNs) are commonly used to host resources such as images, JavaScript files, and CSS. The average web page is nearly 2 MB in size, and offloading heavy resources to third-parties is extremely effective for reducing backend server traffic and latency. However, this makes each CDN an additional point of failure for every site that relies on it. If the CDN fails, its customers could also fail.
  - To test how the application reacts to failures, drop all network traffic between the system and CDN. The application should still serve the content to the user irrespective of the failure.

- Appropriate caching and Content Delivery Network should be enabled to be performant and usable when there is a latency on the client side.
  - Not every user or machine has access to unlimited bandwidth, there might be a delay on the user side ( client ) to access the API’s due to limited bandwidth, throttling or latency depending on the geographic location. It is important to inject latency between the client and API calls to understand the behavior and optimize things including caching wherever possible, using CDN’s or opting for different protocols like HTTP/2 or HTTP/3 vs HTTP.




### Tooling
Now that we looked at the best practices, In this section, we will go through how [Kraken](https://github.com/redhat-chaos/krkn) - a chaos testing framework can help test the resilience of Kubernetes and make sure the applications and services are following the best practices.

#### Workflow
Let us start by understanding the workflow of kraken: the user will start by running kraken by pointing to a specific Kubernetes cluster using kubeconfig to be able to talk to the platform on top of which the Kubernetes cluster is hosted. This can be done by either the oc/kubectl API or the cloud API. Based on the configuration of kraken, it will inject specific chaos scenarios as shown below, talk to [Cerberus](https://github.com/redhat-chaos/cerberus) to get the go/no-go signal representing the overall health of the cluster ( optional - can be turned off ), scrapes metrics from in-cluster prometheus given a metrics profile with the promql queries and stores them long term in Elasticsearch configured  ( optional - can be turned off ), evaluates the promql expressions specified in the alerts profile ( optional - can be turned off ) and aggregated everything to set the pass/fail i.e. exits 0 or 1. More about the metrics collection, cerberus and metrics evaluation can be found in the next section.

![Kraken workflow](../media/kraken-workflow.png)

#### Cluster recovery checks, metrics evaluation and pass/fail criteria
- Most of the scenarios have built in checks to verify if the targeted component recovered from the failure after the specified duration of time but there might be cases where other components might have an impact because of a certain failure and it’s extremely important to make sure that the system/application is healthy as a whole post chaos. This is exactly where [Cerberus](https://github.com/redhat-chaos/cerberus) comes to the rescue.
If the monitoring tool, cerberus is enabled it will consume the signal and continue running chaos or not based on that signal.

- Apart from checking the recovery and cluster health status, it’s equally important to evaluate the performance metrics like latency, resource usage spikes, throughput, etcd health like disk fsync, leader elections etc. To help with this, Kraken has a way to evaluate promql expressions from the incluster prometheus and set the exit status to 0 or 1 based on the severity set for each of the query. Details on how to use this feature can be found [here](https://github.com/redhat-chaos/krkn#alerts).

- The overall pass or fail of kraken is based on the recovery of the specific component (within a certain amount of time), the cerberus health signal which tracks the health of the entire cluster and metrics evaluation from incluster prometheus.




### Scenarios

Let us take a look at how to run the chaos scenarios on your Kubernetes clusters using Kraken-hub - a lightweight wrapper around Kraken to ease the runs by providing the ability to run them by just running container images using podman with parameters set as environment variables. This eliminates the need to carry around and edit configuration files and makes it easy for any CI framework integration. Here are the scenarios supported:

- Pod Scenarios ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/pod-scenarios.md))
  - Disrupts Kubernetes/Kubernetes and applications deployed as pods:
    - Helps understand the availability of the application, the initialization timing and recovery status.
  - [Demo](https://asciinema.org/a/452351?speed=3&theme=solarized-dark)

- Container Scenarios ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/container-scenarios.md))
  - Disrupts Kubernetes/Kubernetes and applications deployed as containers running as part of a pod(s) using a specified kill signal to mimic failures:
    - Helps understand the impact and recovery timing when the program/process running in the containers are disrupted - hangs, paused, killed etc., using various kill signals, i.e. SIGHUP, SIGTERM, SIGKILL etc.
  - [Demo](https://asciinema.org/a/BXqs9JSGDSEKcydTIJ5LpPZBM?speed=3&theme=solarized-dark)

- Node Scenarios ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/node-scenarios.md))
  - Disrupts nodes as part of the cluster infrastructure by talking to the cloud API. AWS, Azure, GCP, OpenStack and Baremetal are the supported platforms as of now. Possible disruptions include:
    - Terminate nodes
    - Fork bomb inside the node
    - Stop the node
    - Crash the kubelet running on the node
    - etc.
  - [Demo](https://asciinema.org/a/ANZY7HhPdWTNaWt4xMFanF6Q5)

- Zone Outages ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/zone-outages.md))
  - Creates outage of availability zone(s) in a targeted region in the public cloud where the Kubernetes cluster is running by tweaking the network acl of the zone to simulate the failure, and that in turn will stop both ingress and egress traffic from all nodes in a particular zone for the specified duration and reverts it back to the previous state.
    - Helps understand the impact on both Kubernetes/Kubernetes control plane as well as applications and services running on the worker nodes in that zone.
    - Currently, only set up for AWS cloud platform: 1 VPC and multiples subnets within the VPC can be specified.
    - [Demo](https://asciinema.org/a/452672?speed=3&theme=solarized-dark)

- Application Outages ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/application-outages.md))
  - Scenario to block the traffic ( Ingress/Egress ) of an application matching the labels for the specified duration of time to understand the behavior of the service/other services which depend on it during the downtime.
    - Helps understand how the dependent services react to the unavailability.
    - [Demo](https://asciinema.org/a/452403?speed=3&theme=solarized-dark)

- Power Outages ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/power-outages.md))
  - This scenario imitates a power outage by shutting down of the entire cluster for a specified duration of time, then restarts all the nodes after the specified time and checks the health of the cluster.
    - There are various use cases in the customer environments. For example, when some of the clusters are shutdown in cases where the applications are not needed to run in a particular time/season in order to save costs.
    - The nodes are stopped in parallel to mimic a power outage i.e., pulling off the plug
  - [Demo](https://asciinema.org/a/r0zLbh70XK7gnc4s5v0ZzSXGo)

- Resource Hog
  - Hogs CPU, Memory and IO on the targeted nodes
    - Helps understand if the application/system components have reserved resources to not get disrupted because of rogue applications, or get performance throttled.
      - CPU Hog ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/node-cpu-hog.md), [Demo](https://asciinema.org/a/452762))
      - Memory Hog ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/node-memory-hog.md), [Demo](https://asciinema.org/a/452742?speed=3&theme=solarized-dark))

- Time Skewing ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/time-scenarios.md))
  - Manipulate the system time and/or date of specific pods/nodes.
    - Verify scheduling of objects so they continue to work.
    - Verify time gets reset properly.

- Namespace Failures ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/namespace-scenarios.md))
  - Delete namespaces for the specified duration.
    - Helps understand the impact on other components and tests/improves recovery time of the components in the targeted namespace.

- Persistent Volume Fill ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/pvc-scenarios.md))
  - Fills up the persistent volumes, up to a given percentage, used by the pod for the specified duration.
    - Helps understand how an application deals when it is no longer able to write data to the disk. For example, kafka’s behavior when it is not able to commit data to the disk.

- Network Chaos ([Documentation](https://github.com/redhat-chaos/krkn-hub/blob/main/docs/network-chaos.md))
  - Scenarios supported includes:
    - Network latency
    - Packet loss
    - Interface flapping
    - DNS errors
    - Packet corruption
    - Bandwidth limitation




### Test Environment Recommendations - how and where to run chaos tests

Let us take a look at few recommendations on how and where to run the chaos tests:

- Run the chaos tests continuously in your test pipelines:
  - Software, systems, and infrastructure does change – and the condition/health of each can change pretty rapidly. A good place to run tests is in your CI/CD pipeline running on a regular cadence.

- Run the chaos tests manually to learn from the system:
  - When running a Chaos scenario or Fault tests, it is more important to understand how the system responds and reacts, rather than mark the execution as pass or fail.
  - It is important to define the scope of the test before the execution to avoid some issues from masking others.

- Run the chaos tests in production environments or mimic the load in staging environments:
  - As scary as a thought about testing in production is, production is the environment that users are in and traffic spikes/load are real. To fully test the robustness/resilience of a production system, running Chaos Engineering experiments in a production environment will provide needed insights. A couple of things to keep in mind:
    - Minimize blast radius and have a backup plan in place to make sure the users and customers do not undergo downtime.
    - Mimic the load in a staging environment in case Service Level Agreements  are too tight to cover any downtime.

- Enable Observability:
  - Chaos Engineering Without Observability ... Is Just Chaos.
  - Make sure to have logging and monitoring installed on the cluster to help with understanding the behaviour as to why it is happening. In case of running the tests in the CI where it is not humanly possible to monitor the cluster all the time, it is recommended to leverage Cerberus to capture the state during the runs and metrics collection in Kraken to store metrics long term even after the cluster is gone.
  - Kraken ships with dashboards that will help understand API, Etcd and Kubernetes cluster level stats and performance metrics.
  - Pay attention to Prometheus alerts. Check if they are firing as expected.

- Run multiple chaos tests at once to mimic the production outages:
  - For example, hogging both IO and Network at the same time instead of running them separately to observe the impact.
  - You might have existing test cases, be it related to Performance, Scalability or QE. Run the chaos in the background during the test runs to observe the impact. Signaling feature in Kraken can help with coordinating the chaos runs i.e., start, stop, pause the scenarios based on the state of the other test jobs.


#### Chaos testing in Practice

##### OpenShift organization
Within the OpenShift organization we use kraken to perform chaos testing throughout a release before the code is available to customers.

    1. We execute kraken during our regression test suite.

        i. We cover each of the chaos scenarios across different clouds.

            a. Our testing is predominantly done on AWS, Azure and GCP.

    2. We run the chaos scenarios during a long running reliability test.

        i. During this test we perform different types of tasks by different users on the cluster.

        ii. We have added the execution of kraken to perform at certain times throughout the long running test and monitor the health of the cluster.

        iii. This test can be seen here: https://github.com/openshift/svt/tree/master/reliability-v2

    3. We are starting to add in test cases that perform chaos testing during an upgrade (not many iterations of this have been completed).


##### startx-lab

**NOTE**: Requests for enhancements and any issues need to be filed at the mentioned links given that they are not natively supported in Kraken.

The following content covers the implementation details around how Startx is leveraging Kraken:

* Using kraken as part of a tekton pipeline

You can find on [artifacthub.io](https://artifacthub.io/packages/search?kind=7&ts_query_web=kraken) the 
[kraken-scenario](https://artifacthub.io/packages/tekton-task/startx-tekton-catalog/kraken-scenario) `tekton-task`
which can be used to start a kraken chaos scenarios as part of a chaos pipeline.

To use this task, you must have :

  - Openshift pipeline enabled (or tekton CRD loaded for Kubernetes clusters)
  - 1 Secret named `kraken-aws-creds` for scenarios using aws
  - 1 ConfigMap named `kraken-kubeconfig` with credentials to the targeted cluster
  - 1 ConfigMap named `kraken-config-example` with kraken configuration file (config.yaml)
  - 1 ConfigMap named `kraken-common-example` with all kraken related files
  - The `pipeline` SA with be autorized to run with priviveged SCC

You can create theses resources using the following sequence :

```bash
oc project default
oc adm policy add-scc-to-user privileged -z pipeline
oc apply -f https://github.com/startxfr/tekton-catalog/raw/stable/task/kraken-scenario/0.1/samples/common.yaml
```

Then you must change content of `kraken-aws-creds` secret, `kraken-kubeconfig` and `kraken-config-example` configMap
to reflect your cluster configuration. Refer to the [kraken configuration](https://github.com/redhat-chaos/krkn/blob/main/config/config.yaml)
and [configuration examples](https://github.com/startxfr/tekton-catalog/blob/stable/task/kraken-scenario/0.1/samples/) 
for details on how to configure theses resources.

* Start as a single taskrun

```bash
oc apply -f https://github.com/startxfr/tekton-catalog/raw/stable/task/kraken-scenario/0.1/samples/taskrun.yaml
```

* Start as a pipelinerun

```yaml
oc apply -f https://github.com/startxfr/tekton-catalog/raw/stable/task/kraken-scenario/0.1/samples/pipelinerun.yaml
```

* Deploying kraken using a helm-chart

You can find on [artifacthub.io](https://artifacthub.io/packages/search?kind=0&ts_query_web=kraken) the
[chaos-kraken](https://artifacthub.io/packages/helm/startx/chaos-kraken) `helm-chart`
which can be used to deploy a kraken chaos scenarios.

Default configuration create the following resources :

  - 1 project named **chaos-kraken**
  - 1 scc with privileged context for kraken deployment
  - 1 configmap with kraken 21 generic scenarios, various scripts and configuration
  - 1 configmap with kubeconfig of the targeted cluster
  - 1 job named kraken-test-xxx
  - 1 service to the kraken pods
  - 1 route to the kraken service

```bash
# Install the startx helm repository
helm repo add startx https://startxfr.github.io/helm-repository/packages/
# Install the kraken project
helm install --set project.enabled=true chaos-kraken-project  startx/chaos-kraken
# Deploy the kraken instance
helm install \
--set kraken.enabled=true \
--set kraken.aws.credentials.region="eu-west-3" \
--set kraken.aws.credentials.key_id="AKIAXXXXXXXXXXXXXXXX" \
--set kraken.aws.credentials.secret="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
--set kraken.kubeconfig.token.server="https://api.mycluster:6443" \
--set kraken.kubeconfig.token.token="sha256~XXXXXXXXXX_PUT_YOUR_TOKEN_HERE_XXXXXXXXXXXX" \
-n chaos-kraken \
chaos-kraken-instance startx/chaos-kraken
```
