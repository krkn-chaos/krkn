# KRKN Chaos Scenario Templates

This directory contains the KRKN Chaos Template Library - a collection of pre-configured chaos engineering scenarios for quick execution and testing.

## Available Templates

### 📦 Availability Templates

#### [pod-failure](pod-failure/)
- **Description**: Simulates pod crash to test application resiliency
- **Risk Level**: Medium
- **Target**: Kubernetes Pods
- **Use Case**: Test restart policies and self-healing

#### [node-failure](node-failure/)
- **Description**: Simulates node failure to test cluster resiliency
- **Risk Level**: High
- **Target**: Kubernetes Nodes
- **Use Case**: Test cluster self-healing and pod redistribution

#### [pod-kill](pod-kill/)
- **Description**: Forcefully terminates pods to test recovery mechanisms
- **Risk Level**: Medium
- **Target**: Kubernetes Pods
- **Use Case**: Test graceful shutdown and restart

#### [container-restart](container-restart/)
- **Description**: Restarts containers within pods to test container-level recovery
- **Risk Level**: Low
- **Target**: Kubernetes Containers
- **Use Case**: Test multi-container pod resilience

#### [vm-outage](vm-outage/)
- **Description**: Simulates VM outage for OpenShift Virtualization
- **Risk Level**: High
- **Target**: OpenShift VMs
- **Use Case**: Test VM recovery and high availability

#### [resource-failure](resource-failure/)
- **Description**: Simulates Kubernetes resource failures
- **Risk Level**: Medium
- **Target**: Kubernetes Resources
- **Use Case**: Test resource recreation procedures

### ⚡ Performance Templates

#### [network-latency](network-latency/)
- **Description**: Introduces network latency to test performance
- **Risk Level**: Low
- **Target**: Network Traffic
- **Use Case**: Test timeout handling and retry mechanisms

#### [cpu-stress](cpu-stress/)
- **Description**: Applies CPU stress to test performance under load
- **Risk Level**: Medium
- **Target**: Node CPU Resources
- **Use Case**: Test performance bottlenecks and auto-scaling

#### [disk-stress](disk-stress/)
- **Description**: Applies disk I/O stress to test storage performance
- **Risk Level**: Medium
- **Target**: Node Disk I/O
- **Use Case**: Test storage performance and I/O bottlenecks

## Quick Usage

### List All Templates
```bash
python run_kraken.py list
```

### Run a Template
```bash
# Basic usage
python run_kraken.py run pod-failure

# With custom parameters
python run_kraken.py run network-latency --param latency="200ms"
```

### Get Template Details
```bash
python run_kraken.py show pod-failure
```

## Template Structure

Each template follows this standardized structure:

```
template-name/
├── scenario.yaml      # Chaos scenario configuration
├── metadata.yaml      # Template metadata and parameters
└── README.md          # Detailed documentation
```

## Risk Levels

- **🟢 Low**: Minimal impact, unlikely to cause service disruption
- **🟡 Medium**: May cause temporary service disruption
- **🔴 High**: Can cause significant service disruption

## Categories

- **Availability**: Tests system availability and recovery mechanisms
- **Performance**: Tests system performance under stress conditions

## Best Practices

1. **Start with Low Risk**: Begin with low-risk templates to understand the impact
2. **Test in Staging**: Always test in non-production environments first
3. **Monitor Health**: Watch cluster and application health during execution
4. **Have Rollback Plans**: Ensure you can quickly recover from failures
5. **Document Results**: Record outcomes and observations for future reference

## Contributing

To contribute new templates:

1. Create a new directory following the naming convention
2. Add all required files (scenario.yaml, metadata.yaml, README.md)
3. Follow the established structure and documentation standards
4. Test thoroughly in multiple environments
5. Submit a pull request with detailed description

## Integration with Scenarios Hub

These templates are designed to integrate with the [KRKN Scenarios Hub](https://github.com/krkn-chaos/scenarios-hub) for community sharing and collaboration.

## Support

For template-specific issues:

1. Check the individual template README files
2. Review the [main documentation](../../docs/chaos-templates.md)
3. Search existing GitHub issues
4. Create new issues with template name and detailed information
