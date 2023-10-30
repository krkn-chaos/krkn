import argparse
import logging
import os.path
import sys
import yaml
# kraken module import for running the recommender
# both from the root directory and the recommender
# folder
sys.path.insert(0, './')
sys.path.insert(0, '../../')

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

    parser.add_argument("-M", "--MEM", nargs='+', action="store", default=[],
                        help="Memory related chaos tests (space separated list)")
    parser.add_argument("-C", "--CPU", nargs='+', action="store", default=[],
                        help="CPU related chaos tests (space separated list)")
    parser.add_argument("-N", "--NETWORK", nargs='+', action="store", default=[],
                        help="Network related chaos tests (space separated list)")
    parser.add_argument("-G", "--GENERIC", nargs='+', action="store", default=[],
                        help="Memory related chaos tests (space separated list)")


    return parser.parse_args()

def read_configuration(config_file_path):
    if not os.path.exists(config_file_path):
        logging.error(f"Config file not found: {config_file_path}")
        sys.exit(1)

    with open(config_file_path, mode="r") as config_file:
        config = yaml.safe_load(config_file)

    log_level = config.get("log level", "INFO")
    namespace = config.get("namespace", "")
    kubeconfig = config.get("kubeconfig", kube_config.KUBE_CONFIG_DEFAULT_LOCATION)

    prometheus_endpoint = config.get("prometheus_endpoint", "")
    auth_token = config.get("auth_token", "")
    scrape_duration = config.get("scrape_duration", "10m")
    chaos_tests = config.get("chaos_tests" , {})
    return (namespace, kubeconfig, prometheus_endpoint, auth_token, scrape_duration,
            chaos_tests, log_level)

def prompt_input(prompt, default_value):
    user_input = input(f"{prompt} [{default_value}]: ")
    if user_input.strip():
        return user_input
    return default_value

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
         log_level
         ) = read_configuration(args.config_file)

    if args.options:
        namespace = args.namespace
        kubeconfig = args.kubeconfig
        auth_token = args.token
        scrape_duration = args.scrape_duration
        log_level = args.log_level
        prometheus_endpoint = args.prometheus_endpoint
        chaos_tests = {"MEM": args.MEM, "GENERIC": args.GENERIC, "CPU": args.CPU, "NETWORK": args.NETWORK}

    if log_level not in ["DEBUG","INFO", "WARNING", "ERROR","CRITICAL"]:
        logging.error(f"{log_level} not a valid log level")
        sys.exit(1)

    logging.basicConfig(level=log_level)

    logging.info("============================INPUTS===================================")
    logging.info(f"Namespace: {namespace}")
    logging.info(f"Kubeconfig: {kubeconfig}")
    logging.info(f"Prometheus endpoint: {prometheus_endpoint}")
    logging.info(f"Scrape duration: {scrape_duration}")
    for test in chaos_tests.keys():
        logging.info(f"Chaos tests {test}: {chaos_tests[test]}")
    logging.info("=====================================================================")
    logging.info("Starting Analysis ...")
    logging.info("Fetching the Telemetry data")

    file_path = prometheus.fetch_utilization_from_prometheus(prometheus_endpoint, auth_token, namespace, scrape_duration)
    analysis(file_path, chaos_tests)

if __name__ == "__main__":
    main()
