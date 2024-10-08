import os
import unittest

import yaml

from .context_auth import ContextAuth


class TestCurrentContext(unittest.TestCase):

    def get_kubeconfig_with_data(self) -> str:
        """
        This function returns a test kubeconfig file as a string.

        :return: a test kubeconfig file in string format (for unit testing purposes)
        """  # NOQA
        return """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUM5ekNDQWQrZ0F3SUJBZ0lVV01PTVBNMVUrRi9uNXN6TSthYzlMcGZISHB3d0RRWUpLb1pJaHZjTkFRRUwKQlFBd0hqRWNNQm9HQTFVRUF3d1RhM1ZpZFc1MGRTNXNiMk5oYkdSdmJXRnBiakFlRncweU1URXlNRFl4T0RBdwpNRFJhRncwek1URXlNRFF4T0RBd01EUmFNQjR4SERBYUJnTlZCQU1NRTJ0MVluVnVkSFV1Ykc5allXeGtiMjFoCmFXNHdnZ0VpTUEwR0NTcUdTSWIzRFFFQkFRVUFBNElCRHdBd2dnRUtBb0lCQVFDNExhcG00SDB0T1NuYTNXVisKdzI4a0tOWWRwaHhYOUtvNjUwVGlOK2c5ZFNQU3VZK0V6T1JVOWVONlgyWUZkMEJmVFNodno4Y25rclAvNysxegpETEoxQ3MwRi9haEV3ZDQxQXN5UGFjbnRiVE80dGRLWm9POUdyODR3YVdBN1hSZmtEc2ZxRGN1YW5UTmVmT1hpCkdGbmdDVzU5Q285M056alB1eEFrakJxdVF6eE5GQkgwRlJPbXJtVFJ4cnVLZXo0aFFuUW1OWEFUNnp0M21udzMKWUtWTzU4b2xlcUxUcjVHNlRtVFQyYTZpVGdtdWY2N0cvaVZlalJGbkw3YkNHWmgzSjlCSTNMcVpqRzE4dWxvbgpaVDdQcGQrQTlnaTJOTm9UZlI2TVB5SndxU1BCL0xZQU5ZNGRoZDVJYlVydDZzbmViTlRZSHV2T0tZTDdNTWRMCmVMSzFBZ01CQUFHakxUQXJNQWtHQTFVZEV3UUNNQUF3SGdZRFZSMFJCQmN3RllJVGEzVmlkVzUwZFM1c2IyTmgKYkdSdmJXRnBiakFOQmdrcWhraUc5dzBCQVFzRkFBT0NBUUVBQTVqUHVpZVlnMExySE1PSkxYY0N4d3EvVzBDNApZeFpncVd3VHF5VHNCZjVKdDlhYTk0SkZTc2dHQWdzUTN3NnA2SlBtL0MyR05MY3U4ZWxjV0E4UXViQWxueXRRCnF1cEh5WnYrZ08wMG83TXdrejZrTUxqQVZ0QllkRzJnZ21FRjViTEk5czBKSEhjUGpHUkl1VHV0Z0tHV1dPWHgKSEg4T0RzaG9wZHRXMktrR2c2aThKaEpYaWVIbzkzTHptM00xRUNGcXAvMEdtNkN1RFphVVA2SGpJMWRrYllLdgpsSHNVZ1U1SmZjSWhNYmJLdUllTzRkc1YvT3FHcm9iNW5vcmRjaExBQmRDTnc1cmU5T1NXZGZ1VVhSK0ViZVhrCjVFM0tFYzA1RGNjcGV2a1NTdlJ4SVQrQzNMOTltWGcxL3B5NEw3VUhvNFFLTXlqWXJXTWlLRlVKV1E9PQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0tCg==
    server: https://127.0.0.1:6443
  name: default
contexts:
- context:
    cluster: default
    namespace: default
    user: testuser
  name: default
current-context: default
kind: Config
preferences: {}
users:
- name: testuser
  user:
    client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUM5ekNDQWQrZ0F3SUJBZ0lVV01PTVBNMVUrRi9uNXN6TSthYzlMcGZISHB3d0RRWUpLb1pJaHZjTkFRRUwKQlFBd0hqRWNNQm9HQTFVRUF3d1RhM1ZpZFc1MGRTNXNiMk5oYkdSdmJXRnBiakFlRncweU1URXlNRFl4T0RBdwpNRFJhRncwek1URXlNRFF4T0RBd01EUmFNQjR4SERBYUJnTlZCQU1NRTJ0MVluVnVkSFV1Ykc5allXeGtiMjFoCmFXNHdnZ0VpTUEwR0NTcUdTSWIzRFFFQkFRVUFBNElCRHdBd2dnRUtBb0lCQVFDNExhcG00SDB0T1NuYTNXVisKdzI4a0tOWWRwaHhYOUtvNjUwVGlOK2c5ZFNQU3VZK0V6T1JVOWVONlgyWUZkMEJmVFNodno4Y25rclAvNysxegpETEoxQ3MwRi9haEV3ZDQxQXN5UGFjbnRiVE80dGRLWm9POUdyODR3YVdBN1hSZmtEc2ZxRGN1YW5UTmVmT1hpCkdGbmdDVzU5Q285M056alB1eEFrakJxdVF6eE5GQkgwRlJPbXJtVFJ4cnVLZXo0aFFuUW1OWEFUNnp0M21udzMKWUtWTzU4b2xlcUxUcjVHNlRtVFQyYTZpVGdtdWY2N0cvaVZlalJGbkw3YkNHWmgzSjlCSTNMcVpqRzE4dWxvbgpaVDdQcGQrQTlnaTJOTm9UZlI2TVB5SndxU1BCL0xZQU5ZNGRoZDVJYlVydDZzbmViTlRZSHV2T0tZTDdNTWRMCmVMSzFBZ01CQUFHakxUQXJNQWtHQTFVZEV3UUNNQUF3SGdZRFZSMFJCQmN3RllJVGEzVmlkVzUwZFM1c2IyTmgKYkdSdmJXRnBiakFOQmdrcWhraUc5dzBCQVFzRkFBT0NBUUVBQTVqUHVpZVlnMExySE1PSkxYY0N4d3EvVzBDNApZeFpncVd3VHF5VHNCZjVKdDlhYTk0SkZTc2dHQWdzUTN3NnA2SlBtL0MyR05MY3U4ZWxjV0E4UXViQWxueXRRCnF1cEh5WnYrZ08wMG83TXdrejZrTUxqQVZ0QllkRzJnZ21FRjViTEk5czBKSEhjUGpHUkl1VHV0Z0tHV1dPWHgKSEg4T0RzaG9wZHRXMktrR2c2aThKaEpYaWVIbzkzTHptM00xRUNGcXAvMEdtNkN1RFphVVA2SGpJMWRrYllLdgpsSHNVZ1U1SmZjSWhNYmJLdUllTzRkc1YvT3FHcm9iNW5vcmRjaExBQmRDTnc1cmU5T1NXZGZ1VVhSK0ViZVhrCjVFM0tFYzA1RGNjcGV2a1NTdlJ4SVQrQzNMOTltWGcxL3B5NEw3VUhvNFFLTXlqWXJXTWlLRlVKV1E9PQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0tCg==
    client-key-data: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUV2QUlCQURBTkJna3Foa2lHOXcwQkFRRUZBQVNDQktZd2dnU2lBZ0VBQW9JQkFRQzRMYXBtNEgwdE9TbmEKM1dWK3cyOGtLTllkcGh4WDlLbzY1MFRpTitnOWRTUFN1WStFek9SVTllTjZYMllGZDBCZlRTaHZ6OGNua3JQLwo3KzF6RExKMUNzMEYvYWhFd2Q0MUFzeVBhY250YlRPNHRkS1pvTzlHcjg0d2FXQTdYUmZrRHNmcURjdWFuVE5lCmZPWGlHRm5nQ1c1OUNvOTNOempQdXhBa2pCcXVRenhORkJIMEZST21ybVRSeHJ1S2V6NGhRblFtTlhBVDZ6dDMKbW53M1lLVk81OG9sZXFMVHI1RzZUbVRUMmE2aVRnbXVmNjdHL2lWZWpSRm5MN2JDR1poM0o5QkkzTHFaakcxOAp1bG9uWlQ3UHBkK0E5Z2kyTk5vVGZSNk1QeUp3cVNQQi9MWUFOWTRkaGQ1SWJVcnQ2c25lYk5UWUh1dk9LWUw3Ck1NZExlTEsxQWdNQkFBRUNnZ0VBQ28rank4NW5ueVk5L2l6ZjJ3cjkzb2J3OERaTVBjYnIxQURhOUZYY1hWblEKT2c4bDZhbU9Ga2tiU0RNY09JZ0VDdkx6dEtXbmQ5OXpydU5sTEVtNEdmb0trNk5kK01OZEtKRUdoZHE5RjM1Qgpqdi91R1owZTIyRE5ZLzFHNVdDTE5DcWMwQkVHY2RFOTF0YzJuMlppRVBTNWZ6WVJ6L1k4cmJ5K1NqbzJkWE9RCmRHYWRlUFplbi9UbmlHTFlqZWhrbXZNQjJvU0FDbVMycTd2OUNrcmdmR1RZbWJzeGVjSU1QK0JONG9KS3BOZ28KOUpnRWJ5SUxkR1pZS2pQb2lLaHNjMVhmSy8zZStXSmxuYjJBaEE5Y1JMUzhMcDdtcEYySWp4SjNSNE93QTg3WQpNeGZvZWFGdnNuVUFHWUdFWFo4Z3BkWmhQMEoxNWRGdERjajIrcngrQVFLQmdRRDFoSE9nVGdFbERrVEc5bm5TCjE1eXYxRzUxYnJMQU1UaWpzNklEMU1qelhzck0xY2ZvazVaaUlxNVJsQ3dReTlYNDdtV1RhY0lZRGR4TGJEcXEKY0IydjR5Wm1YK1VleGJ3cDU1OWY0V05HdzF5YzQrQjdaNFF5aTRFelN4WmFjbldjMnBzcHJMUFVoOUFXRXVNcApOaW1vcXNiVGNnNGs5QWRxeUIrbWhIWmJRUUtCZ1FEQUNzU09qNXZMU1VtaVpxYWcrOVMySUxZOVNOdDZzS1VyCkprcjdCZEVpN3N2YmU5cldRR2RBb0xkQXNzcU94aENydmtPNkpSSHB1YjlRRjlYdlF4Riszc2ZpZm4yYkQ0ZloKMlVsclA1emF3RlNrNDNLbjdMZzRscURpaVUxVGlqTkJBL3dUcFlmbTB4dW5WeFRWNDZpNVViQW1XRk12TWV0bQozWUZYQmJkK2RRS0JnRGl6Q1B6cFpzeEcrazAwbUxlL2dYajl4ekNwaXZCbHJaM29teTdsVWk4YUloMmg5VlBaCjJhMzZNbVcyb1dLVG9HdW5xcCtibWU1eUxRRGlFcjVQdkJ0bGl2V3ppYmRNbFFMY2Nlcnpveml4WDA4QU5WUnEKZUpZdnIzdklDSGFFM25LRjdiVjNJK1NlSk1ra1BYL0QrV1R4WTQ5clZLYm1FRnh4c1JXRW04ekJBb0dBWEZ3UgpZanJoQTZqUW1DRmtYQ0loa0NJMVkwNEorSHpDUXZsY3NGT0EzSnNhUWduVUdwekl5OFUvdlFiLzhpQ0IzZ2RZCmpVck16YXErdnVkbnhYVnRFYVpWWGJIVitPQkVSdHFBdStyUkprZS9yYm1SNS84cUxsVUxOVWd4ZjA4RkRXeTgKTERxOUhKOUZPbnJnRTJvMU9FTjRRMGpSWU81U041dXFXODd0REEwQ2dZQXpXbk1KSFgrbmlyMjhRRXFyVnJKRAo4ZUEwOHIwWTJRMDhMRlcvMjNIVWQ4WU12VnhTUTdwcUwzaE41RXVJQ2dCbEpGVFI3TndBREo3eDY2M002akFMCm1DNlI4dWxSZStwa08xN2Y0UUs3MnVRanJGZEhESnlXQmdDL0RKSkV6d1dwY0Q4VVNPK3A5bVVIbllLTUJTOEsKTVB1ejYrZ3h0VEtsRU5pZUVacXhxZz09Ci0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS0K
    username: testuser
    password: testpassword
    token: sha256~fFyEqjf1xxFMO0tbEyGRvWeNOd7QByuEgS4hyEq_A9o
    """  # NOQA

    def get_kubeconfig_with_paths(self) -> str:
        """
        This function returns a test kubeconfig file as a string.

        :return: a test kubeconfig file in string format (for unit testing purposes)
        """  # NOQA
        return """apiVersion: v1
clusters:
- cluster:
    certificate-authority: fixtures/ca.crt
    server: https://127.0.0.1:6443
  name: default
contexts:
- context:
    cluster: default
    namespace: default
    user: testuser
  name: default
current-context: default
kind: Config
preferences: {}
users:
- name: testuser
  user:
    client-certificate: fixtures/client.crt
    client-key: fixtures/client.key
    username: testuser
    password: testpassword
    token: sha256~fFyEqjf1xxFMO0tbEyGRvWeNOd7QByuEgS4hyEq_A9o
    """  # NOQA

    def test_current_context(self):
        cwd = os.getcwd()
        current_context_data = ContextAuth()
        data = yaml.safe_load(self.get_kubeconfig_with_data())
        current_context_data.fetch_auth_data(data)
        self.assertIsNotNone(current_context_data.clusterCertificateData)
        self.assertIsNotNone(current_context_data.clientCertificateData)
        self.assertIsNotNone(current_context_data.clientKeyData)
        self.assertIsNotNone(current_context_data.username)
        self.assertIsNotNone(current_context_data.password)
        self.assertIsNotNone(current_context_data.bearerToken)
        self.assertIsNotNone(current_context_data.clusterHost)

        current_context_no_data = ContextAuth()
        data = yaml.safe_load(self.get_kubeconfig_with_paths())
        current_context_no_data.fetch_auth_data(data)
        self.assertIsNotNone(current_context_no_data.clusterCertificate)
        self.assertIsNotNone(current_context_no_data.clusterCertificateData)
        self.assertIsNotNone(current_context_no_data.clientCertificate)
        self.assertIsNotNone(current_context_no_data.clientCertificateData)
        self.assertIsNotNone(current_context_no_data.clientKey)
        self.assertIsNotNone(current_context_no_data.clientKeyData)
        self.assertIsNotNone(current_context_no_data.username)
        self.assertIsNotNone(current_context_no_data.password)
        self.assertIsNotNone(current_context_no_data.bearerToken)
        self.assertIsNotNone(current_context_data.clusterHost)
