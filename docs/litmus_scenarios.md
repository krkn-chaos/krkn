### Litmus Scenarios
Kraken consumes [Litmus](https://github.com/litmuschaos/litmus) under the hood for some infrastructure, pod, and node scenarios

Official Litmus documentation and to read more information on specifics of Litmus resources can be found [here](https://docs.litmuschaos.io/docs/next/getstarted/)


#### Litmus Chaos Custom Resources
There are 3 custom resources that are created during each Litmus scenario. Below is a description of the resources:
* ChaosEngine: A resource to link a Kubernetes application or Kubernetes node to a ChaosExperiment. ChaosEngine is watched by Litmus' Chaos-Operator which then invokes Chaos-Experiments
* ChaosExperiment: A resource to group the configuration parameters of a chaos experiment. ChaosExperiment CRs are created by the operator when experiments are invoked by ChaosEngine.
* ChaosResult : A resource to hold the results of a chaos-experiment. The Chaos-exporter reads the results and exports the metrics into a configured Prometheus server.

### Understanding Litmus Scenarios

To run Litmus scenarios we need to apply 3 different resources/yaml files to our cluster
1. **Chaos experiments** contain the actual chaos details of a scenario

    i. This is installed automatically by Kraken (does not need to be specified in kraken scenario configuration)

2. **Service Account**: should be created to allow chaosengine to run experiments in your application namespace. Usually sets just enough permissions to a specific namespace to be able to run the experiment properly

    i. This can be defined using either a link to a yaml file or a downloaded file in the scenarios folder

3. **Chaos Engine** connects the application instance to a Chaos Experiment. This is where you define the specifics of your scenario; ie: the node or pod name you want to cause chaos within

    i. This is a downloaded yaml file in the scenarios folder, full list of scenarios can be found [here](https://hub.litmuschaos.io/)

**NOTE**: By default all chaos experiments will be installed based on the version you give in the config file.

Adding a new Litmus based scenario is as simple as adding references to 2 new yaml files (the Service Account and Chaos engine files for your scenario ) in the Kraken config.

### Current Scenarios

Following are the start of scenarios for which a chaos scenario config exists today.

Component                | Description                                                                                        | Working
------------------------ | ---------------------------------------------------------------------------------------------------| ------------------------- |
Node CPU Hog             | Chaos scenario that hogs up the CPU on a defined node for a specific amount of time                | :heavy_check_mark:        |
