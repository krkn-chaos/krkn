import kraken.invoke.command as runcommand


# Get prometheus details
def instance(distribution, prometheus_url, prometheus_bearer_token):
    if distribution == "openshift" and not prometheus_url:
        url = runcommand.invoke(
            r"""oc get routes -n openshift-monitoring -o=jsonpath='{.items[?(@.metadata.name=="prometheus-k8s")].spec.host}'"""  # noqa
        )
        prometheus_url = "https://" + url
    if distribution == "openshift" and not prometheus_bearer_token:
        prometheus_bearer_token = runcommand.invoke("oc -n openshift-monitoring " "sa get-token prometheus-k8s")
    return prometheus_url, prometheus_bearer_token
