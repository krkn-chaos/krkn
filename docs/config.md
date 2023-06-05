### Config
Set the scenarios to inject and the tunings like duration to wait between each scenario in the config file located at [config/config.yaml](https://github.com/redhat-chaos/krkn/blob/main/config/config.yaml).

**NOTE**: [config](https://github.com/redhat-chaos/krkn/blob/main/config/config_performance.yaml) can be used if leveraging the [automated way](https://github.com/redhat-chaos/krkn#setting-up-infrastructure-dependencies) to install the infrastructure pieces.

Config components: 
* [Kraken](#kraken)
* [Cerberus](#cerberus)
* [Performance Monitoring](#performance-monitoring)
* [Tunings](#tunings)

# Kraken 
This section defines scenarios and specific data to the chaos run 

## Distribution
Either **openshift** or **kubernetes** depending on the type of cluster you want to run chaos on. 
The prometheus url/route and bearer token are automatically obtained in case of OpenShift, please set it when the distribution is Kubernetes.

## Exit on failure
**exit_on_failure**:  Exit when a post action check or cerberus run fails

## Publish kraken status
**publish_kraken_status**: Can be accessed at http://0.0.0.0:8081 (or what signal_address and port you set in signal address section)
**signal_state**: State you want kraken to start at; will wait for the RUN signal to start running a chaos iteration. When set to PAUSE before running the scenarios, refer to [signal.md](signal.md) for more details

## Signal Address 
**signal_address**: Address to listen/post the signal state to
**port**: port to listen/post the signal state to

## Chaos Scenarios 

**chaos_scenarios**: List of different types of chaos scenarios you want to run with paths to their specific yaml file configurations

If a scenario has a post action check script, it will be run before and after each scenario to validate the component under test starts and ends at the same state

Currently the scenarios are run one after another (in sequence) and will exit if one of the scenarios fail, without moving onto the next one

Chaos scenario types: 
- container_scenarios     
- plugin_scenarios
- node_scenarios
- time_scenarios
- cluster_shut_down_scenarios
- namespace_scenarios
- zone_outages
- application_outages
- pvc_scenarios
- network_chaos


# Cerberus 
Parameters to set for enabling of cerberus checks at the end of each executed scenario. The given url will pinged after the scenario and post action check have been completed for each scenario and iteration.
**cerberus_enabled**: Enable it when cerberus is previously installed
**cerberus_url**: When cerberus_enabled is set to True, provide the url where cerberus publishes go/no-go signal
**check_applicaton_routes**:  When enabled will look for application unavailability using the routes specified in the cerberus config and fails the run


# Performance Monitoring 
There are 2 main sections defined in this part of the config [metrics](metrics.md) and [alerts](alerts.md); read more about each of these configurations in their respective docs 

# Tunings
**wait_duration**: Duration to wait between each chaos scenario
**iterations**: Number of times to execute the scenarios
**daemon_mode**: True or False; If true, iterations are set to infinity which means that the kraken will cause chaos forever and number of iterations is ignored

