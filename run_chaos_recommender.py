import argparse
import configparser
from kraken.recommender import analisys
from kraken.recommender import prometheus

def parse_arguments():
    parser = argparse.ArgumentParser(description="Command-line tool")
    parser.add_argument("-p", "--prompt", action="store_true", help="Prompt for input")
    return parser.parse_args()

def read_configuration():
    config = configparser.ConfigParser()
    config.read("./config.ini")

    application = config.get("General", "application", fallback="")
    namespace = config.get("General", "namespace", fallback="")
    labels = config.get("General", "labels", fallback="")
    kubeconfig = config.get("General", "kubeconfig", fallback="~/.kube/config.yaml")

    prometheus_endpoint = config.get("Options", "prometheus_endpoint", fallback="")
    auth_token = config.get("Options", "auth_token", fallback="")
    scrape_duration = config.get("Options", "scrape_duration", fallback="1m")
    chaos_library = config.get("Options", "chaos_library", fallback="kraken")

    return application, namespace, labels, kubeconfig, prometheus_endpoint, auth_token, scrape_duration, chaos_library

def prompt_input(prompt, default_value):
    user_input = input(f"{prompt} [{default_value}]: ")
    if user_input.strip():
        return user_input
    return default_value

def main():
    args = parse_arguments()

    application, namespace, labels, kubeconfig, prometheus_endpoint, auth_token, scrape_duration, chaos_library = read_configuration()

    if args.prompt:
        application = prompt_input("Application name", application)
        namespace = prompt_input("Namespace", namespace)
        labels = prompt_input("Labels", labels)
        kubeconfig = prompt_input("Kubeconfig file location", kubeconfig)
        prometheus_endpoint = prompt_input("Prometheus endpoint", prometheus_endpoint)
        auth_token = prompt_input("Auth Token for Prometheus", auth_token)
        scrape_duration = prompt_input("Scrape duration", scrape_duration)
        chaos_library = prompt_input("Chaos library", chaos_library)

    print("============================INPUTS===================================")
    print(f"Application: {application}")
    print(f"Namespace: {namespace}")
    print(f"Labels: {labels}")
    print(f"Kubeconfig: {kubeconfig}")
    print(f"Prometheus endpoint: {prometheus_endpoint}")
    print(f"Scrape duration: {scrape_duration}")
    print(f"Chaos library: {chaos_library}")
    print("=====================================================================")
    print("Starting Analysis ...")
    print("Fetching the Telemetry data")

    file_path = prometheus.fetch_utilization_from_prometheus(prometheus_endpoint, auth_token, namespace, scrape_duration)

    analisys.analysis(file_path)

if __name__ == "__main__":
    main()
