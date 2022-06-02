import requests as requests

from kraken.health.cerberus.config import CerberusConfig
from kraken.health.health import HealthChecker, HealthCheckDecision


class CerberusHealthChecker(HealthChecker):
    def __init__(self, config: CerberusConfig):
        self._config = config

    def check(self) -> HealthCheckDecision:
        cerberus_status = requests.get(self._config.cerberus_url, timeout=60).content
        return HealthCheckDecision.GO if cerberus_status == b"True" else HealthCheckDecision.STOP
