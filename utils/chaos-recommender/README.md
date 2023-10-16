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
    python3 chaos-recommender.py
    ```

2. Follow the prompts to provide the required information.

## Configuration

You can customize the default values by editing the `config.ini` file. The configuration file contains the following options:

- `[General]`
  - `application`: Specify the application name.
  - `namespace`: Specify the namespace name. If you want to profile
  - `labels`: Specify the labels (not used).
  - `kubeconfig`: Specify the location of the kubeconfig file (not used).

- `[Options]`
  - `prometheus_endpoint`: Specify the prometheus endpoint (must).
  - `auth_token`: Auth token to connect to prometheus endpoint (must).
  - `scrape_duration`: For how long data should be fetched, e.g., '1m' (must).
  - `chaos_library`: "kraken" (currently it only supports kraken). One can make modifications in kraken_chaos_tests.txt though.

You can also provide the input values through command-line arguments. The following options are available:

- `-p`, `--prompt`: Prompt all options on console.

If you provide the input values through command-line arguments, the corresponding config file inputs would be ignored.

## Docker 

To run chaos recommendation to via Docker. please follow the steps below. 

- Build a docker image  `make build`
- Run the tool `make run`  or alternatively `docker run -it --rm <IMAGE_NAME:TAG> python3 chaos-recommender.py -p`

PS: Please note that either one should provide populated config.ini during the image build, or use -p flag to ask for a prompt when running in docker. 

## How it works

After obtaining telemetry data, sourced either locally or from Prometheus, the tool conducts a comprehensive data analysis to detect anomalies. Employing the Z-score method and heatmaps, it identifies outliers by evaluating CPU, memory, and network usage against established limits. Services with Z-scores surpassing a specified threshold are categorized as outliers. This categorization classifies services as network, CPU, or memory-sensitive, consequently leading to the recommendation of relevant test cases.

## Customizing Thresholds and Options

You can customize the thresholds and options used for data analysis by modifying the `analysis.py` file. For example, you can adjust the threshold for identifying outliers by changing the value of the `threshold` variable in the `identify_outliers` function.

## Additional Files

- `config.ini`: The configuration file containing default values for application, namespace, labels, and kubeconfig.
- `requirements.txt`: The file listing the required dependencies for the project.
- `Dockerfile`: The Dockerfile used to build the Docker image for the project.
- `Makefile`: The file containing commands to build and run the project using `make`.

Happy Chaos!
