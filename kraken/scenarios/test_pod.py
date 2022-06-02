import logging
import sys
import unittest

from kraken.scenarios import kube
from kraken.scenarios.kube import Client, NotFoundException
from kraken.scenarios.pod import PodScenario


class TestPodScenario(unittest.TestCase):
    def test_run(self):
        """
        This test creates a test pod and then runs the pod scenario restricting the run to that specific pod.
        """
        logging.basicConfig(stream=sys.stdout, level=logging.INFO)

        c = Client()
        test_pod = c.create_test_pod()
        self.addCleanup(lambda: self._remove_test_pod(c, test_pod.name, test_pod.namespace))

        scenario = PodScenario(logging.getLogger(__name__))
        config = scenario.create_config()
        config.kill = 1
        config.name_pattern = test_pod.name
        config.namespace_pattern = test_pod.namespace
        scenario.run(c, config)

        try:
            c.get_pod(test_pod.name)
            self.fail("Getting the pod after a pod scenario run should result in a NotFoundException.")
        except NotFoundException:
            return

    @staticmethod
    def _remove_test_pod(c: kube.Client, pod_name: str, pod_namespace: str):
        try:
            c.remove_pod(pod_name, pod_namespace)
        except NotFoundException:
            pass


if __name__ == '__main__':
    unittest.main()
