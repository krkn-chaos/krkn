## Krkn Roadmap

Following are a list of enhancements that we are planning to work on adding support in Krkn. Of course any help/contributions are greatly appreciated.

- [ ] [Ability to visualize the metrics that are being captured by Kraken and stored in Elasticsearch](https://github.com/krkn-chaos/krkn/issues/124)
- [ ] [Ability to roll back cluster to original state if chaos fails](https://github.com/krkn-chaos/krkn/issues/804)
- [ ] Add recovery time metrics to each scenario for better regression analysis
- [ ] [Add resiliency scoring to chaos scenarios ran on cluster](https://github.com/krkn-chaos/krkn/issues/125)
- [ ] [Add AI-based Chaos Configuration Generator](https://github.com/krkn-chaos/krkn/issues/1166)
- [ ] [Introduce Security Chaos Engineering Scenarios](https://github.com/krkn-chaos/krkn/issues/1165)
- [ ] [Add AWS-native Chaos Scenarios (S3, Lambda, Networking)](https://github.com/krkn-chaos/krkn/issues/1164)
- [ ] [Unify Krkn Ecosystem under krknctl for Enhanced UX](https://github.com/krkn-chaos/krknctl/issues/113)
- [ ] [Build Web UI for Creating, Monitoring, and Reviewing Chaos Scenarios](https://github.com/krkn-chaos/krkn/issues/1167)
- [ ] [Add Predefined Chaos Scenario Templates (KRKN Chaos Library)](https://github.com/krkn-chaos/krkn/issues/1168)
- [x] [Ability to run multiple chaos scenarios in parallel under load to mimic real world outages](https://github.com/krkn-chaos/krkn/issues/424)
- [x] [Centralized storage for chaos experiments artifacts](https://github.com/krkn-chaos/krkn/issues/423) - [PR #758](https://github.com/krkn-chaos/krkn/pull/758)
- [x] [Support for causing DNS outages](https://github.com/krkn-chaos/krkn/issues/394) - [PR #856](https://github.com/krkn-chaos/krkn/pull/856)
- [x] [Chaos recommender](https://github.com/krkn-chaos/krkn/tree/main/utils/chaos-recommender) to suggest scenarios having probability of impacting the service under test using profiling results - [PR #508](https://github.com/krkn-chaos/krkn/pull/508)
- [x] Chaos AI integration to improve test coverage while reducing fault space to save costs and execution time [krkn-chaos-ai](https://github.com/krkn-chaos/krkn-chaos-ai)
- [x] [Support for pod level network traffic shaping](https://github.com/krkn-chaos/krkn/issues/393) - [PR #449](https://github.com/krkn-chaos/krkn/pull/449), [PR #501](https://github.com/krkn-chaos/krkn/pull/501)
- [x] Support for running all the scenarios of Kraken on Kubernetes distribution - see https://github.com/krkn-chaos/krkn/issues/185, https://github.com/redhat-chaos/krkn/issues/186
- [x] Continue to improve [Chaos Testing Guide](https://krkn-chaos.github.io/krkn) in terms of adding best practices, test environment recommendations and scenarios to make sure the OpenShift platform, as well the applications running on top it, are resilient and performant under chaotic conditions.
- [x] [Switch documentation references to Kubernetes](https://github.com/krkn-chaos/krkn/issues/495)
- [x] [OCP and Kubernetes functionalities segregation](https://github.com/krkn-chaos/krkn/issues/497) - [PR #507](https://github.com/krkn-chaos/krkn/pull/507)
- [x] [Krknctl - client for running Krkn scenarios with ease](https://github.com/krkn-chaos/krknctl)
- [x] [AI Chat bot to help get started with Krkn and commands](https://github.com/krkn-chaos/krkn-lightspeed)


---

## Proposing a Roadmap Item

Anyone in the community can propose an item for the roadmap. The process is designed to be lightweight and transparent.

### Step 1 — Open a GitHub Issue

Open a [new feature request issue](https://github.com/krkn-chaos/krkn/issues/new?template=feature.md) describing what you want to add and why. A strong proposal includes:

- **Problem statement** – what gap or limitation exists today
- **Proposed solution** – what the feature would do at a high level
- **Scope** – is this a small enhancement, a new scenario, or a large architectural change?
- **Benefit to the community** – who would use this and how

Add the label **`roadmap-proposal`** to the issue so maintainers can find it easily.

### Step 2 — Community Discussion

Leave the issue open for community feedback for **at least two weeks**. Gather responses from users and contributors — this helps maintainers understand demand and surface edge cases before committing it to the roadmap.

You can also raise the proposal in the [#krkn channel on Kubernetes Slack](https://kubernetes.slack.com/archives/C05SFMHRWK1) or bring it to the monthly [office hours](https://zoom-lfx.platform.linuxfoundation.org/meetings/krkn?view=month) for live discussion.

### Step 3 — Maintainer Review and Decision

Maintainers review `roadmap-proposal` issues at the monthly community meeting or asynchronously via the issue thread. A **simple majority vote** of Maintainers is required to add an item to the roadmap (see [GOVERNANCE.md](GOVERNANCE.md)).

Items are evaluated against the following criteria:

| Criterion | Description |
|-----------|-------------|
| Alignment | Does it fit the project's mission of chaos and resiliency testing for Kubernetes? |
| Impact | Does it benefit a broad set of users or address a common pain point? |
| Feasibility | Is it technically achievable with reasonable effort? |
| Ownership | Is there a contributor willing to drive implementation? |

### Step 4 — Added to the Roadmap

If approved, a maintainer opens a PR to add the item to this file under the open (`[ ]`) section. The PR should link to the original proposal issue. Do not begin implementation until the roadmap PR is merged — that merge is the signal that the item is officially accepted.

Once the item is on the roadmap, comment on the issue to request assignment before starting work. The contributor who originally proposed the issue is given priority, but if they are not planning to implement it, any community member can be assigned. Maintainers may also pick up items independently if no one has claimed them.

### Step 5 — Implementation and Completion

When the feature is implemented, the roadmap item is updated to checked (`[x]`) and the implementing PR link is added. The proposal issue is then closed.

---
