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

## Questions?

Reach out to us on slack if you ever have any questions or want to know how to get started. You can join the kubernetes Slack [here](https://communityinviter.com/apps/kubernetes/community) and can join our [Krkn channel](https://kubernetes.slack.com/archives/C05SFMHRWK1)
