# KRKN Chaos Library

The KRKN Chaos Library provides a collection of pre-defined chaos scenario templates that can be easily executed to test the resiliency of your Kubernetes applications and infrastructure.

## Overview

The Chaos Library is designed to make chaos engineering more accessible by providing ready-to-use scenario templates that follow best practices and can be customized for specific use cases.

## Features

- **Pre-defined Templates**: 10+ chaos scenarios covering common failure modes
- **Easy Execution**: Simple CLI commands to run templates
- **Parameter Customization**: Override template parameters without editing files
- **Validation**: Built-in template validation to ensure correctness
- **Documentation**: Comprehensive documentation for each template

## Available Templates

### 1. Pod Failure
**Risk Level**: Medium  
**Target**: Kubernetes Pods  
**Category**: Availability

Simulates pod crashes to test application resiliency and recovery mechanisms.

```bash
krkn run-template pod-failure
```

### 2. Node Failure
**Risk Level**: High  
**Target**: Kubernetes Nodes  
**Category**: Availability

Simulates node failure to test cluster resiliency and failover mechanisms.

```bash
krkn run-template node-failure
```

### 3. Network Latency
**Risk Level**: Medium  
**Target**: Kubernetes Network  
**Category**: Performance

Introduces network latency to test application performance under degraded network conditions.

```bash
krkn run-template network-latency
```

### 4. CPU Stress
**Risk Level**: Medium  
**Target**: Kubernetes Nodes  
**Category**: Performance

Applies CPU stress to test application performance under high CPU load.

```bash
krkn run-template cpu-stress
```

### 5. Disk Stress
**Risk Level**: Medium  
**Target**: Kubernetes Nodes  
**Category**: Performance

Applies disk I/O stress to test application performance under high disk load.

```bash
krkn run-template disk-stress
```

### 6. Pod Kill
**Risk Level**: High  
**Target**: Kubernetes Pods  
**Category**: Availability

Forcefully kills pods to test application resiliency under various termination conditions.

```bash
krkn run-template pod-kill
```

### 7. Container Restart
**Risk Level**: Medium  
**Target**: Kubernetes Containers  
**Category**: Availability

Restarts containers within pods to test application resiliency at the container level.

```bash
krkn run-template container-restart
```

### 8. VM Outage
**Risk Level**: High  
**Target**: OpenShift VMs  
**Category**: Availability

Simulates VM outage for OpenShift Virtualization environments.

```bash
krkn run-template vm-outage
```

### 9. Resource Failure
**Risk Level**: Medium  
**Target**: Kubernetes Resources  
**Category**: Availability

Simulates Kubernetes resource failures by deleting, modifying, or corrupting various resources.

```bash
krkn run-template resource-failure
```

## CLI Commands

### List Available Templates

View all available chaos scenario templates with their metadata:

```bash
krkn list-templates
```

Output:
```
Available Chaos Scenario Templates:
==================================================
Name: pod-failure
Description: Simulates pod crash to test application resiliency
Target: kubernetes-pod
Risk Level: medium
Category: availability
--------------------------------------------------
Name: node-failure
Description: Simulates node failure to test cluster resiliency
Target: kubernetes-node
Risk Level: high
Category: availability
--------------------------------------------------
...
```

### Run a Template

Execute a chaos scenario template:

```bash
krkn run-template <template-name>
```

Example:
```bash
krkn run-template pod-failure
```

### Customize Template Parameters

Override template parameters using the `--param` flag:

```bash
krkn run-template <template-name> --param <key>=<value>
```

Example:
```bash
krkn run-template pod-failure \
  --param name_pattern="^nginx-.*$" \
  --param namespace_pattern="^production$" \
  --param kill=2 \
  --param krkn_pod_recovery_time=180
```

### Validate Templates

Check if a template is properly configured:

```bash
krkn validate-template <template-name>
```

Example:
```bash
krkn validate-template pod-failure
```

Output:
```
✓ Template 'pod-failure' is valid
```

## Template Structure

Each template follows a standardized structure:

```
templates/chaos-scenarios/
└── <template-name>/
    ├── scenario.yaml      # Chaos scenario configuration
    ├── metadata.yaml      # Template metadata and parameters
    └── README.md          # Template documentation
```

### scenario.yaml
Contains the actual chaos scenario configuration that KRKN executes.

### metadata.yaml
Contains template metadata including:
- `name`: Template identifier
- `description`: What the template does
- `target`: What resources it targets
- `risk_level`: Risk assessment (low/medium/high)
- `category`: Type of chaos (availability/performance/security)
- `parameters`: Configurable parameters with defaults

### README.md
Comprehensive documentation including:
- Usage examples
- Parameter descriptions
- Prerequisites
- Expected behavior
- Cleanup procedures

## Creating Custom Templates

You can create your own templates by following the standard structure:

1. Create a new directory under `templates/chaos-scenarios/`
2. Add the three required files: `scenario.yaml`, `metadata.yaml`, `README.md`
3. Validate your template: `krkn validate-template <your-template>`

### Template Example

```yaml
# scenario.yaml
- id: custom-chaos
  config:
    name_pattern: ^app-.*$
    namespace_pattern: ^default$
    custom_param: "default-value"
```

```yaml
# metadata.yaml
name: custom-chaos
description: Custom chaos scenario for specific testing
target: kubernetes-pod
risk_level: medium
category: availability
parameters:
  - name: name_pattern
    type: string
    description: Regex pattern to match pod names
    default: ^app-.*$
  - name: custom_param
    type: string
    description: Custom parameter for the scenario
    default: "default-value"
```

## Best Practices

### Risk Management
- Start with low-risk templates in development environments
- Always test in non-production environments first
- Monitor your applications during chaos experiments
- Have rollback and recovery procedures in place

### Parameter Customization
- Use specific name patterns to target only intended resources
- Adjust recovery times based on your application's startup time
- Consider the blast radius when setting resource counts

### Monitoring and Observability
- Enable comprehensive monitoring before running chaos scenarios
- Log all chaos experiments for post-mortem analysis
- Set up alerts for critical service degradation

## Integration with CI/CD

The Chaos Library can be integrated into your CI/CD pipelines:

```bash
#!/bin/bash
# Example CI/CD integration script

# Validate templates before execution
krkn validate-template pod-failure
krkn validate-template network-latency

# Run chaos scenarios in staging environment
krkn run-template pod-failure --param namespace_pattern="^staging$"
krkn run-template network-latency --param duration=30

# Check application health after chaos
kubectl wait --for=condition=ready pod -l app=myapp --timeout=300s
```

## Troubleshooting

### Common Issues

1. **Template not found**: Ensure the template directory exists and contains required files
2. **Permission denied**: Check Kubernetes RBAC permissions for the service account
3. **Parameter validation failed**: Verify parameter types and values
4. **Scenario execution failed**: Check logs for detailed error messages

### Debug Mode

Enable debug logging for troubleshooting:

```bash
krkn --debug run-template pod-failure
```

### Template Validation

Always validate templates before use:

```bash
krkn validate-template <template-name>
```

## Contributing

To contribute new templates to the Chaos Library:

1. Follow the template structure and naming conventions
2. Include comprehensive documentation
3. Add appropriate risk assessments
4. Test templates in various environments
5. Submit a pull request with your template

## Support

For questions or issues with the Chaos Library:

- Check the [KRKN documentation](https://krkn-chaos.dev/docs/)
- Review existing templates for examples
- Open an issue on the [KRKN GitHub repository](https://github.com/krkn-chaos/krkn)
- Join the community discussions on [Kubernetes Slack](https://kubernetes.slack.com/messages/C05SFMHRWK1)
