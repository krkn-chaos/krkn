import unittest

from kraken.scenarios import kube


class TestClient(unittest.TestCase):
    def test_list_all_pods(self):
        c = kube.Client()
        pod = c.create_test_pod()
        self.addCleanup(lambda: self._remove_pod(c, pod.name, pod.namespace))
        pods = c.list_all_pods()
        for pod in pods:
            if pod.name == pod.name and pod.namespace == pod.namespace:
                return
        self.fail("The created pod %s was not in the pod list." % pod.name)

    def test_get_pod(self):
        c = kube.Client()
        pod = c.create_test_pod()
        self.addCleanup(lambda: c.remove_pod(pod.name, pod.namespace))
        pod2 = c.get_pod(pod.name, pod.namespace)
        assert pod2.name == pod.name
        assert pod2.namespace == pod.namespace

    def test_get_pod_notfound(self):
        c = kube.Client()
        try:
            c.get_pod("non-existent-pod")
            self.fail("Fetching a non-existent pod did not result in a NotFoundException.")
        except kube.NotFoundException:
            pass

    @staticmethod
    def _remove_pod(c: kube.Client, pod_name: str, pod_namespace: str):
        try:
            c.remove_pod(pod_name, pod_namespace)
        except kube.NotFoundException:
            pass


if __name__ == '__main__':
    unittest.main()
