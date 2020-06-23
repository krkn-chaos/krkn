### Kraken image

Container image gets automatically built by quay.io at [Kraken image](https://quay.io/repository/openshift-scale/kraken). 

### Run containerized version
Refer [instructions](https://github.com/openshift-scale/kraken#Run-containerized-version) for information on how to run the containerized version of kraken.


### Kraken as a KubeApp

To run containerized Kraken as a Kubernetes/OpenShift Deployment, follow these steps:
1. Configure the [config.yaml](https://github.com/openshift-scale/kraken/tree/master/config/config.yaml) file according to your requirements.
2. Create a namespace under which you want to run the kraken pod using `kubectl create ns <namespace>`.
3. Switch to `<namespace>` namespace:
    - In Kubernetes, use `kubectl config set-context --current --namespace=<namespace>`
    - In OpenShift, use `oc project <namespace>`
4. Create a ConfigMap named kube-config using `kubectl create configmap kube-config --from-file=<path_to_kubeconfig>`
5. Create a ConfigMap named kraken-config using `kubectl create configmap kraken-config --from-file=<path_to_kraken_config>`
6. Create a ConfigMap named scenarios-config using `kubectl create configmap scenarios-config --from-file=<path_to_scenarios_folder>`
7. Create a serviceaccount to run the kraken pod `kubectl create serviceaccount useroot`.
8. In Openshift, add privileges to service account and execute `oc adm policy add-scc-to-user privileged -z useroot`.
9. Create a Deployment and a NodePort Service using `kubectl apply -f kraken.yml`

NOTE: It is not recommended to run Kraken internal to the cluster as the pod which is running Kraken might get disrupted.