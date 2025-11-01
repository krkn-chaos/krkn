import argparse
import json
import logging
import os.path
import re
import sys
import time
import yaml

# kraken module import for running the recommender
# both from the root directory and the recommender
# folder
sys.path.insert(0, "./")
sys.path.insert(0, "../../")

from krkn_lib.utils import get_yaml_item_value

import krkn.chaos_recommender.analysis as analysis
import krkn.chaos_recommender.prometheus as prometheus
from kubernetes import config as kube_config


def parse_arguments(parser):

    # command line options
    parser.add_argument("-c", "--config-file", action="store", help="Config file path")
    parser.add_argument(
        "-o", "--options", action="store_true", help="Evaluate command line options"
    )
    parser.add_argument(
        "-n",
        "--namespaces",
        action="store",
        default="",
        nargs="+",
        help="Kubernetes application namespaces separated by space",
    )
    parser.add_argument(
        "-p",
        "--prometheus-endpoint",
        action="store",
        default="",
        help="Prometheus endpoint URI",
    )
    parser.add_argument(
        "-k",
        "--kubeconfig",
        action="store",
        default=kube_config.KUBE_CONFIG_DEFAULT_LOCATION,
        help="Kubeconfig path",
    )
    parser.add_argument(
        "-t",
        "--token",
        action="store",
        default="",
        help="Kubernetes authentication token",
    )
    parser.add_argument(
        "-s",
        "--scrape-duration",
        action="store",
        default="10m",
        help="Prometheus scrape duration",
    )
    parser.add_argument(
        "-L",
        "--log-level",
        action="store",
        default="INFO",
        help="log level (DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    parser.add_argument(
        "-J",
        "--json-output-file",
        default=False,
        nargs="?",
        action="store",
        help="Create output file, the path to the folder can be specified, if not specified the default folder is used",
    )

    parser.add_argument(
        "-M",
        "--MEM",
        nargs="+",
        action="store",
        default=[],
        help="Memory related chaos tests (space separated list)",
    )
    parser.add_argument(
        "-C",
        "--CPU",
        nargs="+",
        action="store",
        default=[],
        help="CPU related chaos tests (space separated list)",
    )
    parser.add_argument(
        "-N",
        "--NETWORK",
        nargs="+",
        action="store",
        default=[],
        help="Network related chaos tests (space separated list)",
    )
    parser.add_argument(
        "-G",
        "--GENERIC",
        nargs="+",
        action="store",
        default=[],
        help="Memory related chaos tests (space separated list)",
    )
    parser.add_argument("--threshold", action="store", help="Threshold")
    parser.add_argument(
        "--cpu-threshold", action="store", help="CPU threshold"
    )
    parser.add_argument(
        "--mem-threshold", action="store", help="Memory threshold"
    )

    return parser.parse_args()


def read_configuration(config_file_path):
    if not os.path.exists(config_file_path):
        logging.error(f"Config file not found: {config_file_path}")
        sys.exit(1)

    with open(config_file_path, mode="r") as config_file:
        config = yaml.safe_load(config_file)

    log_level = config.get("log level", "INFO")
    namespaces = config.get("namespaces")
    namespaces = re.split(r",+\s+|,+|\s+", namespaces)
    kubeconfig = get_yaml_item_value(
        config, "kubeconfig", kube_config.KUBE_CONFIG_DEFAULT_LOCATION
    )

    prometheus_endpoint = config.get("prometheus_endpoint")
    auth_token = config.get("auth_token")
    scrape_duration = get_yaml_item_value(config, "scrape_duration", "10m")
    threshold = get_yaml_item_value(config, "threshold")
    heatmap_cpu_threshold = get_yaml_item_value(config, "cpu_threshold")
    heatmap_mem_threshold = get_yaml_item_value(config, "mem_threshold")
    output_file = config.get("json_output_file", False)
    if output_file is True:
        output_path = config.get("json_output_folder_path")
    else:
        output_path = False
    chaos_tests = config.get("chaos_tests", {})
    return (
        namespaces,
        kubeconfig,
        prometheus_endpoint,
        auth_token,
        scrape_duration,
        chaos_tests,
        log_level,
        threshold,
        heatmap_cpu_threshold,
        heatmap_mem_threshold,
        output_path,
    )


def prompt_input(prompt, default_value):
    user_input = input(f"{prompt} [{default_value}]: ")
    if user_input.strip():
        return user_input
    return default_value


def make_json_output(inputs, namespace_data, output_path):
    time_str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())

    data = {"inputs": inputs, "analysis_outputs": namespace_data}

    logging.info(f"Summary\n{json.dumps(data, indent=4)}")

    if output_path is not False:
        file = f"recommender_{time_str}.json"
        path = f"{os.path.expanduser(output_path)}/{file}"

        with open(path, "w") as json_output:
            logging.info(f"Saving output file in {output_path} folder...")
            json_output.write(json.dumps(data, indent=4))
            logging.info(f"Recommendation output saved in {file}.")


def json_inputs(
    namespaces,
    kubeconfig,
    prometheus_endpoint,
    scrape_duration,
    chaos_tests,
    threshold,
    heatmap_cpu_threshold,
    heatmap_mem_threshold,
):
    inputs = {
        "namespaces": namespaces,
        "kubeconfig": kubeconfig,
        "prometheus_endpoint": prometheus_endpoint,
        "scrape_duration": scrape_duration,
        "chaos_tests": chaos_tests,
        "threshold": threshold,
        "heatmap_cpu_threshold": heatmap_cpu_threshold,
        "heatmap_mem_threshold": heatmap_mem_threshold,
    }
    return inputs


def json_namespace(namespace, queries, analysis_data):
    data = {
        "namespace": namespace,
        "queries": queries,
        "profiling": analysis_data[0],
        "heatmap_analysis": analysis_data[1],
        "recommendations": analysis_data[2],
    }
    return data


def main():
    parser = argparse.ArgumentParser(description="Krkn Chaos Recommender Command-Line tool")
    args = parse_arguments(parser)

    if args.config_file is None and not args.options:
        logging.error(
            "You have to either specify a config file path or pass recommender options as command line arguments"
        )
        parser.print_help()
        sys.exit(1)

    try:
        if args.config_file is not None:
            (
                namespaces,
                kubeconfig,
                prometheus_endpoint,
                auth_token,
                scrape_duration,
                chaos_tests,
                log_level,
                threshold,
                heatmap_cpu_threshold,
                heatmap_mem_threshold,
                output_path,
            ) = read_configuration(args.config_file)
        else:
            namespaces = args.namespaces
            kubeconfig = args.kubeconfig
            auth_token = args.token
            scrape_duration = args.scrape_duration
            log_level = args.log_level
            prometheus_endpoint = args.prometheus_endpoint
            output_path = args.json_output_file
            chaos_tests = {
                "MEM": args.MEM,
                "GENERIC": args.GENERIC,
                "CPU": args.CPU,
                "NETWORK": args.NETWORK,
            }
            threshold = args.threshold
            heatmap_mem_threshold = args.mem_threshold
            heatmap_cpu_threshold = args.cpu_threshold

        if log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            logging.error(f"{log_level} not a valid log level")
            sys.exit(1)

        logging.basicConfig(level=log_level)

        if output_path is not False:
            if output_path is None:
                output_path = "./recommender_output"
                logging.info(
                    f"Path for output file not specified. "
                    f"Using default folder {output_path}"
                )
            if not os.path.exists(os.path.expanduser(output_path)):
                logging.error(f"Folder {output_path} for output not found.")
                sys.exit(1)

        # Validate required inputs
        if not namespaces:
            logging.error("No namespaces provided")
            sys.exit(1)
        if not prometheus_endpoint:
            logging.error("Prometheus endpoint is required")
            sys.exit(1)
        if not auth_token:
            logging.error("Auth token is required")
            sys.exit(1)

        logging.info("Loading inputs...")
        inputs = json_inputs(
            namespaces,
            kubeconfig,
            prometheus_endpoint,
            scrape_duration,
            chaos_tests,
            threshold,
            heatmap_cpu_threshold,
            heatmap_mem_threshold,
        )
        namespaces_data = []

        logging.info("Starting Analysis...")

        try:
            # Initialize Prometheus client and fetch utilization data
            file_path, queries = prometheus.fetch_utilization_from_prometheus(
                prometheus_endpoint, auth_token, namespaces, scrape_duration
            )
        except prometheus.PrometheusConnectionError as e:
            logging.error(f"Failed to connect to Prometheus at {prometheus_endpoint}: {str(e)}")
            sys.exit(1)
        except prometheus.PrometheusQueryError as e:
            logging.error(f"Failed to execute Prometheus queries: {str(e)}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Unexpected error while fetching Prometheus data: {str(e)}")
            sys.exit(1)

        try:
            analysis_data = analysis(
                file_path,
                namespaces,
                chaos_tests,
                threshold,
                heatmap_cpu_threshold,
                heatmap_mem_threshold,
            )
        except Exception as e:
            logging.error(f"Failed to analyze data: {str(e)}")
            sys.exit(1)

        try:
            for namespace in namespaces:
                namespace_data = json_namespace(
                    namespace, queries[namespace], analysis_data[namespace]
                )
                namespaces_data.append(namespace_data)
        except KeyError as e:
            logging.error(f"Failed to process namespace data: {str(e)}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Unexpected error while processing namespace data: {str(e)}")
            sys.exit(1)

        try:
            make_json_output(inputs, namespaces_data, output_path)
        except Exception as e:
            logging.error(f"Failed to create JSON output: {str(e)}")
            sys.exit(1)

    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
