import re
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

if __name__ == '__main__':
    # print(is_cluster_accessible("~/Downloads/chaos/kraken/kubeconfig"))
    print(is_cluster_accessible("~/Downloads/kube-config-raw"))

