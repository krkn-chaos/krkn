import urllib3
import logging
import prometheus_api_client
import sys
import kraken.invoke.command as runcommand

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize the client
def initialize_prom_client(distribution, prometheus_url, prometheus_bearer_token):
    global prom_cli
    prometheus_url, prometheus_bearer_token = instance(distribution, prometheus_url, prometheus_bearer_token)
    if prometheus_url and prometheus_bearer_token:
        bearer = "Bearer " + prometheus_bearer_token
        headers = {"Authorization": bearer}
        try:
            prom_cli = prometheus_api_client.PrometheusConnect(url=prometheus_url, headers=headers, disable_ssl=True)
        except Exception as e:
            logging.error("Not able to initialize the client %s" % e)
            sys.exit(1)
    else:
        prom_cli = None


# Process custom prometheus query
def process_prom_query(query):
    if prom_cli:
        try:
            return prom_cli.custom_query(query=query, params=None)
        except Exception as e:
            logging.error("Failed to get the metrics: %s" % e)
            sys.exit(1)
    else:
        logging.info("Skipping the prometheus query as the prometheus client couldn't " "be initilized\n")

# Get prometheus details
def instance(distribution, prometheus_url, prometheus_bearer_token):
    if distribution == "openshift" and not prometheus_url:
        url = runcommand.invoke(
            r"""oc get routes -n openshift-monitoring -o=jsonpath='{.items[?(@.metadata.name=="prometheus-k8s")].spec.host}'"""  # noqa
        )
        prometheus_url = "https://" + url
    if distribution == "openshift" and not prometheus_bearer_token:
        prometheus_bearer_token = runcommand.invoke(
            "oc create token -n openshift-monitoring prometheus-k8s  --duration=12h "
            "|| oc -n openshift-monitoring sa get-token prometheus-k8s "
            "|| oc sa new-token -n openshift-monitoring prometheus-k8s"
        )
    return prometheus_url, prometheus_bearer_token
