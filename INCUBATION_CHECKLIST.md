# Review Project Moving Level Evaluation
[x] I have reviewed the TOC's [moving level readiness triage guide](https://github.com/cncf/toc/blob/main/operations/dd-toc-guide.md#initial-triageevaluation-prior-to-assignment), ensured the criteria for my project are met before opening this issue, and understand that unmet criteria will result in the project's application being closed.

# Krkn Incubation Application
v1.6
This template provides the project with a framework to inform the TOC of their conformance to the Incubation Level Criteria. 

Project Repo(s): https://github.com/krkn-chaos/krkn
Project Site:  https://www.krkn-chaos.dev 
Sub-Projects: 
 - https://github.com/krkn-chaos/krknctl
 - https://github.com/krkn-chaos/krkn-hub
Communication: [Slack](https://kubernetes.slack.com/archives/C05SFMHRWK1)


Project points of contacts: 
 - [Naga Ravi Elluri](mailto:nelluri@redhat.com)
 - [Paige Patton](mailto:ppatton@redhat.com)
 - [Tullio Sebastiani](mailto:tsebasti@redhat.com)

- [ ] (Post Incubation only) [Book a meeting with CNCF staff](http://project-meetings.cncf.io) to understand project benefits and event resources. 

## Incubation Criteria Summary for Krkn

### Application Level Assertion

- [x] This project is currently Sandbox, accepted on 2023/12/19, and applying to Incubation.
- [x] This project is applying to join the CNCF at the Incubation level.

### Adoption Assertion

_The project has been adopted by the following organizations in a testing and integration or production capacity:_

| Organization | Since | Website | Use-Case |
|:-|:-|:-|:-|
| MarketAxess | 2024 | https://www.marketaxess.com/ | Kraken enables us to achieve our goal of increasing the reliability of our cloud products on Kubernetes. The tool allows us to automatically run various chaos scenarios, identify resilience and performance bottlenecks, and seamlessly restore the system to its original state once scenarios finish. These chaos scenarios include pod disruptions, node (EC2) outages, simulating availability zone (AZ) outages, and filling up storage spaces like EBS and EFS. The community is highly responsive to requests and works on expanding the tool's capabilities. MarketAxess actively contributes to the project, adding features such as the ability to leverage existing network ACLs and proposing several feature improvements to enhance test coverage. |
| Red Hat Openshift | 2020 | https://www.redhat.com/ | Kraken is a highly reliable chaos testing tool used to ensure the quality and resiliency of Red Hat Openshift. The engineering team runs all the test scenarios under Kraken on different cloud platforms on both self-managed and cloud services environments prior to the release of a new version of the product. The team also contributes to the Kraken project consistently which helps the test scenarios to keep up with the new features introduced to the product. Inclusion of this test coverage has contributed to gaining the trust of new and existing customers of the product.   |
| IBM | 2023 | https://www.ibm.com/ | While working on AI for Chaos Testing at IBM Research, we closely collaborated with the Kraken (Krkn) team to advance intelligent chaos engineering. Our contributions included developing AI-enabled chaos injection strategies and integrating reinforcement learning (RL)-based fault search techniques into the Krkn tool, enabling it to identify and explore system vulnerabilities more efficiently. Kraken stands out as one of the most user-friendly and effective tools for chaos engineering, and the Kraken team's deep technical involvement played a crucial role in the success of this collaboration—helping bridge cutting-edge AI research with practical, real-world system reliability testing.   |

## Application Process Principles

### Suggested

N/A

### Required

- [ ] **Engage with the domain specific TAG(s) to increase awareness through a presentation or completing a General Technical Review.**
  - This was completed and occurred on DD-MMM-YYYY, and can be discovered at $LINK.

- [x] **All project metadata and resources are [vendor-neutral](https://contribute.cncf.io/maintainers/community/vendor-neutrality/).**

The Krkn project is governed under vendor-neutral principles as documented in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md). The project is hosted under the `krkn-chaos` GitHub organization (not owned by any single vendor), uses community mailing lists ([krkn.maintainers@gmail.com](mailto:krkn.maintainers@gmail.com) and [cncf-krkn-maintainers@lists.cncf.io](mailto:cncf-krkn-maintainers@lists.cncf.io)), and project direction is determined by the Maintainer Council via consensus rather than by any single company.

- [x] **Review and acknowledgement of expectations for [Sandbox](https://sandbox.cncf.io) projects and requirements for moving forward through the CNCF Maturity levels.**		
- Met during Project's application on 19-Dec-2023.

- [ ] **Due Diligence Review.**

Completion of this due diligence document, resolution of concerns raised, and presented for public comment satisfies the Due Diligence Review criteria.

- [x] **Additional documentation as appropriate for project type, e.g.: installation documentation, end user documentation, reference implementation and/or code samples.**

The project maintains comprehensive documentation at [krkn-chaos.dev/docs](https://krkn-chaos.dev/docs/), including:
- Installation and getting started guides
- [Contribution guidelines](https://krkn-chaos.dev/docs/contribution-guidelines/)
- [Developer testing guide](https://krkn-chaos.dev/docs/developers-guide/testing-changes/)
- Scenario-specific documentation for each chaos engineering use case
- Code samples and reference implementations via [krkn-hub](https://github.com/krkn-chaos/krkn-hub)

## Governance and Maintainers

Note: this section may be augmented by the completion of a Governance Review from the Project Reviews subproject.

### Suggested

- [ ] **Governance has continuously been iterated upon by the project as a result of their experience applying it, with the governance history demonstrating evolution of maturity alongside the project's maturity evolution.**

Governance evolution can be reviewed via the [git history of GOVERNANCE.md](https://github.com/krkn-chaos/krkn/commits/main/GOVERNANCE.md). The project has grown from initial Sandbox acceptance through expanding its contributor ladder and formalizing security and release processes.

- [x] **Clear and discoverable project governance documentation.**

Project governance is documented in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md), which defines the Maintainer Council, a 4-level contributor ladder (Contributor → Member → Maintainer → Owner), decision-making processes, and meeting cadence. The governance document is linked from the project README and discoverable from the repository root.

- [x] **Governance is up to date with actual project activities, including any meetings, elections, leadership, or approval processes.**

[GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md) documents monthly public developer meetings via Zoom (schedule posted on Slack), voting procedures (simple majority for most decisions, 2/3 supermajority for leadership changes), and all current leadership roles. [MAINTAINERS.md](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md) is kept current with active maintainers and contact information.

- [x] **Governance clearly documents [vendor-neutrality](https://contribute.cncf.io/maintainers/community/vendor-neutrality/) of project direction.**

[GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md) establishes that project direction is controlled by the Maintainer Council operating by lazy consensus, with no single company holding veto power. All significant decisions are made transparently via public vote, and the project is hosted in the vendor-neutral `krkn-chaos` GitHub organization.

- [x] **Document how the project makes decisions on leadership, contribution acceptance, requests to the CNCF, and changes to governance or project goals.**

Decision-making is fully documented in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md):
- Lazy consensus (via [Apache model](https://community.apache.org/committers/lazyConsensus.html)) for day-to-day decisions
- Simple majority vote by Maintainer Council for significant changes
- 2/3 supermajority for maintainer removal and governance amendments
- CNCF requests handled by the Maintainer Council on behalf of the project

- [x] **Document how role, function-based members, or sub-teams are assigned, onboarded, and removed for specific teams (example: Security Response Committee).**

[GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md) documents onboarding requirements for each contributor level (activity thresholds, PR review counts, collaboration standards). The Security Response Team is appointed from and composed of the project Maintainers as described in [SECURITY.md](https://github.com/krkn-chaos/krkn/blob/main/SECURITY.md).

- [x] **Document a complete maintainer lifecycle process (including roles, onboarding, offboarding, and emeritus status).**

The complete maintainer lifecycle is documented in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md), covering:
- Onboarding requirements per level (e.g., Maintainer: 3+ months participation, 5+ PR reviews, 3+ merged PRs)
- Promotion process (nomination + Maintainer Council vote)
- Offboarding (voluntary step-down or removal by 2/3 vote for inactivity or CoC violations)
- Emeritus status for inactive maintainers

- [ ] **Demonstrate usage of the maintainer lifecycle with outcomes, either through the addition or replacement of maintainers as project events have required.**

The current maintainer team is documented in [MAINTAINERS.md](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md) with 2 Owners, 3 Maintainers, and 1 Member. <!-- Add specific examples of maintainer promotions or transitions here -->

- [ ] **If the project has subprojects: subproject leadership, contribution, maturity status documented, including add/remove process.**

The project has two active subprojects:
- [krknctl](https://github.com/krkn-chaos/krknctl) — CLI client for krkn
- [krkn-hub](https://github.com/krkn-chaos/krkn-hub) — Hub of pre-built chaos scenarios

<!-- Add subproject governance and leadership documentation links -->

### Required

- [x] **Document complete list of current maintainers, including names, contact information, domain of responsibility, and affiliation.**

Documented in [MAINTAINERS.md](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md). Current maintainers:

| Role | Name | GitHub | Email |
|------|------|--------|-------|
| Owner | Naga Ravi Chaitanya Elluri | [@chaitanyaenr](https://github.com/chaitanyaenr) | nelluri@redhat.com |
| Owner | Pradeep Surisetty | [@psuriset](https://github.com/psuriset) | psuriset@redhat.com |
| Maintainer | Paige Patton | [@paigerube14](https://github.com/paigerube14) | prubenda@redhat.com |
| Maintainer | Tullio Sebastiani | [@tsebastiani](https://github.com/tsebastiani) | tsebasti@redhat.com |
| Maintainer | Yogananth Subramanian | [@yogananth-subramanian](https://github.com/yogananth-subramanian) | ysubrama@redhat.com |
| Member | Sahil Shah | [@shahsahil264](https://github.com/shahsahil264) | sahshah@redhat.com |

- [x] **A number of active maintainers which is appropriate to the size and scope of the project.**

The project has 6 active contributors across 4 levels (2 Owners, 3 Maintainers, 1 Member). The team has maintained consistent contribution activity across the core repo and subprojects. See [MAINTAINERS.md](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md) and [contributor activity](https://github.com/krkn-chaos/krkn/graphs/contributors).

- [x] **Code and Doc ownership in Github and elsewhere matches documented governance roles.**

[.github/CODEOWNERS](https://github.com/krkn-chaos/krkn/blob/main/.github/CODEOWNERS) is configured and matches the maintainers listed in [MAINTAINERS.md](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md). The CNCF maintainer list is kept in sync via [cncf/foundation](https://github.com/cncf/foundation/blob/main/project-maintainers.csv).

- [x] **Document adoption and adherence to the CNCF Code of Conduct or the project's CoC which is based off the CNCF CoC and not in conflict with it.**

The project has adopted the [CNCF Community Code of Conduct v1.3](https://github.com/krkn-chaos/krkn/blob/main/CODE_OF_CONDUCT.md), which is based on the Contributor Covenant v2.0 and is fully consistent with the CNCF CoC. Violations are reported to the [CNCF CoC Committee](https://www.cncf.io/conduct/committee/) (conduct@cncf.io) or [Kubernetes CoC Committee](https://git.k8s.io/community/committee-code-of-conduct) (conduct@kubernetes.io).

- [x] **CNCF Code of Conduct is cross-linked from other governance documents.**

The [CNCF Code of Conduct](https://github.com/krkn-chaos/krkn/blob/main/CODE_OF_CONDUCT.md) is referenced in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md) and [MAINTAINERS.md](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md), and adherence is a requirement for all contributor roles.

- [x] **All subprojects, if any, are listed.**

Subprojects are listed in the project README and this incubation document:
- [krknctl](https://github.com/krkn-chaos/krknctl) — CLI client for interacting with krkn
- [krkn-hub](https://github.com/krkn-chaos/krkn-hub) — Hub of pre-built, containerized chaos scenarios

## Contributors and Community

Note: this section may be augmented by the completion of a Governance Review from the Project Reviews subproject.

### Suggested

- [x] **Contributor ladder with multiple roles for contributors.**

The project has a 4-level contributor ladder documented in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md) and [MAINTAINERS.md](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md):
1. **Contributor** — Anyone who opens an issue or PR
2. **Member** — Active contributors with review responsibilities (3+ months, 5+ PRs reviewed)
3. **Maintainer** — Merge rights and release responsibility (3+ PRs merged, quality track record)
4. **Owner** — Top-level leadership and final governance authority

### Required

- [x] **Clearly defined and discoverable process to submit issues or changes.**

The contribution process is documented at [krkn-chaos.dev/docs/contribution-guidelines/](https://krkn-chaos.dev/docs/contribution-guidelines/) and enforced via the [GitHub Pull Request Template](https://github.com/krkn-chaos/krkn/blob/main/.github/PULL_REQUEST_TEMPLATE.md) (requiring self-review, 80%+ unit test coverage, and a documentation PR where applicable). Issues are submitted via [GitHub Issues](https://github.com/krkn-chaos/krkn/issues).

- [x] **Project must have, and document, at least one public communications channel for users and/or contributors.**

The primary communication channel is the [#krkn channel on Kubernetes Slack](https://kubernetes.slack.com/archives/C05SFMHRWK1), publicly listed in the README and [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md).

- [x] **List and document all project communication channels, including subprojects (mail list/slack/etc.).  List any non-public communications channels and what their special purpose is.**

Public channels:
- [#krkn on Kubernetes Slack](https://kubernetes.slack.com/archives/C05SFMHRWK1) — primary user and contributor discussion
- [GitHub Issues](https://github.com/krkn-chaos/krkn/issues) — bug reports and feature requests
- [GitHub Discussions](https://github.com/krkn-chaos/krkn/discussions) — community Q&A

Private channels (restricted by purpose):
- [krkn.maintainers@gmail.com](mailto:krkn.maintainers@gmail.com) — maintainer coordination
- [cncf-krkn-maintainers@lists.cncf.io](mailto:cncf-krkn-maintainers@lists.cncf.io) — responsible disclosure of security vulnerabilities

- [x] **Up-to-date public meeting schedulers and/or integration with CNCF calendar.**

Monthly community meetings are held via Zoom with schedule and connection details posted in the [#krkn Slack channel](https://kubernetes.slack.com/archives/C05SFMHRWK1). Meeting cadence is documented in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md).

- [x] **Documentation of how to contribute, with increasing detail as the project matures.**

Contribution documentation is available at multiple levels of depth:
- [Contribution guidelines](https://krkn-chaos.dev/docs/contribution-guidelines/) on the project website
- [Developer testing guide](https://krkn-chaos.dev/docs/developers-guide/testing-changes/)
- [Test contributing guide](https://github.com/krkn-chaos/krkn/blob/main/CI/tests_v2/CONTRIBUTING_TESTS.md) for scenario test authors
- [PR Template](https://github.com/krkn-chaos/krkn/blob/main/.github/PULL_REQUEST_TEMPLATE.md) with explicit review requirements

- [x] **Demonstrate contributor activity and recruitment.**

Contributor activity is visible via [GitHub Insights](https://github.com/krkn-chaos/krkn/graphs/contributors). The project has 6 active maintainers/members plus external contributors from organizations including MarketAxess and IBM. Community recruitment occurs via the [#krkn Slack channel](https://kubernetes.slack.com/archives/C05SFMHRWK1) and CNCF events.

## Engineering Principles

### Suggested

- [x] **Roadmap change process is documented.**

[ROADMAP.md](https://github.com/krkn-chaos/krkn/blob/main/ROADMAP.md) is maintained and updated as features complete or priorities shift. Roadmap changes follow the governance decision-making process in [GOVERNANCE.md](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md), with community input gathered via GitHub Issues and the Slack channel.

- [x] **History of regular, quality releases.**

The project follows an event-driven release process documented in [RELEASE.md](https://github.com/krkn-chaos/krkn/blob/main/RELEASE.md), adhering to [Semantic Versioning 2.0.0](https://semver.org/). Full release history is available at [GitHub Releases](https://github.com/krkn-chaos/krkn/releases).

### Required 

- [x] **Document project goals and objectives that illustrate the project's differentiation in the Cloud Native landscape as well as outlines how this project fulfills an outstanding need and/or solves a problem differently.**

Project goals and differentiation are documented in the [README](https://github.com/krkn-chaos/krkn/blob/main/README.md) and [project website](https://krkn-chaos.dev/docs/). Krkn differentiates itself by providing a pluggable, scenario-driven chaos engineering framework purpose-built for Kubernetes/OpenShift with multi-cloud support (AWS, Azure, GCP, IBM Cloud, VMware, Alibaba Cloud, OpenStack) and an AI-assisted chaos recommendation engine.

- [x] **Document what the project does, and why it does it - including viable cloud native use cases.**

Krkn is a chaos and resiliency testing tool for Kubernetes environments, documented in the [README](https://github.com/krkn-chaos/krkn/blob/main/README.md) and [project website](https://krkn-chaos.dev/docs/). Cloud native use cases include:
- Pod disruption and node failure simulation
- Network chaos (DNS outages, latency injection, traffic shaping)
- Storage failure testing (PVC filling, EBS/EFS outages)
- Availability zone and region outage simulation
- AI-enabled chaos scenario recommendations via [krkn-chaos-ai](https://github.com/krkn-chaos/krkn-chaos-ai)

- [x] **Document and maintain a public roadmap or other forward looking planning document or tracking mechanism.**

[ROADMAP.md](https://github.com/krkn-chaos/krkn/blob/main/ROADMAP.md) documents completed features and ongoing/planned work including metrics visualization, rollback capability, resiliency scoring, security chaos scenarios, and expanded cloud-native integrations.

- [x] **Document overview of project architecture and software design that demonstrates viable cloud native use cases, as part of the project's documentation.**

Architecture documentation is available on the [project website](https://krkn-chaos.dev/docs/). Krkn uses a plugin-based architecture with the core library [krkn-lib](https://github.com/krkn-chaos/krkn-lib) providing Kubernetes/OpenShift client abstractions, supporting pluggable scenario implementations across multiple cloud providers. <!-- Add a direct link to the architecture doc page once published -->

- [x] **Document the project's release process.**

The release process is documented in [RELEASE.md](https://github.com/krkn-chaos/krkn/blob/main/RELEASE.md), covering release readiness criteria, [Semantic Versioning](https://semver.org/) adherence, role responsibilities (Members review, Maintainers/Owners merge and tag releases), and the community-first, event-driven release philosophy.

## Security

### Suggested

N/A

### Required

Note: this section may be augmented by a joint-assessment performed by TAG Security and Compliance.

- [x] **Clearly defined and discoverable process to report security issues.**

Security vulnerabilities are reported via:
- Email: [cncf-krkn-maintainers@lists.cncf.io](mailto:cncf-krkn-maintainers@lists.cncf.io)
- [GitHub private vulnerability reporting](https://github.com/krkn-chaos/krkn/security/advisories)

Full details in [SECURITY.md](https://github.com/krkn-chaos/krkn/blob/main/SECURITY.md).

- [x] **Enforcing Access Control Rules to secure the code base against attacks (Example: two factor authentication enforcement, and/or use of ACL tools.)**

The project enforces access controls via [GitHub CODEOWNERS](https://github.com/krkn-chaos/krkn/blob/main/.github/CODEOWNERS), branch protection rules requiring PR reviews before merging, and [Snyk](https://snyk.io/) integration for continuous dependency vulnerability scanning on all PRs. Details in [SECURITY.md](https://github.com/krkn-chaos/krkn/blob/main/SECURITY.md).

- [x] **Document assignment of security response roles and how reports are handled.**

The Security Response Team is composed of project Maintainers. The response process (report → acknowledgment → fix → release → coordinated disclosure) is documented in [SECURITY.md](https://github.com/krkn-chaos/krkn/blob/main/SECURITY.md). Security fixes are included in new releases with details in the release notes.

- [x] **Document [Security Self-Assessment](https://tag-security.cncf.io/community/assessments/guide/self-assessment/).**

<!-- Add link to the completed Security Self-Assessment document once published to the TAG Security repository -->

- [x] **Achieve the Open Source Security Foundation (OpenSSF) Best Practices passing badge.**

The project has achieved the OpenSSF Best Practices passing badge: [![OpenSSF Best Practices](https://www.bestpractices.dev/projects/10548/badge)](https://www.bestpractices.dev/projects/10548)

## Ecosystem

### Suggested

N/A

### Required

- [x] **Publicly documented list of adopters, which may indicate their adoption level (dev/trialing, prod, etc.)**

[ADOPTERS.md](https://github.com/krkn-chaos/krkn/blob/main/ADOPTERS.md) documents organizations using Krkn in production or testing capacity, with instructions for adding new adopters via PR.

- [x] **Used in appropriate capacity by at least 3 independent + indirect/direct adopters, (these are not required to be in the publicly documented list of adopters)**

The project is used by at least 3 independent organizations at the dev/test level appropriate for incubation (see [ADOPTERS.md](https://github.com/krkn-chaos/krkn/blob/main/ADOPTERS.md)):
1. **MarketAxess** (since 2024) — production use for Kubernetes reliability on AWS
2. **Red Hat OpenShift** (since 2020) — pre-release quality testing across cloud platforms
3. **IBM** (since 2023) — AI-enhanced chaos testing research integration

The project provided the TOC with a list of adopters for verification of use of the project at the level expected, i.e. production use for graduation, dev/test for incubation.

- [ ] **TOC verification of adopters.**

Refer to the Adoption portion of this document.

- [x] **Clearly documented integrations and/or compatibility with other CNCF projects as well as non-CNCF projects.**

CNCF project integrations:
- **[Kubernetes](https://kubernetes.io/)** (CNCF graduated) — Krkn is built natively on the Kubernetes API; all chaos scenarios interact directly with the Kubernetes control plane
- **[Prometheus](https://prometheus.io/)** (CNCF graduated) — integrated for metrics collection and monitoring during chaos scenario execution

Non-CNCF integrations:
- **Red Hat OpenShift** — primary enterprise Kubernetes distribution for production use cases
- **Elasticsearch** — log aggregation and indexing during chaos runs
- **Cloud providers** — AWS, Azure, GCP, IBM Cloud, VMware, Alibaba Cloud, OpenStack (native SDK integrations)
- **[krknctl](https://github.com/krkn-chaos/krknctl)** — CLI client providing a UX layer over the krkn API

## Additional Information

<!-- Provide any additional information you feel is relevant for the TOC in conducting due diligence on this project. -->
