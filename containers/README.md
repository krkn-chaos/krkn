
### Kraken image

Container image gets automatically built by quay.io at [Kraken image](https://quay.io/redhat-chaos/krkn).


### Run containerized version

Refer [instructions](https://krkn-chaos.dev/docs/installation/) for information on how to run the containerized version of kraken.


### Run Custom Kraken Image

Refer to [instructions](https://github.com/redhat-chaos/krkn/blob/main/containers/build_own_image-README.md) for information on how to run a custom containerized version of kraken using podman.

### Check a built image without running a scenario

Set `KRKN_DEPENDENCY_CHECK=1` to check that the installed Python packages have
no declared dependency conflicts and that the Krkn CLI can start. This exits
before SSH setup and does not connect to a cluster or run a chaos scenario.

```sh
docker run --rm -e KRKN_DEPENDENCY_CHECK=1 quay.io/redhat-chaos/krkn:latest
```

Use the same command with the candidate image tag in CI after building or
patching it. This is a smoke check; functional tests still need a separate
disposable Kubernetes cluster.
