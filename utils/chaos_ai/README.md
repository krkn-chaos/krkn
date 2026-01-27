# ⚠️ DEPRECATED - This project has moved

> **All development has moved to [github.com/krkn-chaos/krkn-ai](https://github.com/krkn-chaos/krkn-ai)**
>
> This directory is no longer maintained. Please visit the new repository for:
> - Latest features and updates
> - Active development and support
> - Bug fixes and improvements
> - Documentation and examples
>
> See [../README.md](../README.md) for more information.

---

# aichaos
Enhancing Chaos Engineering with AI-assisted fault injection for better resiliency and non-functional testing.

## Generate python package wheel file
```
$ python3.9 generate_wheel_package.py sdist bdist_wheel
$ cp dist/aichaos-0.0.1-py3-none-any.whl docker/
```
This creates a python package file aichaos-0.0.1-py3-none-any.whl in the dist folder. 

## Build Image
```
$ cd docker
$ podman build -t aichaos:1.0 .
OR
$ docker build -t aichaos:1.0 .
```

## Run Chaos AI
```
$ podman run -v aichaos-config.json:/config/aichaos-config.json --privileged=true --name aichaos -p 5001:5001 aichaos:1.0
OR
$ docker run -v aichaos-config.json:/config/aichaos-config.json --privileged -v /var/run/docker.sock:/var/run/docker.sock --name aichaos -p 5001:5001 aichaos:1.0
```

The output should look like:
```
$ podman run -v aichaos-config.json:/config/aichaos-config.json --privileged=true --name aichaos -p 5001:5001 aichaos:1.0
 * Serving Flask app 'swagger_api' (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5001
 * Running on http://172.17.0.2:5001
```

You can try out the APIs in browser at http://<server-ip>:5001/apidocs (eg. http://127.0.0.1:5001/apidocs). For testing out, you can try “GenerateChaos” api with ‘kubeconfig’ file and application URLs to test.
