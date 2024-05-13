### Service Hijacking Scenarios

Service Hijacking Scenarios aim to simulate fake HTTP responses from a workload targeted by a 
`Service` already deployed in the cluster. 
This scenario is executed by deploying a custom-made web service and modifying the target `Service`
selector to direct traffic to this web service for a specified duration.

The web service will utilize a time-based test plan loaded from the scenario configuration file, 
which outlines the behavior of resources during the chaos scenario, defined as follows:

```yaml
service_target_port: http-web-svc # The port of the service to be hijacked (can be named or numeric, based on the workload and service configuration).
service_name: nginx-service # The name of the service that will be hijacked.
service_namespace: default # The namespace where the target service is located.
image: quay.io/krkn-chaos/krkn-service-hijacking:v0.1.3 # Image of the krkn web service to be deployed to receive traffic.
chaos_duration: 30 # Total duration of the chaos scenario in seconds.
plan:
  - resource: "/list/index.php" # Specifies the resource or path to respond to in the scenario. For paths, both the path and query parameters are captured but ignored. For resources, only query parameters are captured.

    steps:                      # A time-based plan consisting of steps can be defined for each resource.
      GET:                      # One or more HTTP methods can be specified for each step. Note: Non-standard methods are supported for fully custom web services (e.g., using NONEXISTENT instead of POST).

        - duration: 15          # Duration in seconds for this step before moving to the next one, if defined. Otherwise, this step will continue until the chaos scenario ends.

          status: 500           # HTTP status code to be returned in this step.
          mime_type: "application/json" # MIME type of the response for this step.
          payload: |            # The response payload for this step.
            {
              "status":"internal server error"
            }
        - duration: 15
          status: 201
          mime_type: "application/json"
          payload: |
            {
              "status":"resource created"
            }
      POST:
        - duration: 15
          status: 401
          mime_type: "application/json"
          payload: |
            {
               "status": "unauthorized"
            }
        - duration: 15
          status: 404
          mime_type: "text/plain"
          payload: "not found"


```
The scenario will focus on the `service_name` within the `service_namespace`, 
substituting the selector with a randomly generated one, which is added as a label in the mock service manifest.
This allows multiple scenarios to be executed in the same namespace, each targeting different services without 
causing conflicts.

The newly deployed mock web service will expose a `service_target_port`, 
which can be either a named or numeric port based on the service configuration. 
This ensures that the Service correctly routes HTTP traffic to the mock web service during the chaos run.

Each step will last for `duration` seconds from the deployment of the mock web service in the cluster. 
For each HTTP resource, defined as a top-level YAML property of the plan 
(it could be a specific resource, e.g., /list/index.php, or a path-based resource typical in MVC frameworks), 
one or more HTTP request methods can be specified. Both standard and custom request methods are supported.

During this time frame, the web service will respond with:

- `status`: The [HTTP status code](https://datatracker.ietf.org/doc/html/rfc7231#section-6) (can be standard or custom).
- `mime_type`: The [MIME type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types) (can be standard or custom).
- `payload`: The response body to be returned to the client.

At the end of the step `duration`, the web service will proceed to the next step (if available) until 
the global `chaos_duration` concludes. At this point, the original service will be restored, 
and the custom web service and its resources will be undeployed.

__NOTE__: Some clients (e.g., cURL, jQuery) may optimize queries using lightweight methods (like HEAD or OPTIONS) 
to probe API behavior. If these methods are not defined in the test plan, the web service may respond with 
a `405` or `404` status code. If you encounter unexpected behavior, consider this use case.

