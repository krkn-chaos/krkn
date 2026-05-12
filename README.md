# Krkn aka Kraken
![Workflow-Status](https://github.com/krkn-chaos/krkn/actions/workflows/docker-image.yml/badge.svg)
![coverage](https://krkn-chaos.github.io/krkn-lib-docs/coverage_badge_krkn.svg)
![action](https://github.com/krkn-chaos/krkn/actions/workflows/tests.yml/badge.svg)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/10548/badge)](https://www.bestpractices.dev/projects/10548)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/krkn-chaos/krkn/badge)](https://scorecard.dev/viewer/?uri=github.com/krkn-chaos/krkn)
[![CLOMonitor](https://img.shields.io/endpoint?url=https://clomonitor.io/api/projects/cncf/krkn/badge)](https://clomonitor.io/projects/cncf/krkn)

![Krkn logo](media/logo.png)

Chaos and resiliency testing tool for Kubernetes.
Kraken injects deliberate failures into Kubernetes clusters to check if it is resilient to turbulent conditions.

## 🚀 New: Chaos Template Library

KRKN now includes a comprehensive **Chaos Template Library** with pre-configured scenarios for quick execution:

- **Pod Failure**: Test application restart policies
- **Node Failure**: Validate cluster self-healing  
- **Network Latency**: Test performance under poor network
- **CPU/Disk Stress**: Identify resource bottlenecks
- **VM Outage**: OpenShift Virtualization testing
- And more!

### Quick Start with Templates

```bash
# List available templates
python krkn/template_manager.py list

# Run a pod failure test
python krkn/template_manager.py run pod-failure

# Customize with parameters
python krkn/template_manager.py run network-latency --param latency="200ms"
```

📖 **[Full Template Documentation](docs/chaos-templates.md)**


### Workflow
![Kraken workflow](media/kraken-workflow.png) 


<!-- ### Demo
[![Kraken demo](media/KrakenStarting.png)](https://youtu.be/LN-fZywp_mo "Kraken Demo - Click to Watch!") -->


### How to Get Started
Instructions on how to setup, configure and run Kraken can be found in the [documentation](https://krkn-chaos.dev/docs/).


### Blogs, podcasts and interviews
Additional resources, including blog posts, podcasts, and community interviews, can be found on the [website](https://krkn-chaos.dev/blog)


### Roadmap
Enhancements being planned can be found in the [roadmap](ROADMAP.md).


### Contributing
We are always looking for more enhancements, fixes to make it better, any contributions are most welcome. Feel free to report or work on the issues filed on github.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details, or check the [contribution guidelines](https://krkn-chaos.dev/docs/contribution-guidelines/) on the website.


### Community
Key Members(slack_usernames/full name): paigerube14/Paige Rubendall, mffiedler/Mike Fiedler, tsebasti/Tullio Sebastiani, yogi/Yogananth Subramanian, sahil/Sahil Shah, pradeep/Pradeep Surisetty and ravielluri/Naga Ravi Chaitanya Elluri.
* [**#krkn on Kubernetes Slack**](https://kubernetes.slack.com/messages/C05SFMHRWK1)


### Community Meeting
If you have any questions that you think could be better discussed on a meeting, we have [monthly office hours](https://zoom-lfx.platform.linuxfoundation.org/meetings/krkn?view=month). Please add items to the agenda beforehand so we can best prepare to help you.

The Linux Foundation® (TLF) has registered trademarks and uses trademarks. For a list of TLF trademarks, see [Trademark Usage](https://www.linuxfoundation.org/legal/trademark-usage).
