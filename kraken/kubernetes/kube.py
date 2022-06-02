import unittest
from dataclasses import dataclass
from typing import Dict, List
from kubernetes import config, client
from kubernetes.client.models import V1Pod, V1PodSpec, V1ObjectMeta, V1Container
from kubernetes.client.exceptions import ApiException


@dataclass
class Pod:
    """
    A pod is a simplified representation of a Kubernetes pod. We only extract the data we need in krkn.
    """
    name: str
    namespace: str
    labels: Dict[str, str]


class Client:
    """
    This is the implementation of all Kubernetes API calls used in Krkn.
    """

    def __init__(self, kubeconfig_path: str = None):
        # Note: this function replicates much of the functionality already represented in the Kubernetes Python client,
        # but in an object-oriented manner. This allows for creating multiple clients and accessing multiple clusters
        # with minimal effort if needed, which the procedural implementation doesn't allow.
        if kubeconfig_path is None:
            kubeconfig_path = config.KUBE_CONFIG_DEFAULT_LOCATION
        kubeconfig = config.kube_config.KubeConfigMerger(kubeconfig_path)

        if kubeconfig.config is None:
            raise config.ConfigException(
                'Invalid kube-config file: %s. '
                'No configuration found.' % kubeconfig_path)
        loader = config.kube_config.KubeConfigLoader(
            config_dict=kubeconfig.config,
        )
        client_config = client.Configuration()
        loader.load_and_set(client_config)
        self.client = client.ApiClient(configuration=client_config)
        self.core_v1 = client.CoreV1Api(self.client)

    @staticmethod
    def _convert_pod(pod: V1Pod) -> Pod:
        return Pod(
            name=pod.metadata.name,
            namespace=pod.metadata.namespace,
            labels=pod.metadata.labels
        )

    def create_test_pod(self) -> Pod:
        """
        create_test_pod creates a test pod in the default namespace that can be safely killed.
        """
        return self._convert_pod(self.core_v1.create_namespaced_pod(
            "default",
            V1Pod(
                metadata=V1ObjectMeta(
                    generate_name="test-",
                ),
                spec=V1PodSpec(
                    containers=[
                        V1Container(
                            name="test",
                            image="alpine",
                            tty=True,
                        )
                    ]
                ),
            )
        ))

    def list_all_pods(self, label_selector: str = None) -> List[Pod]:
        """
        list_all_pods lists all pods in all namespaces, possibly with a label selector applied.
        """
        try:
            pod_response = self.core_v1.list_pod_for_all_namespaces(watch=False, label_selector=label_selector)
            pod_list: List[client.models.V1Pod] = pod_response.items
            result: List[Pod] = []
            for pod in pod_list:
                result.append(self._convert_pod(pod))
            return result
        except ApiException as e:
            if e.status == 404:
                raise NotFoundException(e)
            raise

    def get_pod(self, name: str, namespace: str = "default") -> Pod:
        """
        get_pod returns a pod based on the name and a namespace.
        """
        try:
            return self._convert_pod(self.core_v1.read_namespaced_pod(name, namespace))
        except ApiException as e:
            if e.status == 404:
                raise NotFoundException(e)
            raise

    def remove_pod(self, name: str, namespace: str = "default"):
        """
        remove_pod removes a pod based on the name and namespace. A NotFoundException is raised if the pod doesn't
        exist.
        """
        try:
            self.core_v1.delete_namespaced_pod(name, namespace)
        except ApiException as e:
            if e.status == 404:
                raise NotFoundException(e)
            raise


class NotFoundException(Exception):
    """
    NotFoundException is an exception specific to the scenario Kubernetes abstraction and is thrown when a specific
    resource (e.g. a pod) cannot be found.
    """

    def __init__(self, cause: Exception):
        self.__cause__ = cause


if __name__ == '__main__':
    unittest.main()
