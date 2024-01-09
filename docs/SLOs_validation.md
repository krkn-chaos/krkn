## SLOs validation

Pass/fail based on metrics captured from the cluster is important in addition to checking the health status and recovery. Kraken supports:

###  Checking for critical alerts post chaos 
If enabled, the check runs at the end of each scenario ( post chaos ) and Kraken exits in case critical alerts are firing to allow user to debug. You can enable it in the config:

```
performance_monitoring:
    check_critical_alerts: False                          # When enabled will check prometheus for critical alerts firing post chaos
```

### Validation and alerting based on the queries defined by the user during chaos
Takes PromQL queries as input and modifies the return code of the run to determine pass/fail. It's especially useful in case of automated runs in CI where user won't be able to monitor the system. This feature can be enabled in the [config](https://github.com/redhat-chaos/krkn/blob/main/config/config.yaml) by setting the following:

```
performance_monitoring:
    prometheus_url:                                       # The prometheus url/route is automatically obtained in case of OpenShift, please set it when the distribution is Kubernetes.
    prometheus_bearer_token:                              # The bearer token is automatically obtained in case of OpenShift, please set it when the distribution is Kubernetes. This is needed to authenticate with prometheus.
    enable_alerts: True                                   # Runs the queries specified in the alert profile and displays the info or exits 1 when severity=error.
    alert_profile: config/alerts.yaml                          # Path to alert profile with the prometheus queries.
```

#### Alert profile
A couple of [alert profiles](https://github.com/redhat-chaos/krkn/tree/main/config) [alerts](https://github.com/redhat-chaos/krkn/blob/main/config/alerts.yaml) are shipped by default and can be tweaked to add more queries to alert on. User can provide a URL or path to the file in the [config](https://github.com/redhat-chaos/krkn/blob/main/config/config.yaml). The following are a few alerts examples:

```
- expr: avg_over_time(histogram_quantile(0.99, rate(etcd_disk_wal_fsync_duration_seconds_bucket[2m]))[5m:]) > 0.01
  description: 5 minutes avg. etcd fsync latency on {{$labels.pod}} higher than 10ms {{$value}}
  severity: error

- expr: avg_over_time(histogram_quantile(0.99, rate(etcd_network_peer_round_trip_time_seconds_bucket[5m]))[5m:]) > 0.1
  description: 5 minutes avg. etcd network peer round trip on {{$labels.pod}} higher than 100ms {{$value}}
  severity: info

- expr: increase(etcd_server_leader_changes_seen_total[2m]) > 0
  description: etcd leader changes observed
  severity: critical
```

Kube-burner supports setting the severity for the alerts with each one having different effects:

```
info: Prints an info message with the alarm description to stdout. By default all expressions have this severity.
warning: Prints a warning message with the alarm description to stdout.
error: Prints a error message with the alarm description to stdout and makes kube-burner rc = 1
critical: Prints a fatal message with the alarm description to stdout and exits execution inmediatly with rc != 0
```
