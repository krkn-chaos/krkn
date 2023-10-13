from prometheus_api_client import PrometheusConnect
import datetime as dt
import urllib3
from datetime import datetime
from tqdm import tqdm


# URL = "https://thanos-querier-openshift-monitoring.apps.bm-prod.comm.ibm.gsc"
URL = "https://thanos-prometheus-openshift-monitoring.chaosai-9ca4d14d48413d18ce61b80811ba4308-0000.eu-gb.containers.appdomain.cloud" #Chaos
#URL = "https://thanos-querier-openshift-monitoring.irl-hcops-cloud-9ca4d14d48413d18ce61b80811ba4308-0000.us-south.containers.appdomain.cloud/api/"

# TOKEN = "sha256~bYo5UAf-Gn5DZYmo0vX6RWSSbk7WLmmZ18_z_pDoWm8"
TOKEN = "sha256~0pkWaTQ-ePKmrMoJF3iCaaFAPMyniL3_TDp-WPLGcFI" #Chaos Cluster
#TOKEN = "sha256~tJZMG5shTPZIp0cjEH-7oxpGpz8uMxx2bDIFlRFmB7k" #HCOps Cluster
urllib3.disable_warnings()
prom = PrometheusConnect(url = URL, headers={'Authorization':'Bearer {}'.format(TOKEN)}, disable_ssl=True)


all_metrics = prom.all_metrics()
print(len(all_metrics))
