import logging

from prometheus_api_client import PrometheusConnect
import pandas as pd
import urllib3


saved_metrics_path = "./utilisation.txt"


def convert_data_to_dataframe(data, label):
    df = pd.DataFrame()
    df["service"] = [item["metric"]["pod"] for item in data]
    df[label] = [item["value"][1] for item in data]

    return df


def convert_data(data, service):
    result = {}
    for entry in data:
        pod_name = entry["metric"]["pod"]
        value = entry["value"][1]
        result[pod_name] = value
    return result.get(
        service
    )  # for those pods whose limits are not defined they can take as much resources, there assigning a very high value


def convert_data_limits(data, node_data, service, prometheus):
    result = {}
    for entry in data:
        pod_name = entry["metric"]["pod"]
        value = entry["value"][1]
        result[pod_name] = value
    return result.get(
        service, get_node_capacity(node_data, service, prometheus)
    )  # for those pods whose limits are not defined they can take as much resources, there assigning a very high value


def get_node_capacity(node_data, pod_name, prometheus):

    # Get the node name on which the pod is running
    query = f'kube_pod_info{{pod="{pod_name}"}}'
    result = prometheus.custom_query(query)
    if not result:
        return None

    node_name = result[0]["metric"]["node"]

    for item in node_data:
        if item["metric"]["node"] == node_name:
            return item["value"][1]

    return "1000000000"


def save_utilization_to_file(utilization, filename, prometheus):

    merged_df = pd.DataFrame(
        columns=[
            "namespace",
            "service",
            "CPU",
            "CPU_LIMITS",
            "MEM",
            "MEM_LIMITS",
            "NETWORK",
        ]
    )
    for namespace in utilization:
        # Loading utilization_data[] for namespace
        # indexes -- 0 CPU, 1 CPU limits, 2 mem, 3 mem limits, 4 network
        utilization_data = utilization[namespace]
        df_cpu = convert_data_to_dataframe(utilization_data[0], "CPU")
        services = df_cpu.service.unique()
        logging.info("Services for namespace %s: %s", namespace, services)

        for s in services:

            new_row_df = pd.DataFrame(
                {
                    "namespace": namespace,
                    "service": s,
                    "CPU": convert_data(utilization_data[0], s),
                    "CPU_LIMITS": convert_data_limits(
                        utilization_data[1], utilization_data[5], s, prometheus
                    ),
                    "MEM": convert_data(utilization_data[2], s),
                    "MEM_LIMITS": convert_data_limits(
                        utilization_data[3], utilization_data[6], s, prometheus
                    ),
                    "NETWORK": convert_data(utilization_data[4], s),
                },
                index=[0],
            )
            merged_df = pd.concat([merged_df, new_row_df], ignore_index=True)

    # Convert columns to string
    merged_df["CPU"] = merged_df["CPU"].astype(str)
    merged_df["MEM"] = merged_df["MEM"].astype(str)
    merged_df["CPU_LIMITS"] = merged_df["CPU_LIMITS"].astype(str)
    merged_df["MEM_LIMITS"] = merged_df["MEM_LIMITS"].astype(str)
    merged_df["NETWORK"] = merged_df["NETWORK"].astype(str)

    # Extract integer part before the decimal point
    # merged_df['CPU'] = merged_df['CPU'].str.split('.').str[0]
    # merged_df['MEM'] = merged_df['MEM'].str.split('.').str[0]
    # merged_df['CPU_LIMITS'] = merged_df['CPU_LIMITS'].str.split('.').str[0]
    # merged_df['MEM_LIMITS'] = merged_df['MEM_LIMITS'].str.split('.').str[0]
    # merged_df['NETWORK'] = merged_df['NETWORK'].str.split('.').str[0]

    merged_df.to_csv(filename, sep="\t", index=False)


def fetch_utilization_from_prometheus(
    prometheus_endpoint, auth_token, namespaces, scrape_duration
):
    urllib3.disable_warnings()
    prometheus = PrometheusConnect(
        url=prometheus_endpoint,
        headers={"Authorization": "Bearer {}".format(auth_token)},
        disable_ssl=True,
    )

    # Dicts for saving utilisation and queries -- key is namespace
    utilization = {}
    queries = {}

    logging.info("Fetching utilization...")
    for namespace in namespaces:

        # Fetch CPU utilization
        cpu_query = (
            'sum (rate (container_cpu_usage_seconds_total{image!="", namespace="%s"}[%s])) by (pod) *1000'
            % (namespace, scrape_duration)
        )
        cpu_result = prometheus.custom_query(cpu_query)

        cpu_limits_query = (
            '(sum by (pod) (kube_pod_container_resource_limits{resource="cpu", namespace="%s"}))*1000'
            % (namespace)
        )
        cpu_limits_result = prometheus.custom_query(cpu_limits_query)

        node_cpu_limits_query = (
            'kube_node_status_capacity{resource="cpu", unit="core"}*1000'
        )
        node_cpu_limits_result = prometheus.custom_query(node_cpu_limits_query)

        mem_query = (
            'sum by (pod) (avg_over_time(container_memory_usage_bytes{image!="", namespace="%s"}[%s]))'
            % (namespace, scrape_duration)
        )
        mem_result = prometheus.custom_query(mem_query)

        mem_limits_query = (
            'sum by (pod) (kube_pod_container_resource_limits{resource="memory", namespace="%s"})  '
            % (namespace)
        )
        mem_limits_result = prometheus.custom_query(mem_limits_query)

        node_mem_limits_query = (
            'kube_node_status_capacity{resource="memory", unit="byte"}'
        )
        node_mem_limits_result = prometheus.custom_query(node_mem_limits_query)

        network_query = (
            'sum by (pod) ((avg_over_time(container_network_transmit_bytes_total{namespace="%s"}[%s])) + \
        (avg_over_time(container_network_receive_bytes_total{namespace="%s"}[%s])))'
            % (namespace, scrape_duration, namespace, scrape_duration)
        )
        network_result = prometheus.custom_query(network_query)

        utilization[namespace] = [
            cpu_result,
            cpu_limits_result,
            mem_result,
            mem_limits_result,
            network_result,
            node_cpu_limits_result,
            node_mem_limits_result,
        ]
        queries[namespace] = json_queries(
            cpu_query, cpu_limits_query, mem_query, mem_limits_query, network_query
        )

    save_utilization_to_file(utilization, saved_metrics_path, prometheus)

    return saved_metrics_path, queries


def json_queries(
    cpu_query, cpu_limits_query, mem_query, mem_limits_query, network_query
):
    queries = {
        "cpu_query": cpu_query,
        "cpu_limit_query": cpu_limits_query,
        "memory_query": mem_query,
        "memory_limit_query": mem_limits_query,
        "network_query": network_query,
    }
    return queries
