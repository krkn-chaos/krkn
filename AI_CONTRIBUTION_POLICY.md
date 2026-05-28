# Krkn AI Contribution Policy

## Overview

This policy establishes guidelines for contributions to the Krkn project that
involve Artificial Intelligence (AI) tools, including but not limited to Large
Language Models (LLMs), code generation tools, AI-assisted development
environments, and AI coding agents. This is a living document that will evolve
as AI technology, community practices, and legal frameworks mature.

## Motivation

AI tools are powerful assistants that can help developers become more productive
when configured and used correctly. This policy encourages their use within the
Krkn project to boost both productivity and innovation while ensuring
transparency and safety.

Krkn is a chaos engineering tool that injects deliberate failures into live
Kubernetes and OpenShift clusters. The consequences of incorrect or
poorly-understood code can be severe — unintended destructive operations,
unrecoverable cluster states, or silent failures that mask real resilience
issues. This context demands a higher standard of human oversight for all
contributions, and especially those involving AI-generated content.

Transparency about AI usage allows the community to learn and refine our
policies and practices to maximize the value of these tools while maintaining
the trust and safety our users depend on.

### Contributor Accountability

AI tools can produce verbose, over-engineered, or superficially-correct code
that places a disproportionate review burden on maintainers. Disclosure creates
accountability and helps ensure contributors take ownership of AI-assisted work.
Contributors are expected to:

- Thoroughly review and understand every line of AI-generated code before
  submission
- Refine and groom AI output to meet project quality standards
- Take full ownership of all submitted content regardless of its origin
- Be able to explain and justify any line of code when asked during review

Low-effort submissions that appear to be unreviewed AI output may be rejected
without detailed feedback until properly refined. This applies to all
contributions, but is particularly relevant for AI-assisted work.

### Legal and Copyright Rationale

Disclosure also serves important legal purposes. Copyright law in this area
continues to evolve, and as of current legal guidance, computer-generated work
may not be considered an original work eligible for copyright protection in many
jurisdictions. Additionally:

- AI training data may originate from materials with unclear or incompatible
  licenses
- Some AI tool vendors may retain rights to generated output, which could
  conflict with open source licensing
- Proper attribution helps maintain the integrity of the project's licensing
  under Apache 2.0

For further reading on these legal considerations, see the
[Linux Foundation Generative AI Guidelines](https://www.linuxfoundation.org/legal/generative-ai)
and [AI-Assisted Development and Open Source: Navigating Legal Issues](https://www.redhat.com/en/blog/ai-assisted-development-and-open-source-navigating-legal-issues).

## AI Tool Disclosure Requirements

### Disclosure

All contributors **SHOULD** disclose AI tool use when submitting code,
documentation, tests, scenario configurations, or other content to the Krkn
project.

Disclosure **SHOULD** take the form of a trailer line within the commit
attributing the AI tool used. Acceptable formats include:

- `Assisted-by: GitHub Copilot <noreply@github.com>`
- `Assisted-by: Claude <noreply@anthropic.com>`
- `Co-authored-by: Claude <noreply@anthropic.com>`
- `Generated-by: ChatGPT <noreply@openai.com>`

Many AI coding tools automatically add `Co-authored-by` trailers — this is
acceptable and need not be changed to `Assisted-by`.

### Scope of Disclosure

Disclosure is expected when AI tools have materially contributed to the
submitted content.

**Requires disclosure:**

- AI wrote a function, class, scenario plugin, or significant code block that
  you included
- AI suggested an algorithm, architecture, or chaos injection approach you
  adopted
- AI generated tests, documentation, scenario YAML configurations, or commit
  messages you used
- AI-suggested solutions, refactoring, or significant debugging help that
  shaped the final implementation
- AI generated rollback logic or cluster interaction code

**Does not require disclosure:**

- General Q&A or learning (even if it informed your approach)
- IDE autocomplete (Copilot line completions, IntelliSense)
- Using AI to explain existing code or understand the krkn-lib API
- Asking AI to review your human-written code
- Spell checking or minor syntax corrections
- Content that has been substantially rewritten such that the original AI
  output is no longer recognizable

When in doubt, err on the side of disclosure — transparency benefits the
community.

## Acceptable Uses of AI Tools

AI tools are **accepted** as development assistants for:

- **Code scaffolding**: Generating boilerplate code, initial plugin
  implementations, and scenario configurations
- **Refactoring**: Suggesting code improvements and modernization
- **Testing**: Creating unit test cases and test data (subject to quality
  standards below)
- **Documentation**: Drafting technical documentation, docstrings, and usage
  examples
- **Debugging**: Identifying potential issues and suggesting fixes
- **Research**: Exploring architectural approaches, chaos engineering patterns,
  and best practices
- **Learning**: Understanding the krkn codebase, krkn-lib API, and Kubernetes
  concepts

## Chaos Engineering Safety Requirements

Given that Krkn operates directly on live Kubernetes and OpenShift clusters,
AI-generated contributions carry unique safety risks that require additional
scrutiny.

### Mandatory Human Verification

The following areas **MUST** receive thorough human review regardless of whether
AI tools were used, but contributors should be especially diligent when AI has
generated code in these areas:

- **Scenario execution logic**: Code that triggers chaos injection (pod
  deletion, node shutdown, network disruption, resource hogging, etc.)
- **Rollback and recovery logic**: Code that restores cluster state after chaos
  injection. Incomplete or incorrect rollback can leave clusters in a degraded
  state.
- **Cloud provider interactions**: Code in
  `krkn/scenario_plugins/node_actions/` that calls cloud APIs (AWS, Azure, GCP,
  IBM Cloud, VMware, Alibaba, OpenStack) to stop, start, reboot, or terminate
  instances
- **Exit code handling**: Krkn uses specific exit codes (0=success, 1=scenario
  failure, 2=critical alerts, 3+=health check failure). AI tools may not
  correctly implement this contract.
- **Credential and kubeconfig handling**: Any code that accesses or processes
  authentication material

### Plugin Architecture Compliance

Krkn enforces strict naming conventions through its plugin factory. AI tools
frequently generate code that violates these conventions. Contributors using AI
to generate scenario plugins **MUST** verify:

- Module files end with `_scenario_plugin.py` and use snake_case
- Class names use CamelCase and end with `ScenarioPlugin`
- Class names match module filenames (snake_case to CamelCase mapping)
- Plugin directories do **NOT** contain "scenario" or "plugin" in their names
- The plugin extends `AbstractScenarioPlugin` and implements both `run()` and
  `get_scenario_types()`

### Dependency Safety

AI tools may suggest dependency versions that conflict with Krkn's
requirements. Contributors **MUST** verify:

- `docker` package remains <7.0
- `requests` package remains <2.32
- New dependencies are compatible with the existing dependency tree
- Dependencies are pinned to specific versions in `requirements.txt`
- Dependencies are checked for known security vulnerabilities

## Code Quality Standards

AI-generated code must meet the same quality standards as human-written code.
Common AI-generated patterns that do **not** meet Krkn's standards include:

- **Excessive comments**: Avoid narrating what the code does (e.g.,
  "# Import the module", "# Define the function"). Comments should only explain
  non-obvious intent, trade-offs, or constraints.
- **Over-engineering**: AI often generates unnecessarily complex solutions.
  Prefer simplicity and consistency with existing patterns in the codebase.
- **Hallucinated APIs**: AI may generate calls to krkn-lib functions or
  Kubernetes API methods that do not exist. All API calls must be verified.
- **Generic variable names**: AI tends toward `result`, `data`, `item` etc.
  Use descriptive names consistent with the existing codebase.

## Testing Requirements

AI-generated code must meet Krkn's existing testing requirements. Additional
considerations for AI-assisted contributions:

- Unit tests must achieve **80% or greater code coverage** for core features
- Tests must contain **meaningful assertions** that validate behavior, not just
  verify that code runs without exceptions
- AI-generated tests that mock everything and test only the mock interactions
  will be rejected
- Scenario plugins must include evidence of execution on a real Kubernetes or
  OpenShift cluster (kind cluster is acceptable for development)
- Test output must be included in the PR description as required by the
  [contribution guidelines](https://github.com/krkn-chaos/krkn/blob/main/CONTRIBUTING.md)

## Contributor Ladder and AI

The Krkn project uses a
[contributor ladder](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md)
model (Contributor → Member → Maintainer → Owner). AI tool usage intersects
with this model in the following ways:

- **AI tools are tools, not contributors.** AI cannot be listed as a
  contributor, member, or maintainer.
- **Contribution quality over quantity**: Bulk AI-generated PRs that do not
  demonstrate genuine understanding of the project will not count toward
  advancement on the contributor ladder.
- **Review credibility**: PR reviews must reflect genuine human understanding.
  AI-assisted reviews that parrot generic feedback without engaging with the
  actual code changes may not count toward the review requirements for becoming
  a maintainer.
- **Demonstrated understanding**: Maintainers may ask contributors to explain
  their AI-assisted contributions during review. Inability to explain the code
  is grounds for requesting rework.

## Prohibited Uses

The following uses of AI tools are **not permitted** within the Krkn project:

- **Substituting AI for required human review**: Maintainer and member reviews
  must reflect genuine human evaluation
- **AI participation in governance**: AI-generated content must not be used in
  governance votes, Code of Conduct proceedings, or security response
  activities
- **Bulk low-quality contributions**: Using AI to generate high volumes of
  trivial PRs, issues, or comments to inflate contribution metrics
- **Unverified security reports**: AI-generated vulnerability reports submitted
  without human verification and analysis
- **Circumventing disclosure**: Deliberately concealing material AI involvement
  in a contribution

## Legal and Licensing Considerations

### Copyright Compliance

Contributors must ensure that:

- AI tool terms of service do not conflict with Apache 2.0 licensing
- No copyrighted material is inadvertently included in AI-generated output
- All third-party content is properly attributed and licensed

### Employer Policies

Contributors should verify that their use of AI tools complies with their
employer's policies regarding AI-generated code in open source contributions.

## Review Process

### Review Criteria

Consistent with [Krkn's contribution guidelines](https://github.com/krkn-chaos/krkn/blob/main/CONTRIBUTING.md),
reviewers should evaluate all contributions — AI-assisted or otherwise — for:

- Code quality and adherence to project standards
- Appropriate test coverage and meaningful assertions
- Security implications, especially for cluster-facing operations
- Correct implementation of rollback and recovery logic
- Long-term maintainability and consistency with existing patterns
- Compliance with plugin naming conventions

### Reviewer Guidance for AI-Assisted Contributions

Reviewers should be attentive to common AI-generated issues:

- Plausible-but-incorrect logic, especially in chaos injection and rollback
  paths
- Hallucinated API calls to krkn-lib, Kubernetes client, or cloud SDKs
- Incorrect exit code handling
- Violations of the plugin naming conventions that would cause factory rejection
- Over-commented or over-engineered code
- Tests that achieve coverage without meaningful validation

Reviewers may request that contributors demonstrate understanding of AI-assisted
code before approving.

## Policy Evolution

This policy will be regularly reviewed and updated to reflect:

- Changes in AI technology capabilities
- Legal and regulatory developments
- Community feedback and experience
- Industry best practices within the CNCF ecosystem

Changes to this policy may be approved by a 2/3 vote of the
[Maintainers](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md),
consistent with Krkn's [Governance](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md)
charter modification process.

## Questions and Clarifications

For questions about this policy, please:

1. Open an issue in the [krkn repository](https://github.com/krkn-chaos/krkn)
2. Discuss in the [#krkn channel](https://kubernetes.slack.com/archives/C05SFMHRWK1)
   on Kubernetes Slack
3. Bring up during monthly
   [office hours](https://zoom-lfx.platform.linuxfoundation.org/meetings/krkn?view=month)
4. Email the maintainers at krkn.maintainers@gmail.com

## References

- [Linux Foundation Generative AI Guidelines](https://www.linuxfoundation.org/legal/generative-ai)
- [KubeVirt AI Contribution Policy](https://github.com/kubevirt/community/blob/main/ai-contribution-policy.md)
- [Avocado Framework AI Policy](https://avocado-framework.readthedocs.io/en/latest/guides/contributor/chapters/ai_policy.html)
- [QEMU Code Provenance Policy](https://www.qemu.org/docs/master/devel/code-provenance.html#use-of-ai-content-generators)
- [Ghostty AI Policy](https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md)
- [AI-Assisted Development and Open Source: Navigating Legal Issues](https://www.redhat.com/en/blog/ai-assisted-development-and-open-source-navigating-legal-issues)
- [AGENT.md Standard](https://ampcode.com/AGENT.md)
- [Krkn Contributing Guidelines](https://github.com/krkn-chaos/krkn/blob/main/CONTRIBUTING.md)
- [Krkn Governance](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md)
- [Krkn Code of Conduct](https://github.com/krkn-chaos/krkn/blob/main/CODE_OF_CONDUCT.md)
