import logging

import pandas as pd
import kraken.chaos_recommender.kraken_tests as kraken_tests
import time

KRAKEN_TESTS_PATH = "./kraken_chaos_tests.txt"


# Placeholder, this should be done with topology
def return_critical_services():
    return ["web", "cart"]


def load_telemetry_data(file_path):
    data = pd.read_csv(file_path, delimiter=r"\s+")
    return data


def calculate_zscores(data):
    zscores = pd.DataFrame()
    zscores["Namespace"] = data["namespace"]
    zscores["Service"] = data["service"]
    zscores["CPU"] = (data["CPU"] - data["CPU"].mean()) / data["CPU"].std()
    zscores["Memory"] = (data["MEM"] - data["MEM"].mean()) / data["MEM"].std()
    zscores["Network"] = (data["NETWORK"] - data["NETWORK"].mean()) / data["NETWORK"].std()
    return zscores


def identify_outliers(data, threshold):
    outliers_cpu = data[data["CPU"] > threshold]["Service"].tolist()
    outliers_memory = data[data["Memory"] > threshold]["Service"].tolist()
    outliers_network = data[data["Network"] > threshold]["Service"].tolist()

    return outliers_cpu, outliers_memory, outliers_network


def get_services_above_heatmap_threshold(dataframe, cpu_threshold, mem_threshold):
    # Filter the DataFrame based on CPU_HEATMAP and MEM_HEATMAP thresholds
    filtered_df = dataframe[((dataframe['CPU']/dataframe['CPU_LIMITS']) > cpu_threshold)]
    # Get the lists of services
    cpu_services = filtered_df['service'].tolist()

    filtered_df = dataframe[((dataframe['MEM']/dataframe['MEM_LIMITS']) > mem_threshold)]
    mem_services = filtered_df['service'].tolist()

    return cpu_services, mem_services


def analysis(file_path, namespaces, chaos_tests_config, threshold,
             heatmap_cpu_threshold, heatmap_mem_threshold):
    # Load the telemetry data from file
    logging.info("Fetching the Telemetry data...")
    data = load_telemetry_data(file_path)

    # Calculate Z-scores for CPU, Memory, and Network columns
    zscores = calculate_zscores(data)
    # Dict for saving analysis data -- key is the namespace
    analysis_data = {}

    # Identify outliers for each namespace
    for namespace in namespaces:

        logging.info(f"Identifying outliers for namespace {namespace}...")

        namespace_zscores = zscores.loc[zscores["Namespace"] == namespace]
        namespace_data = data.loc[data["namespace"] == namespace]
        outliers_cpu, outliers_memory, outliers_network = identify_outliers(
            namespace_zscores, threshold)
        cpu_services, mem_services = get_services_above_heatmap_threshold(
            namespace_data, heatmap_cpu_threshold, heatmap_mem_threshold)

        analysis_data[namespace] = analysis_json(outliers_cpu, outliers_memory,
                                                 outliers_network,
                                                 cpu_services, mem_services,
                                                 chaos_tests_config)

        if cpu_services:
            logging.info(f"These services use significant CPU compared to "
                         f"their assigned limits: {cpu_services}")
        else:
            logging.info("There are no services that are using significant "
                         "CPU compared to their assigned limits "
                         "(infinite in case no limits are set).")
        if mem_services:
            logging.info(f"These services use significant MEMORY compared to "
                         f"their assigned limits: {mem_services}")
        else:
            logging.info("There are no services that are using significant "
                         "MEMORY compared to their assigned limits "
                         "(infinite in case no limits are set).")
        time.sleep(2)

    logging.info("Please check data in utilisation.txt for further analysis")

    return analysis_data


def analysis_json(outliers_cpu, outliers_memory, outliers_network,
                  cpu_services, mem_services, chaos_tests_config):

    profiling = {
        "cpu_outliers": outliers_cpu,
        "memory_outliers": outliers_memory,
        "network_outliers": outliers_network
    }

    heatmap = {
        "services_with_cpu_heatmap_above_threshold": cpu_services,
        "services_with_mem_heatmap_above_threshold": mem_services
    }

    recommendations = {}

    if cpu_services:
        cpu_recommend = {"services": cpu_services,
                         "tests": chaos_tests_config['CPU']}
        recommendations["cpu_services_recommendations"] = cpu_recommend

    if mem_services:
        mem_recommend = {"services": mem_services,
                         "tests": chaos_tests_config['MEM']}
        recommendations["mem_services_recommendations"] = mem_recommend

    if outliers_network:
        outliers_network_recommend = {"outliers_networks": outliers_network,
                                      "tests": chaos_tests_config['NETWORK']}
        recommendations["outliers_network_recommendations"] = (
            outliers_network_recommend)

    return [profiling, heatmap, recommendations]
