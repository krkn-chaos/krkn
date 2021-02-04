## Installation

Following ways are supported to run Kraken:

- Standalone python program through Git
- Containerized version using either Podman or Docker as the runtime
- Kubernetes or OpenShift deployment

**NOTE**: It is recommended to run Kraken external to the cluster ( Standalone or Containerized ) hitting the Kubernetes/OpenShift API as running it internal to the cluster might be disruptive to itself and also might not report back the results if the chaos leads to cluster's API server instability.

**NOTE**: To run Kraken on Power (ppc64le) architecture, build and run a containerized version by following the instructions given [here](https://github.com/openshift-scale/kraken/tree/master/containers/build_own_image-README.md).

### Git

#### Clone the repository
```
$ git clone https://github.com/openshift-scale/kraken.git
$ cd kraken
```

#### Install the dependencies
```
$ pip3 install -r requirements.txt
```

**NOTE**: Make sure python3-devel is installed on the system.

#### Run
```
$ python3 run_kraken.py --config <config_file_location>
```

### Run containerized version
Assuming that the latest docker ( 17.05 or greater with multi-build support ) is intalled on the host, run:
```
$ docker pull quay.io/openshift-scale/kraken:latest
$ docker run --name=kraken --net=host -v <path_to_kubeconfig>:/root/.kube/config -v <path_to_kraken_config>:/root/kraken/config/config.yaml -d quay.io/openshift-scale/kraken:latest
$ docker logs -f kraken
```

Similarly, podman can be used to achieve the same:
```
$ podman pull quay.io/openshift-scale/kraken
$ podman run --name=kraken --net=host -v <path_to_kubeconfig>:/root/.kube/config:Z -v <path_to_kraken_config>:/root/kraken/config/config.yaml:Z -d quay.io/openshift-scale/kraken:latest
$ podman logs -f kraken
```

If you want to build your own kraken image see [here](https://github.com/openshift-scale/kraken/tree/master/containers/build_own_image-README.md)


### Run Kraken as a Kubernetes deployment
Refer [Instructions](https://github.com/openshift-scale/kraken/blob/master/containers/README.md) on how to deploy and run Kraken as a Kubernetes/OpenShift deployment.
