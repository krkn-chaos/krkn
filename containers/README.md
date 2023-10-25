
### Kraken image

Container image gets automatically built by quay.io at [Kraken image](https://quay.io/redhat-chaos/krkn).


### Run containerized version

Refer [instructions](https://github.com/redhat-chaos/krkn/blob/main/docs/installation.md#run-containerized-version) for information on how to run the containerized version of kraken.


### Run Custom Kraken Image

Refer to [instructions](https://github.com/redhat-chaos/krkn/blob/main/containers/build_own_image-README.md) for information on how to run a custom containerized version of kraken using podman.


### Kraken as a KubeApp ( Unsupported and not recommended )

#### GENERAL NOTES:

- It is not generally recommended to run Kraken internal to the cluster as the pod which is running Kraken might get disrupted, the suggested use case to run kraken from inside k8s/OpenShift is to target **another** cluster (eg. to bypass network restrictions or to leverage cluster's computational resources)

- your kubeconfig might contain several cluster contexts and credentials so be sure, before creating the ConfigMap, to keep **only** the credentials related to the destination cluster. Please refer to the [Kubernetes documentation](https://kubernetes.io/docs/tasks/access-application-cluster/configure-access-multiple-clusters/) for more details
- to add privileges to the service account you must be logged in the cluster with an highly privileged account (ideally kubeadmin)

  

To run containerized Kraken as a Kubernetes/OpenShift Deployment, follow these steps:

1. Configure the [config.yaml](https://github.com/redhat-chaos/krkn/blob/main/config/config.yaml) file according to your requirements.

**NOTE**: both the scenarios ConfigMaps are needed regardless you're running kraken in Kubernetes or OpenShift

2. Create a namespace under which you want to run the kraken pod using `kubectl create ns <namespace>`.
3. Switch to `<namespace>` namespace:
- In Kubernetes, use `kubectl config set-context --current --namespace=<namespace>`
- In OpenShift, use `oc project <namespace>`
  
4. Create a ConfigMap named kube-config using `kubectl create configmap kube-config --from-file=<path_to_kubeconfig>`  *(eg. ~/.kube/config)*
5. Create a ConfigMap named kraken-config using `kubectl create configmap kraken-config --from-file=<path_to_kraken>/config`
6. Create a ConfigMap named scenarios-config using `kubectl create configmap scenarios-config --from-file=<path_to_kraken>/scenarios`
7. Create a ConfigMap named scenarios-openshift-config using `kubectl create configmap scenarios-openshift-config --from-file=<path_to_kraken>/scenarios/openshift`
8. Create a ConfigMap named scenarios-kube-config using `kubectl create configmap scenarios-kube-config --from-file=<path_to_kraken>/scenarios/kube` 
9. Create a service account to run the kraken pod `kubectl create serviceaccount useroot`.
10.  In Openshift, add privileges to service account and execute `oc adm policy add-scc-to-user privileged -z useroot`.
11.  Create a Job using `kubectl apply -f <path_to_kraken>/containers/kraken.yml` and monitor the status using `oc get jobs` and `oc get pods`.
