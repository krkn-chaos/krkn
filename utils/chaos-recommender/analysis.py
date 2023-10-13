import pandas as pd
import kraken_tests
import time

threshold = .7  # Adjust the threshold as needed
heatmap_cpu_threshold = .5
heatmap_mem_threshold = .5

KRAKEN_TESTS_PATH = "./kraken_chaos_tests.txt"

#Placeholder, this should be done with topology
def return_critical_services():
    return ["web", "cart"]


def load_telemetry_data(file_path):
    data = pd.read_csv(file_path, delimiter=r"\s+")
    return data

def calculate_zscores(data):
    zscores = pd.DataFrame()
    zscores["Service"] = data["service"]
    zscores["CPU"] = (data["CPU"] - data["CPU"].mean()) / data["CPU"].std()
    zscores["Memory"] = (data["MEM"] - data["MEM"].mean()) / data["MEM"].std()
    zscores["Network"] = (data["NETWORK"] - data["NETWORK"].mean()) / data["NETWORK"].std()
    #print("wdfdsfsdfsdfssd")
    #print(zscores)
    return zscores

def identify_outliers(data):
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


def analysis(file_path):
    # Load the telemetry data from file
    data = load_telemetry_data(file_path)

    # Calculate Z-scores for CPU, Memory, and Network columns
    zscores = calculate_zscores(data)

    # Identify outliers
    outliers_cpu, outliers_memory, outliers_network = identify_outliers(zscores)
    cpu_services, mem_services = get_services_above_heatmap_threshold(data, heatmap_cpu_threshold, heatmap_mem_threshold)

    # Display the identified outliers
    print("======================== Profiling ==================================")
    print("CPU outliers:", outliers_cpu)
    print("Memory outliers:", outliers_memory)
    print("Network outliers:", outliers_network)
    print("===================== HeatMap Analysis ==============================")

    if cpu_services:
        print("Services with CPU_HEATMAP above threshold:", cpu_services)
    else:
        print("There are no services that are using siginificant CPU compared to their assigned limits (infinite in case no limits are set).")
    if mem_services:
        print("Services with MEM_HEATMAP above threshold:", mem_services)
    else:
        print("There are no services that are using siginificant MEMORY compared to their assigned limits (infinite in case no limits are set).")
    time.sleep(2)
    print("======================= Recommendations =============================")
    if cpu_services:
        print("Recommended tests for " + str(cpu_services) + " :\n" + str(kraken_tests.get_entries_by_category(KRAKEN_TESTS_PATH, "CPU")) )
        print("\n")
    if mem_services:
        print("Recommended tests for " + str(mem_services) + " :\n" + str(kraken_tests.get_entries_by_category(KRAKEN_TESTS_PATH, "MEM")) )
        print("\n")

    if outliers_network:
        print("Recommended tests for " + str(outliers_network) + " :\n" + str(kraken_tests.get_entries_by_category(KRAKEN_TESTS_PATH, "NETWORK")) )
        print("\n")

    #print("Recommended tests for " + str(return_critical_services()) + " :\n" + str(kraken_tests.get_entries_by_category(KRAKEN_TESTS_PATH, "GENERIC")) )
    print("\n")
    print("Please check data in utilisation.txt for further analysis")

#if __name__ == "__main__":
#    file_path = "./utilisation.txt"  # Replace with the actual file path
#    analysis(file_path)
