## Performance dashboards

Kraken supports installing a mutable grafana on the cluster with the dashboards loaded to help with monitoring the cluster for things like resource usage to find the outliers, API stats, Etcd health, Critical alerts etc. It can be deployed by enabling the following in the config:

```
performance_monitoring:
    deploy_dashboards: True
```

The route and credentials to access the dashboards will be printed on the stdout before Kraken starts creating chaos. The dashboards can be edited/modified to include your queries of interest.

**NOTE**: The dashboards leverage Prometheus for scraping the metrics off of the cluster and currently only supports OpenShift since Prometheus is setup on the cluster by default and leverages routes object to expose the grafana dashboards externally.
