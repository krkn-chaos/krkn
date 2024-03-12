## Installation

The following ways are supported to run Kraken:

- Standalone python program through Git.
- Containerized version using either Podman or Docker as the runtime via [Krkn-hub](https://github.com/krkn-chaos/krkn-hub)
- Kubernetes or OpenShift deployment ( unsupported )

**NOTE**: It is recommended to run Kraken external to the cluster ( Standalone or Containerized ) hitting the Kubernetes/OpenShift API as running it internal to the cluster might be disruptive to itself and also might not report back the results if the chaos leads to cluster's API server instability.

**NOTE**: To run Kraken on Power (ppc64le) architecture, build and run a containerized version by following the
 instructions given [here](https://github.com/krkn-chaos/krkn/blob/main/containers/build_own_image-README.md).

**NOTE**: Helper functions for interactions in Krkn are part of [krkn-lib](https://github.com/redhat-chaos/krkn-lib). 
Please feel free to reuse and expand them as you see fit when adding a new scenario or expanding 
the capabilities of the current supported scenarios.


### Git

#### Clone the repository
Pick the latest stable release to install [here](https://github.com/krkn-chaos/krkn/releases).
```
$ git clone https://github.com/krkn-chaos/krkn.git --branch <release version>
$ cd krkn
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
[Krkn-hub](https://github.com/krkn-chaos/krkn-hub) is a wrapper that allows running Krkn chaos scenarios via podman or docker runtime with scenario parameters/configuration defined as environment variables.

Refer [instructions](https://github.com/krkn-chaos/krkn-hub#supported-chaos-scenarios) to get started.


### Run Kraken as a Kubernetes deployment ( unsupported option - standalone or containerized deployers are recommended )
Refer [Instructions](https://github.com/krkn-chaos/krkn/blob/main/containers/README.md) on how to deploy and run Kraken as a Kubernetes/OpenShift deployment.


Refer to the [chaos-kraken chart manpage](https://artifacthub.io/packages/helm/startx/chaos-kraken)
and especially the [kraken configuration values](https://artifacthub.io/packages/helm/startx/chaos-kraken#chaos-kraken-values-dictionary) 
for details on how to configure this chart.
