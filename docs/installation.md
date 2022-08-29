## Installation

The following ways are supported to run Kraken:

- Standalone python program through Git.
- Containerized version using either Podman or Docker as the runtime.
- Kubernetes or OpenShift deployment.
- Using chaos-kraken helm chart.

**NOTE**: It is recommended to run Kraken external to the cluster ( Standalone or Containerized ) hitting the Kubernetes/OpenShift API as running it internal to the cluster might be disruptive to itself and also might not report back the results if the chaos leads to cluster's API server instability.

**NOTE**: To run Kraken on Power (ppc64le) architecture, build and run a containerized version by following the
 instructions given [here](https://github.com/chaos-kubox/krkn/blob/main/containers/build_own_image-README.md).

### Git

#### Clone the repository
Pick the latest stable release to install [here](https://github.com/redhat-chaos/krkn/releases).
```
$ git clone https://github.com/redhat-chaos/krkn.git --branch <release version>
$ cd kraken
```

#### Install the dependencies
```
$ python3.9 -m venv chaos
$ source chaos/bin/activate
$ pip3.9 install -r requirements.txt
```

**NOTE**: Make sure python3-devel and latest pip versions are installed on the system. The dependencies install has been tested with pip >= 21.1.3 versions.

#### Run
```
$ python3.9 run_kraken.py --config <config_file_location>
```

### Run containerized version
Assuming that the latest docker ( 17.05 or greater with multi-build support ) is installed on the host, run:
```
$ docker pull quay.io/chaos-kubox/krkn:latest
$ docker run --name=kraken --net=host -v <path_to_kubeconfig>:/root/.kube/config:Z -v <path_to_kraken_config>:/root/kraken/config/config.yaml:Z -d quay.io/chaos-kubox/krkn:latest
$ docker run --name=kraken --net=host -v <path_to_kubeconfig>:/root/.kube/config:Z -v <path_to_kraken_config>:/root/kraken/config/config.yaml:Z -v <path_to_scenarios_directory>:/root/kraken/scenarios:Z -d quay.io/chaos-kubox/krkn:latest #custom or tweaked scenario configs
$ docker logs -f kraken
```

Similarly, podman can be used to achieve the same:
```
$ podman pull quay.io/chaos-kubox/krkn
$ podman run --name=kraken --net=host -v <path_to_kubeconfig>:/root/.kube/config:Z -v <path_to_kraken_config>:/root/kraken/config/config.yaml:Z -d quay.io/chaos-kubox/krkn:latest
$ podman run --name=kraken --net=host -v <path_to_kubeconfig>:/root/.kube/config:Z -v <path_to_kraken_config>:/root/kraken/config/config.yaml:Z -v <path_to_scenarios_directory>:/root/kraken/scenarios:Z -d quay.io/chaos-kubox/krkn:latest #custom or tweaked scenario configs
$ podman logs -f kraken
```

If you want to build your own kraken image see [here](https://github.com/chaos-kubox/krkn/blob/main/containers/build_own_image-README.md)


### Run Kraken as a Kubernetes deployment
Refer [Instructions](https://github.com/chaos-kubox/krkn/blob/main/containers/README.md) on how to deploy and run Kraken as a Kubernetes/OpenShift deployment.


### Deploying kraken using a helm-chart

You can find on [artifacthub.io](https://artifacthub.io/packages/search?kind=0&ts_query_web=kraken) the 
[chaos-kraken](https://artifacthub.io/packages/helm/startx/chaos-kraken) `helm-chart`
which can be used to deploy a kraken chaos scenarios.

Default configuration create the following resources :

  - 1 project named **chaos-kraken**
  - 1 scc with privileged context for kraken deployment
  - 1 configmap with kraken 21 generic scenarios, various scripts and configuration
  - 1 configmap with kubeconfig of the targeted cluster
  - 1 job named kraken-test-xxx
  - 1 service to the kraken pods
  - 1 route to the kraken service

```bash
# Install the startx helm repository
helm repo add startx https://startxfr.github.io/helm-repository/packages/
# Install the kraken project
helm install --set project.enabled=true chaos-kraken-project  startx/chaos-kraken
# Deploy the kraken instance
helm install \
--set kraken.enabled=true \
--set kraken.aws.credentials.region="eu-west-3" \
--set kraken.aws.credentials.key_id="AKIAXXXXXXXXXXXXXXXX" \
--set kraken.aws.credentials.secret="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
--set kraken.kubeconfig.token.server="https://api.mycluster:6443" \
--set kraken.kubeconfig.token.token="sha256~XXXXXXXXXX_PUT_YOUR_TOKEN_HERE_XXXXXXXXXXXX" \
-n chaos-kraken \
chaos-kraken-instance startx/chaos-kraken
```

Refer to the [chaos-kraken chart manpage](https://artifacthub.io/packages/helm/startx/chaos-kraken)
and especially the [kraken configuration values](https://artifacthub.io/packages/helm/startx/chaos-kraken#chaos-kraken-values-dictionary) 
for details on how to configure this chart.