<!--
Copyright 2025 The Krkn Authors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# KRKN Chaos Templates

This guide covers the KRKN Chaos Template Library, which provides pre-configured chaos scenarios for quick execution and testing.

## Overview

The KRKN Chaos Template Library offers ready-to-use chaos engineering scenarios that can be easily customized and executed. These templates follow a standardized structure and cover common failure patterns in Kubernetes environments.

## Available Templates

### Core Templates

| Template | Description | Risk Level | Category |
|----------|-------------|------------|----------|
| **pod-failure** | Simulates pod crash to test application resiliency | Medium | Availability |
| **node-failure** | Simulates node failure to test cluster resiliency | High | Availability |
| **network-latency** | Introduces network latency to test performance | Low | Performance |
| **cpu-stress** | Applies CPU stress to test performance under load | Medium | Performance |
| **disk-stress** | Applies disk I/O stress to test storage performance | Medium | Performance |
| **pod-kill** | Forcefully terminates pods to test recovery | Medium | Availability |
| **container-restart** | Restarts containers to test container-level recovery | Low | Availability |
| **vm-outage** | Simulates VM outage for OpenShift Virtualization | High | Availability |
| **resource-failure** | Simulates Kubernetes resource failures | Medium | Availability |

## Quick Start

### Installation

The template system is included with KRKN. No additional installation is required.

### Listing Available Templates

```bash
# Using the template manager directly
python krkn/template_manager.py list

# Using the template wrapper
python krkn-template list
```

### Running a Template

```bash
# Run a template with default parameters
python krkn/template_manager.py run pod-failure

# Or using the template wrapper
python krkn-template run pod-failure
```

### Viewing Template Details

```bash
# Show detailed information about a template
python krkn/template_manager.py show pod-failure

# Include README content
python krkn/template_manager.py show pod-failure --show-readme
```

## Template Customization

### Parameter Overrides

You can customize templates by overriding parameters:

```bash
python krkn/template_manager.py run pod-failure \
  --param name_pattern="^nginx-.*$" \
  --param namespace_pattern="^production$" \
  --param kill=2
```

### Common Parameters

Most templates support these common parameters:

- **name_pattern**: Regex pattern for resource names
- **namespace_pattern**: Regex pattern for namespaces
- **timeout**: Operation timeout in seconds
- **recovery_time**: Recovery monitoring duration

## Template Structure

Each template follows this structure:

```
templates/chaos-scenarios/
└── template-name/
    ├── scenario.yaml      # Main chaos configuration
    ├── metadata.yaml      # Template metadata and parameters
    └── README.md          # Detailed documentation
```

### scenario.yaml

Contains the actual chaos scenario configuration in KRKN format.

### metadata.yaml

Contains template metadata including:

```yaml
name: template-name
description: Brief description of the template
target: kubernetes-pod|kubernetes-node|kubernetes-network
risk_level: low|medium|high
category: availability|performance
version: "1.0"
author: KRKN Team
tags:
  - tag1
  - tag2
estimated_duration: "2-5 minutes"
dependencies: []
parameters:
  - name: parameter_name
    type: string|integer|boolean
    description: Parameter description
    default: default_value
```

### README.md

Comprehensive documentation including:

- Use cases
- Prerequisites
- Usage examples
- Expected behavior
- Customization options
- Troubleshooting guide

## Usage Examples

### Pod Failure Testing

```bash
# Test pod failure with default settings
python krkn-template run pod-failure

# Target specific application
python krkn-template run pod-failure \
  --param name_pattern="^frontend-.*$" \
  --param namespace_pattern="^production$"

# Kill multiple pods
python krkn-template run pod-failure \
  --param kill=3 \
  --param krkn_pod_recovery_time=180
```

### Network Latency Testing

```bash
# Add 100ms latency
python krkn-template run network-latency

# Custom latency settings
python krkn-template run network-latency \
  --param latency="200ms" \
  --param jitter="20ms" \
  --param duration=120
```

### CPU Stress Testing

```bash
# Apply 80% CPU load
python krkn-template run cpu-stress

# High intensity stress
python krkn-template run cpu-stress \
  --param cpu-load-percentage=95 \
  --param duration=300 \
  --param number-of-nodes=2
```

### Node Failure Testing

```bash
# Test single node failure
python krkn-template run node-failure

# Target specific nodes
python krkn-template run node-failure \
  --param label_selector="node-role.kubernetes.io/app=" \
  --param instance_count=1
```

## Best Practices

### Before Running Templates

1. **Test in Non-Production**: Always test templates in development/staging environments first.
2. **Check Prerequisites**: Ensure all prerequisites are met for the target template.
3. **Monitor Resources**: Verify sufficient cluster resources are available.
4. **Backup Data**: Ensure critical data is backed up before running high-risk templates.

### During Execution

1. **Monitor Health**: Watch cluster and application health metrics.
2. **Check Logs**: Monitor KRKN and application logs for issues.
3. **Abort if Necessary**: Stop execution if unexpected issues occur.
4. **Document Results**: Record outcomes and observations.

### After Execution

1. **Verify Recovery**: Ensure all resources have recovered properly.
2. **Review Logs**: Analyze logs for insights and improvements.
3. **Update Configurations**: Adjust application configurations based on results.
4. **Document Learnings**: Record findings for future reference.

## Risk Management

### Risk Levels

- **Low**: Minimal impact, unlikely to cause service disruption
- **Medium**: May cause temporary service disruption
- **High**: Can cause significant service disruption

### Safety Measures

1. **Start Small**: Begin with low-risk templates and low intensity settings.
2. **Gradual Increase**: Slowly increase intensity and complexity.
3. **Time Restrictions**: Run chaos experiments during maintenance windows.
4. **Rollback Plans**: Have clear rollback procedures ready.

## Integration with CI/CD

### GitHub Actions Example

```yaml
- name: Run Chaos Test
  run: |
    python krkn-template run pod-failure \
      --param name_pattern="^app-.*$" \
      --param namespace_pattern="^testing$"
```

### Jenkins Pipeline Example

```groovy
stage('Chaos Test') {
    steps {
        sh 'python krkn-template run network-latency --param latency="50ms"'
    }
}
```

## Troubleshooting

### Common Issues

1. **Template Not Found**: Check template name spelling and templates directory path.
2. **Permission Denied**: Verify RBAC permissions for KRKN service account.
3. **Resource Not Found**: Ensure target resources exist and are accessible.
4. **Timeout Errors**: Increase timeout values for slow clusters.

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
python krkn-template run pod-failure --debug
```

### Log Locations

- KRKN logs: Console output and report files
- Application logs: Kubernetes pod logs
- System logs: Node system logs (if accessible)

## Contributing Templates

### Creating New Templates

1. Create directory under `templates/chaos-scenarios/`
2. Add `scenario.yaml`, `metadata.yaml`, and `README.md`
3. Follow the established structure and naming conventions
4. Test thoroughly before submitting

### Template Guidelines

- Use descriptive names and clear documentation
- Include comprehensive parameter descriptions
- Provide multiple usage examples
- Include troubleshooting sections
- Follow KRKN coding standards

## Support

For issues related to the template system:

1. Check the template README files
2. Review KRKN documentation
3. Search existing GitHub issues
4. Create new issues with detailed information

## Integration with Scenarios Hub

The template system is designed to integrate with the [KRKN Scenarios Hub](https://github.com/krkn-chaos/scenarios-hub). Templates can be contributed to the hub for community sharing and collaboration.
