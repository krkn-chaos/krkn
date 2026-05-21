# How to contribute

We're excited to have you consider contributing to our chaos! Contributions are always appreciated.

# Krkn

## Contributing to Krkn

If you would like to contribute to Krkn, but are not sure exactly what to work on, you can find a number of open issues that are awaiting contributions in
[issues.](https://github.com/krkn-chaos/krkn/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22good%20first%20issue%22)

Please start by discussing potential solutions and your proposed approach for the issue you plan to work on. We encourage you to gather feedback from maintainers and contributors and to have the issue assigned to you before opening a pull request with a solution.

## Adding New Scenarios and Configurations

### New Scenarios

We are always looking for new scenarios to make krkn better and more usable for our chaos community. If you have any ideas, please first open an issue to explain the new scenario you are wanting to add. We will review and respond with ideas of how to get started.

If adding a new scenario or tweaking the main config, be sure to add in updates into the CI to be sure the CI is up to date.
Please read [the developers guide](https://krkn-chaos.dev/docs/developers-guide/) for more information on updates.

#### Scenario Plugin Development

If you're gearing up to develop new scenarios, take a moment to review our
[Scenario Plugin API Documentation](https://krkn-chaos.dev/docs/developers-guide/scenario_plugin_api/).
It's the perfect starting point to tap into your chaotic creativity!

### New Configuration to Scenarios

If you are currently using a scenario but want more configuration options, please open a [github issue](https://github.com/krkn-chaos/krkn/issues) describing your use case and what fields and functionality you would like to see added. We will review the suggestion and give pointers on how to add the functionality. If you feel inclined, you can start working on the feature and we'll help if you get stuck along the way.


## Work in Progress PR's
If you are working on a contribution in any capacity and would like to get a new set of eyes on your work, go ahead and open a PR with '[WIP]' at the start of the title in your PR and tag the [maintainers](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md) for review. We will review your changes and give you suggestions to keep you moving!

## Office Hours
If you have any questions that you think could be better discussed on a meeting we have monthly office hours [zoom link](https://zoom-lfx.platform.linuxfoundation.org/meetings/krkn?view=month). Please add items to agenda before so we can best prepare to help you.


## AI-Assisted Contributions
We welcome contributions that use AI tools (LLMs, code generators, AI coding agents, etc.) as development assistants. If you use AI tools in your contribution, please review our [AI Contribution Policy](AI_CONTRIBUTION_POLICY.md) for disclosure requirements, safety guidelines, and quality expectations. In short: disclose AI usage in your commit trailers and make sure you understand and can explain every line of code you submit.

## Good PR Checklist
Here's a quick checklist for a good PR, more details below:
- One feature/change per PR
- One commit per PR ([squash your commits](https://krkn-chaos.dev/docs/contribution-guidelines/git-pointers/#squash-commits))
- PR rebased on main ([git rebase](https://krkn-chaos.dev/docs/contribution-guidelines/git-pointers/#rebase-with-upstream), not git pull)
- Good descriptive commit message, with link to issue
- No changes to code not directly related to your PR
- Includes functional/integration test (more applicable to krkn-lib)
- Includes link to documentation PR (documentation hosted in https://github.com/krkn-chaos/website)

## Helpful Documents
Refer to the docs below to be able to test your own images with any changes and be able to contribute them to the repository
- [Getting Started](https://krkn-chaos.dev/docs/getting-started/getting-started-krkn/)
- [Contribute - Git Pointers](https://krkn-chaos.dev/docs/contribution-guidelines/git-pointers/)
- [Testing Your Krkn-hub Changes](https://krkn-chaos.dev/docs/developers-guide/testing-changes/)

## Joining the Contributor Ladder

The following explains how to formally join the Krkn community at each level of the contributor ladder. For a description of what each role entails, see [GOVERNANCE.md](GOVERNANCE.md) and [MAINTAINERS.md](MAINTAINERS.md).

### Contributor

**Anyone who participates in the project is a contributor.** There is no application required — opening an issue, submitting a PR, reviewing someone else's work, improving documentation, or helping others in Slack all count.

To get started:
1. Find something to work on in the [open issues](https://github.com/krkn-chaos/krkn/issues?q=is%3Aissue+state%3Aopen+label%3A%22good+first+issue%22), or open one of your own.
2. Join the [#krkn channel on Kubernetes Slack](https://kubernetes.slack.com/archives/C05SFMHRWK1) to introduce yourself and ask questions.

### Member

Members are active contributors who review PRs and have demonstrated a solid understanding of the project's codebase and conventions.

**Requirements** — before applying, you should have:
- Been actively contributing for **at least 3 months**
- Submitted **at least 3 non-trivial PRs** that have been merged
- Reviewed **at least 5 PRs** from other contributors
- Shown familiarity with the project's coding style, testing practices, and documentation standards

**How to apply:**
1. Open a [Member Application issue](https://github.com/krkn-chaos/krkn/issues/new?template=member_request.md) and complete all sections.
2. Tag two current Maintainers to review your application.

Maintainers will evaluate the application and respond within **two weeks**. A simple majority vote of Maintainers is required for approval. Once approved, you will be added to [MAINTAINERS.md](MAINTAINERS.md) and granted the appropriate repository permissions.

### Maintainer

Maintainers are responsible for the overall health and direction of the project. They have write access to the repository and can merge pull requests.

**Requirements** — before applying, you should have:
- Been an active **Member for at least 6 months**
- Performed reviews for **at least 5 non-trivial pull requests**
- Contributed **at least 3 non-trivial pull requests** that have been merged
- Demonstrated the ability to mentor contributors and provide constructive, timely feedback
- Shown a clear understanding of the project's technical direction and goals

**How to apply:**

Maintainer nominations are peer-driven — an existing Maintainer must sponsor your application.

1. Reach out to an existing Maintainer (via Slack or a GitHub issue) and ask them to nominate you.
2. The sponsoring Maintainer opens a [Maintainer Nomination issue](https://github.com/krkn-chaos/krkn/issues/new?template=maintainer_request.md) and completes all sections.
3. The Maintainer Council votes on the issue or at the next monthly meeting. A **simple majority** is required for approval.

Once approved, you will be added to [MAINTAINERS.md](MAINTAINERS.md), granted write access to the repository, and invited to the maintainer mailing list.

**Stepping down:** To request removal from any role, see the "Requesting Removal" section in [GOVERNANCE.md](GOVERNANCE.md).

## Questions?

Reach out to us on slack if you ever have any questions or want to know how to get started. You can join the kubernetes Slack [here](https://communityinviter.com/apps/kubernetes/community) and can join our [Krkn channel](https://kubernetes.slack.com/archives/C05SFMHRWK1)
