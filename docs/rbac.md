Following is the compilation of all the rbac config required to run [run_kraken](https://github.com/redhat-chaos/krkn/blob/main/run_kraken.py) and each of the krkn test scenarios.

> **_NOTE:_** Below configuration assumes the user executing the krkrkn as `user1` and the user would be using the namespace `testnamespace` to test his application and run krn tests.

## [run_kraken](https://github.com/redhat-chaos/krkn/blob/main/run_kraken.py)

Allow the user to query prometheus metrics and get infrastructure,network level details.

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
openshift-monitoring   |  ""        |  "serviceaccounts/token" |   "create"
clusterRole    | "config.openshift.io"               | "networks","infrastructures","clusterversions" | "get","list"  

Allow the use user1 to view resources in test1 namespace
```
kubectl create rolebinding view-role-binding --clusterrole=view --user=user1 --namespace=testnamespace
```

## [Pod Scenarios](docs/pod_scenarios.md)

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods"    | "delete"


## [Container Scenarios](docs/container_scenarios.md) 

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec" | "get","create","delete"

## [Service Disruption Scenarios](docs/service_disruption_scenarios.md.md) 

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec","services" | "get","create","delete"
testnamespace    | "apps"           | "daemonsets","statefulsets","replicasets","deployments" | "get","delete"

## [Application_outages](docs/application_outages.md)

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | "networking.k8s.io"         | "networkpolicies" | "get","create","delete"

## [PVC scenario](docs/pvc_scenario.md)

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec" | "get","create","delete"

## [Time Scenarios](docs/time_scenarios.md)

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec" | "get","create","delete"

> ## **_NOTE:_** Grant the privileged SCC to the user running the pod, to execute all the below krkn testscenarios
```
oc adm policy add-scc-to-user privileged user1
```

## [Hog Scenarios: CPU, Memory](docs/hog_scenarios.md)

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec" | "get","create","delete"
clusterRole    | ""               | "nodes","nodes/proxy" | "list","get"

## [Network_Chaos](docs/network_chaos.md)

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec" | "get","create","delete"
testnamespace    | "batch"              | "jobs" | "get","delete","list","create"
clusterRole    | ""               | "nodes","nodes/proxy" | "list","get"

## [Pod Network Scenarios](docs/pod_network_scenarios.md)

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec" | "get","create","delete"
testnamespace    | "batch"              | "jobs" | "get","delete","list","create"
clusterRole    | ""               | "nodes","nodes/proxy" | "list","get"
clusterRole    | "apiextensions.k8s.io"              | "customresourcedefinitions" | "get", "list", "watch"
clusterRole    | "config.openshift.io"               | "networks" | "get"

## Compounded list of all rbac rules

namespace/clusterRole  | apigroups  | resources | verb    
---------------------- | ---------- | --------- | ----
testnamespace    | ""               | "pods","pods/exec","services" | "get","create","delete"
testnamespace    | "batch"              | "jobs" | "get","delete","list","create"
clusterRole    | ""               | "nodes","nodes/proxy" | "list","get"
clusterRole    | "apiextensions.k8s.io"              | "customresourcedefinitions" | "get", "list", "watch"
clusterRole    | "config.openshift.io"               | "networks","infrastructures","clusterversions" | "get","list"