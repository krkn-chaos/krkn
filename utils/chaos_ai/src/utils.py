import re

import urllib3
from kubernetes import client, config
from kubernetes.client.rest import ApiException


def get_load(fault):
    params = re.findall(r'\(.*?\)', fault)
    load = 100
    if len(params) > 0:
        load = params[0].strip('()')
        fault = fault.strip(params[0])
    return fault, load


def is_cluster_accessible(kubeconfig_path: str) -> bool:
    try:
        config.load_kube_config(config_file=kubeconfig_path)
        v1 = client.CoreV1Api()

        # Try to list nodes in the cluster
        nodes = v1.list_node()
        print("#Nodes in Cluster: ", len(nodes.items))

        return True
    except (FileNotFoundError, ApiException, Exception) as e:
        print(f"Cluster is not accessible: {e}")
        return False

def get_namespace_pods(namespaces: str, kubeconfig_path: str):
    ns_list = namespaces.split(",")
    ns_pods = {}
    for ns in ns_list:
        pods = get_pod_labels(ns, kubeconfig_path)
        if len(pods) > 0:
            ns_pods[ns] = pods
    return ns_pods

def get_ns_from_pod(ns_pods, podlabel):
    for ns in ns_pods:
        if podlabel in ns:
            return ns
    return ''

# get all pod labels from a namespace
def get_pod_labels(namespace: str, kubeconfig_path: str = None):
    pods = []
    try:
        if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            config.load_kube_config()  # Load default kubeconfig file

        v1 = client.CoreV1Api()

        pods = v1.list_namespaced_pod(namespace)

        print(f"Pod labels in namespace '{namespace}':")
        for pod in pods.items:
            print(f"Pod Name: {pod.metadata.name}, Labels: {pod.metadata.labels}")

    except FileNotFoundError:
        print(f"Kubeconfig file not found at {kubeconfig_path}")
    except ApiException as e:
        print(f"API exception occurred: {e}")
    except urllib3.exceptions.MaxRetryError as e:
        print(f"Max retries exceeded: {e}")
    except urllib3.exceptions.NewConnectionError as e:
        print(f"New connection error: {e}")
    except urllib3.exceptions.NameResolutionError as e:
        print(f"Name resolution error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return pods


def get_pods(kubeconfig_path: str = None):
    pods = []
    try:
        # Load the kubeconfig file
        if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            config.load_kube_config()  # Load default kubeconfig file
        v1 = client.CoreV1Api()
        pods = v1.list_pod_for_all_namespaces()

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return pods

# Example usage
namespace = 'default'
kubeconfig_path = '/path/to/your/kubeconfig'  # Provide the path to your kubeconfig file, or set to None to use the default
get_pod_labels(namespace, kubeconfig_path)

if __name__ == '__main__':
    # print(is_cluster_accessible("~/Downloads/chaos/kraken/kubeconfig"))
    print(is_cluster_accessible("~/Downloads/kube-config-raw"))

