# Chaos Recommendation Tool

This tool, designed for Redhat Kraken, operates through the command line and offers recommendations for chaos testing. It suggests probable chaos test cases that can disrupt application services by analyzing their behavior and assessing their susceptibility to specific fault types.

This tool profiles an application and gathers telemetry data such as CPU, Memory, and Network usage, analyzing it to suggest probable chaos scenarios. For optimal results, it is recommended to activate the utility while the application is under load.

## Pre-requisites

- Openshift Or Kubernetes Environment where the application is hosted
- Access to the telemetry data via the exposed Prometheus endpoint
- Python3

## Usage

1. To run

    ```
    $ python3.9 -m venv chaos
    $ source chaos/bin/activate
    $ git clone https://github.com/krkn-chaos/krkn.git 
    $ cd krkn
    $ pip3 install -r requirements.txt
    Edit configuration file:
    $ vi config/recommender_config.yaml 
    $ python3.9 utils/chaos_recommender/chaos_recommender.py
    ```

2. Follow the prompts to provide the required information.

## Configuration
To run the recommender with a config file specify the config file path with the `-c` argument.
You can customize the default values by editing the `krkn/config/recommender_config.yaml` file. The configuration file contains the following options:

  - `application`: Specify the application name.
  - `namespace`: Specify the namespace name. If you want to profile
  - `labels`: Specify the labels (not used).
  - `kubeconfig`: Specify the location of the kubeconfig file (not used).
  - `prometheus_endpoint`: Specify the prometheus endpoint (must).
  - `auth_token`: Auth token to connect to prometheus endpoint (must).
  - `scrape_duration`: For how long data should be fetched, e.g., '1m' (must).
  - `chaos_library`: "kraken" (currently it only supports kraken).
  - `json_output_file`: True or False (by default False).
  - `json_output_folder_path`: Specify folder path where output should be saved. If empty the default path is used.
  - `chaos_tests`: (for output purpose only do not change if not needed)
    - `GENERAL`: list of general purpose tests available in Krkn
    - `MEM`: list of memory related tests available in Krkn
    - `NETWORK`: list of network related tests available in Krkn
    - `CPU`: list of memory related tests available in Krkn
  - `threshold`: Specify the threshold to use for comparison and identifying outliers
  - `cpu_threshold`: Specify the cpu threshold to compare with the cpu limits set on the pods and identify outliers
  - `mem_threshold`: Specify the memory threshold to compare with the memory limits set on the pods and identify outliers

*TIP:* to collect prometheus endpoint and token from your OpenShift cluster you can run the following commands:
        ```
         prometheus_url=$(kubectl get routes -n openshift-monitoring prometheus-k8s --no-headers | awk '{print $2}')
         #TO USE YOUR CURRENT SESSION TOKEN
         token=$(oc whoami -t)
         #TO CREATE A NEW TOKEN
         token=$(kubectl create token -n openshift-monitoring prometheus-k8s --duration=6h || oc sa new-token -n openshift-monitoring prometheus-k8s)
        ```

You can also provide the input values through command-line arguments launching the recommender with `-o` option:

```
  -o, --options         Evaluate command line options
  -a APPLICATION, --application APPLICATION
                        Kubernetes application name
  -n NAMESPACE, --namespace NAMESPACE
                        Kubernetes application namespace
  -l LABELS, --labels LABELS
                        Kubernetes application labels
  -p PROMETHEUS_ENDPOINT, --prometheus-endpoint PROMETHEUS_ENDPOINT
                        Prometheus endpoint URI
  -k KUBECONFIG, --kubeconfig KUBECONFIG
                        Kubeconfig path
  -t TOKEN, --token TOKEN
                        Kubernetes authentication token
  -s SCRAPE_DURATION, --scrape-duration SCRAPE_DURATION
                        Prometheus scrape duration
  -i LIBRARY, --library LIBRARY
                        Chaos library
  -L LOG_LEVEL, --log-level LOG_LEVEL
                        log level (DEBUG, INFO, WARNING, ERROR, CRITICAL
  -J [FOLDER_PATH], --json-output-file [FOLDER_PATH]
                        Create output file, the path to the folder can be specified, if not specified the default folder is used.
  -M MEM [MEM ...], --MEM MEM [MEM ...]
                        Memory related chaos tests (space separated list)
  -C CPU [CPU ...], --CPU CPU [CPU ...]
                        CPU related chaos tests (space separated list)
  -N NETWORK [NETWORK ...], --NETWORK NETWORK [NETWORK ...]
                        Network related chaos tests (space separated list)
  -G GENERIC [GENERIC ...], --GENERIC GENERIC [GENERIC ...]
                        Memory related chaos tests (space separated list)
  --threshold THRESHOLD
                        Threshold
  --cpu_threshold CPU_THRESHOLD
                        CPU threshold to compare with the cpu limits
  --mem_threshold MEM_THRESHOLD
                        Memory threshold to compare with the memory limits
```

If you provide the input values through command-line arguments, the corresponding config file inputs would be ignored.

## Podman & Docker image

To run the recommender image please visit the [krkn-hub](https://github.com/krkn-chaos/krkn-hub for further infos.

## How it works

After obtaining telemetry data, sourced either locally or from Prometheus, the tool conducts a comprehensive data analysis to detect anomalies. Employing the Z-score method and heatmaps, it identifies outliers by evaluating CPU, memory, and network usage against established limits. Services with Z-scores surpassing a specified threshold are categorized as outliers. This categorization classifies services as network, CPU, or memory-sensitive, consequently leading to the recommendation of relevant test cases.

## Customizing Thresholds and Options

You can customize the thresholds and options used for data analysis and identifying the outliers by setting the threshold, cpu_threshold and mem_threshold parameters in the config.

## Additional Files

- `config/recommender_config.yaml`: The configuration file containing default values for application, namespace, labels, and kubeconfig.

Happy Chaos!
