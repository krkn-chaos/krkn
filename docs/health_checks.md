### Health Checks

Health checks provide real-time visibility into the impact of chaos scenarios on application availability and performance. 
Health checks are configured in the ```config.yaml```For applications requiring authentication bearer tokens and credentials can be configured.

The system periodically checks the provided URLs based on the defined interval and records the results in Telemetry. The telemetry data includes:

- Success response ```200``` when the application is running normally.
- Failure response other than 200 if the application experiences downtime or errors.

This helps users quickly identify application health issues and take necessary actions.

#### Sample health check config
```
health_checks:
  interval: <time_in_seconds>                       # Defines the frequency of health checks, default value is 2 seconds
  config:                                           # List of application endpoints to check
    - url: "http://example.com/health"
      bearer_token:                                 # Bearer token for authentication if any
      auth:                                         # Provide authentication credentials (username , password) in tuple format if any, ex:("admin","secretpassword")
      exit_on_failure:                              # Exit when health check failed for application, value can be True/False
    - url: "http://another-service.com/status"
      bearer_token:
      auth:
      exit_on_failure:
```
#### Sample health check telemetry
```
"health_checks": [
            {
                "url": "http://example.com/health",
                "status": false,
                "status_code": "503",
                "start_timestamp": "2025-02-25 11:51:33",
                "end_timestamp": "2025-02-25 11:51:40",
                "duration": "0:00:07"
            },
            {
                "url": "http://another-service.com/status",
                "status": true,
                "status_code": 200,
                "start_time_stamp": "2025-02-25 22:18:19",
                "end_timestamp": "22025-02-25 22:22:46",
                "duration": "0:04:27"
            }
        ],
```