from prometheus_api_client import PrometheusConnect
import pandas as pd
import urllib3


saved_metrics_path = "./utilisation.txt"
duration = "10m"

def convert_data_to_dataframe(data, label):
    df = pd.DataFrame()
    df['service'] = [item['metric']['pod'] for item in data]
    df[label] = [item['value'][1] for item in data]

    return df


def get_value_from_data(data, service):
    df = pd.DataFrame()
    df['service'] = [item['metric']['pod'] for item in data]
    df[label] = [item['value'][1] for item in data]

    return df


def convert_data(data, service):

    #print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
    #print(data)
    #print(service)
    result = {}
    for entry in data:
        pod_name = entry['metric']['pod']
        value = entry['value'][1]
        result[pod_name] = value
    #print(result)
    return result.get(service, '100000000000') # for those pods whose limits are not defined they can take as much resources, there assigning a very high value

def save_utilization_to_file(cpu_data, cpu_limits_result, mem_data, mem_limits_result, network_data, filename):

    #print(cpu_data)
    df_cpu = convert_data_to_dataframe(cpu_data, "CPU")
    #df_cpu_limits = convert_data_to_dataframe(cpu_limits_result, "CPU_LIMITS")
    #df_mem = convert_data_to_dataframe(mem_data, "MEM")
    #df_mem_limits = convert_data_to_dataframe(mem_limits_result, "MEM_LIMITS")
    #df_network = convert_data_to_dataframe(network_data, "NETWORK")

    #dataframes = [df_cpu, df_cpu_limits, df_mem, df_mem_limits, df_network]

    #print(df_cpu, df_cpu_limits, df_mem, df_mem_limits, df_network)

    merged_df = pd.DataFrame(columns=['service','CPU','CPU_LIMITS','MEM','MEM_LIMITS','NETWORK'])


    services = df_cpu.service.unique()

    print(services)

    for s in services:

        new_row = {"service": s, "CPU" : convert_data(cpu_data, s),
                    "CPU_LIMITS" : convert_data(cpu_limits_result, s),
                    "MEM" : convert_data(mem_data, s), "MEM_LIMITS" : convert_data(mem_limits_result, s),
                    "NETWORK" : convert_data(network_data, s)}
        merged_df = merged_df.append(new_row, ignore_index=True)

    print("===========merged_df==================")
    print(merged_df)

    # Convert columns to string
    merged_df['CPU'] = merged_df['CPU'].astype(str)
    merged_df['MEM'] = merged_df['MEM'].astype(str)
    merged_df['CPU_LIMITS'] = merged_df['CPU_LIMITS'].astype(str)
    merged_df['MEM_LIMITS'] = merged_df['MEM_LIMITS'].astype(str)
    merged_df['NETWORK'] = merged_df['NETWORK'].astype(str)

    # Extract integer part before the decimal point
    merged_df['CPU'] = merged_df['CPU'].str.split('.').str[0]
    merged_df['MEM'] = merged_df['MEM'].str.split('.').str[0]
    merged_df['CPU_LIMITS'] = merged_df['CPU_LIMITS'].str.split('.').str[0]
    merged_df['MEM_LIMITS'] = merged_df['MEM_LIMITS'].str.split('.').str[0]
    merged_df['NETWORK'] = merged_df['NETWORK'].str.split('.').str[0]

    #print ("====================================================================")
    #print(merged_df.to_string(index=False))
    #print ("====================================================================")
    #merged_df['service'] = merged_df['service'].apply(lambda x: x.split('-')[0])
    merged_df.to_csv(filename, sep='\t', index=False)

def fetch_utilization_from_prometheus(prometheus_endpoint, auth_token, namespace, n):
    urllib3.disable_warnings()
    prometheus = PrometheusConnect(url=prometheus_endpoint, headers={'Authorization':'Bearer {}'.format(auth_token)}, disable_ssl=True)

    # Fetch CPU utilization
    cpu_query = 'sum (rate (container_cpu_usage_seconds_total{image!="", namespace="%s"}[%s])) by (pod) *1000' % (namespace,duration)
    print(cpu_query)
    cpu_result = prometheus.custom_query(cpu_query)
    cpu_data = cpu_result


    cpu_limits_query = '(sum by (pod) (kube_pod_container_resource_limits{resource="cpu", namespace="%s"}))*1000' %(namespace)
    print(cpu_limits_query)
    cpu_limits_result = prometheus.custom_query(cpu_limits_query)

    #cpu_heatmap_query = '((sum by (pod) (rate(container_cpu_usage_seconds_total{container!="", namespace="%s"}[%s])) \
    #/ on (pod) group_left() \
    #kube_pod_container_resource_limits{resource="cpu", namespace="%s"}) )*100' % (namespace, duration, namespace)
    #cpu_heatmap_result = prometheus.custom_query(cpu_heatmap_query)
    #cpu_heatmap_data = cpu_heatmap_result


    # Fetch memory utilization
    #mem_query = 'container_memory_usage_bytes{namespace="%s"} by (pod)' % namespace
    mem_query = 'sum by (pod) (avg_over_time(container_memory_usage_bytes{image!="", namespace="%s"}[%s]))' % (namespace, duration)
    print(mem_query)
    mem_result = prometheus.custom_query(mem_query)
    mem_data = mem_result

    mem_limits_query = 'sum by (pod) (kube_pod_container_resource_limits{resource="memory", namespace="%s"})  ' %(namespace)
    print(mem_limits_query)
    mem_limits_result = prometheus.custom_query(mem_limits_query)

    #mem_heatmap_query  = '(avg_over_time(container_memory_usage_bytes{container!="", namespace="%s"}[%s]) \
    #                / on (pod) group_left() \
    #                kube_pod_container_resource_limits{container!="", resource="memory", namespace="%s"}) *100' % (namespace, duration, namespace)
    #mem_heatmap_result = prometheus.custom_query(mem_heatmap_query)
    #mem_heatmap_data = mem_heatmap_result

    # Fetch network utilization
    network_query = 'sum by (pod) ((avg_over_time(container_network_transmit_bytes_total{namespace="%s"}[%s])) + \
    (avg_over_time(container_network_receive_bytes_total{namespace="%s"}[%s])))' % (namespace, duration, namespace, duration)
    network_result = prometheus.custom_query(network_query)
    print(network_query)
    network_data = network_result


    save_utilization_to_file(cpu_data, cpu_limits_result, mem_data, mem_limits_result, network_data, saved_metrics_path)
    return saved_metrics_path


# Example usage
#prometheus_endpoint = "http://localhost:9090"
#namespace ="robot-shop"
#n = 1  # Number of minutes

#fetch_utilization_from_prometheus(prometheus_endpoint, namespace, n)
#save_utilization_to_file(cpu_data, mem_data, network_data, 'utilization.txt')
