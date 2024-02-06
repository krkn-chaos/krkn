import argparse
import json
import logging
import os.path
import sys
import time
import yaml
# kraken module import for running the recommender
# both from the root directory and the recommender
# folder
sys.path.insert(0, './')
sys.path.insert(0, '../../')

from krkn_lib.utils import get_yaml_item_value

import kraken.chaos_recommender.analysis as analysis
import kraken.chaos_recommender.prometheus as prometheus
from kubernetes import config as kube_config


def parse_arguments(parser):

    # command line options
    parser.add_argument("-c", "--config-file", action="store", help="Config file path")
    parser.add_argument("-o", "--options", action="store_true", help="Evaluate command line options")
    parser.add_argument("-n", "--namespace", action="store", default="", help="Kubernetes application namespace")
    parser.add_argument("-p", "--prometheus-endpoint", action="store", default="", help="Prometheus endpoint URI")
    parser.add_argument("-k", "--kubeconfig", action="store", default=kube_config.KUBE_CONFIG_DEFAULT_LOCATION, help="Kubeconfig path")
    parser.add_argument("-t", "--token", action="store", default="", help="Kubernetes authentication token")
    parser.add_argument("-s", "--scrape-duration", action="store", default="10m", help="Prometheus scrape duration")
    parser.add_argument("-L", "--log-level", action="store", default="INFO", help="log level (DEBUG, INFO, WARNING, ERROR, CRITICAL")

    parser.add_argument("-J", "--json-output-file", default=False, nargs="?", action="store",
                        help="Create output file, the path to the folder can be specified, if not specified the default folder is used")

    parser.add_argument("-M", "--MEM", nargs='+', action="store", default=[],
                        help="Memory related chaos tests (space separated list)")
    parser.add_argument("-C", "--CPU", nargs='+', action="store", default=[],
                        help="CPU related chaos tests (space separated list)")
    parser.add_argument("-N", "--NETWORK", nargs='+', action="store", default=[],
                        help="Network related chaos tests (space separated list)")
    parser.add_argument("-G", "--GENERIC", nargs='+', action="store", default=[],
                        help="Memory related chaos tests (space separated list)")
    parser.add_argument("--threshold", action="store", default="", help="Threshold")
    parser.add_argument("--cpu-threshold", action="store", default="", help="CPU threshold")
    parser.add_argument("--mem-threshold", action="store", default="", help="Memory threshold")

    return parser.parse_args()


def read_configuration(config_file_path):
    if not os.path.exists(config_file_path):
        logging.error(f"Config file not found: {config_file_path}")
        sys.exit(1)

    with open(config_file_path, mode="r") as config_file:
        config = yaml.safe_load(config_file)

    log_level = config.get("log level", "INFO")
    namespace = config.get("namespace")
    kubeconfig = get_yaml_item_value(config, "kubeconfig", kube_config.KUBE_CONFIG_DEFAULT_LOCATION)

    prometheus_endpoint = config.get("prometheus_endpoint")
    auth_token = config.get("auth_token")
    scrape_duration = get_yaml_item_value(config, "scrape_duration", "10m")
    threshold = get_yaml_item_value(config, "threshold", ".7")
    heatmap_cpu_threshold = get_yaml_item_value(config, "cpu_threshold", ".5")
    heatmap_mem_threshold = get_yaml_item_value(config, "mem_threshold", ".3")
    output_file = config.get("json_output_file", False)
    if output_file is True:
        output_path = config.get("json_output_folder_path")
    else:
        output_path = False
    chaos_tests = config.get("chaos_tests", {})
    return (namespace, kubeconfig, prometheus_endpoint, auth_token, scrape_duration,
            chaos_tests, log_level, threshold, heatmap_cpu_threshold,
            heatmap_mem_threshold, output_path)


def prompt_input(prompt, default_value):
    user_input = input(f"{prompt} [{default_value}]: ")
    if user_input.strip():
        return user_input
    return default_value


def make_json_output(inputs, queries, analysis_data, output_path):
    time_str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())

    data = {
        "inputs": inputs,
        "queries": queries,
        "profiling": analysis_data[0],
        "heatmap_analysis": analysis_data[1],
        "recommendations": analysis_data[2]
    }

    logging.info(f"Summary\n{json.dumps(data, indent=4)}")

    if output_path is not False:
        file = f"recommender_{inputs['namespace']}_{time_str}.json"
        path = f"{os.path.expanduser(output_path)}/{file}"

        with open(path, "w") as json_output:
            logging.info(f"Saving output file in {output_path} folder...")
            json_output.write(json.dumps(data, indent=4))
            logging.info(f"Recommendation output saved in {file}.")


def json_inputs(namespace, kubeconfig, prometheus_endpoint, scrape_duration, chaos_tests, threshold, heatmap_cpu_threshold, heatmap_mem_threshold):
    inputs = {
        "namespace": namespace,
        "kubeconfig": kubeconfig,
        "prometheus_endpoint": prometheus_endpoint,
        "scrape_duration": scrape_duration,
        "chaos_tests": chaos_tests,
        "threshold": threshold,
        "heatmap_cpu_threshold": heatmap_cpu_threshold,
        "heatmap_mem_threshold": heatmap_mem_threshold
    }
    return inputs


def main():
    parser = argparse.ArgumentParser(description="Krkn Chaos Recommender Command-Line tool")
    args = parse_arguments(parser)

    if args.config_file is None and not args.options:
        logging.error("You have to either specify a config file path or pass recommender options as command line arguments")
        parser.print_help()
        sys.exit(1)

    if args.config_file is not None:
        (
         namespace,
         kubeconfig,
         prometheus_endpoint,
         auth_token,
         scrape_duration,
         chaos_tests,
         log_level,
         threshold,
         heatmap_cpu_threshold,
         heatmap_mem_threshold,
         output_path
         ) = read_configuration(args.config_file)

    if args.options:
        namespace = args.namespace
        kubeconfig = args.kubeconfig
        auth_token = args.token
        scrape_duration = args.scrape_duration
        log_level = args.log_level
        prometheus_endpoint = args.prometheus_endpoint
        output_path = args.json_output_file
        chaos_tests = {"MEM": args.MEM, "GENERIC": args.GENERIC, "CPU": args.CPU, "NETWORK": args.NETWORK}
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
            logging.info(f"Path for output file not specified. "
                         f"Using default folder {output_path}")
        if not os.path.exists(os.path.expanduser(output_path)):
            logging.error(f"Folder {output_path} for output not found.")
            sys.exit(1)
    logging.info("Loading inputs...")
    inputs = json_inputs(namespace, kubeconfig, prometheus_endpoint, scrape_duration, chaos_tests, threshold, heatmap_cpu_threshold, heatmap_mem_threshold)
    logging.info("Starting Analysis ...")

    file_path, queries = prometheus.fetch_utilization_from_prometheus(prometheus_endpoint, auth_token, namespace, scrape_duration)
    analysis_data = analysis(file_path, chaos_tests, threshold, heatmap_cpu_threshold, heatmap_mem_threshold)

    make_json_output(inputs, queries, analysis_data, output_path)


if __name__ == "__main__":
    main()
