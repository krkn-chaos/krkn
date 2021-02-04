# Building your own Kraken image

1. Git clone the Kraken repository using `git clone https://github.com/openshift-scale/kraken.git`.
2. Modify the python code and yaml files to address your needs.
3. Execute `podman build -t <new_image_name>:latest .` in the containers directory within kraken to build an image from a Dockerfile.
4. Execute `podman run --detach --name <container_name> <new_image_name>:latest` to start a container based on your new image.

# Building the Kraken image on IBM Power (ppc64le)

1. Git clone the Kraken repository using `git clone https://github.com/cloud-bulldozer/kraken.git` on an IBM Power Systems server.
2. Modify the python code and yaml files to address your needs.
3. Execute `podman build -t <new_image_name>:latest -f Dockerfile-ppc64le` in the containers directory within kraken to build an image from the Dockerfile for Power.
4. Execute `podman run --detach --name <container_name> <new_image_name>:latest` to start a container based on your new image.