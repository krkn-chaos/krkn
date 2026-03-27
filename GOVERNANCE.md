# Krkn Project Governance

Krkn is a chaos and resiliency testing tool for Kubernetes that injects deliberate failures into clusters to validate their resilience under turbulent conditions. This governance document explains how the project is run.

- [Values](#values)
- [Community Roles](#community-roles)
- [Becoming a Maintainer](#becoming-a-maintainer)
- [Removing a Maintainer](#removing-a-maintainer)
- [Meetings](#meetings)
- [CNCF Resources](#cncf-resources)
- [Code of Conduct](#code-of-conduct)
- [Security Response Team](#security-response-team)
- [Voting](#voting)
- [Modifying this Charter](#modifying-this-charter)

## Values

Krkn and its leadership embrace the following values:

* **Openness**: Communication and decision-making happens in the open and is discoverable for future reference. As much as possible, all discussions and work take place in public forums and open repositories.

* **Fairness**: All stakeholders have the opportunity to provide feedback and submit contributions, which will be considered on their merits.

* **Community over Product or Company**: Sustaining and growing our community takes priority over shipping code or sponsors' organizational goals. Each contributor participates in the project as an individual.

* **Inclusivity**: We innovate through different perspectives and skill sets, which can only be accomplished in a welcoming and respectful environment.

* **Participation**: Responsibilities within the project are earned through participation, and there is a clear path up the contributor ladder into leadership positions.

## Community Roles

Krkn uses a tiered contributor model. Each level comes with increasing responsibilities and privileges.

### Contributor

Anyone can become a contributor by participating in discussions, reporting bugs, or submitting code or documentation.

**Responsibilities:**
- Adhere to the [Code of Conduct](CODE_OF_CONDUCT.md)
- Report bugs and suggest new features
- Contribute high-quality code and documentation

### Member

Members are active contributors who have demonstrated a solid understanding of the project's codebase and conventions.

**Responsibilities:**
- Review pull requests for correctness, quality, and adherence to project standards
- Provide constructive and timely feedback to contributors
- Ensure contributions are well-tested and documented
- Work with maintainers to support a smooth release process

### Maintainer

Maintainers are responsible for the overall health and direction of the project. They have write access to the [project GitHub repository](https://github.com/krkn-chaos/krkn) and can merge patches from themselves or others. The current maintainers are listed in [MAINTAINERS.md](./MAINTAINERS.md).

Maintainers collectively form the **Maintainer Council**, the governing body for the project.

A maintainer is not just someone who can make changes — they are someone who has demonstrated the ability to collaborate with the team, get the right people to review code and docs, contribute high-quality work, and follow through to fix issues.

**Responsibilities:**
- Set the technical direction and vision for the project
- Manage releases and ensure stability of the main branch
- Make decisions on feature inclusion and project priorities
- Mentor contributors and help grow the community
- Resolve disputes and make final decisions when consensus cannot be reached

### Owner

Owners have administrative access to the project and are the final decision-makers.

**Responsibilities:**
- Manage the core team of maintainers
- Set the overall vision and strategy for the project
- Handle administrative tasks such as managing the repository and other resources
- Represent the project in the broader open-source community

## Becoming a Maintainer

To become a Maintainer you need to demonstrate the following:

- **Commitment to the project:**
  - Participate in discussions, contributions, code and documentation reviews for 3 months or more
  - Perform reviews for at least 5 non-trivial pull requests
  - Contribute at least 3 non-trivial pull requests that have been merged
- Ability to write quality code and/or documentation
- Ability to collaborate effectively with the team
- Understanding of how the team works (policies, processes for testing and code review, etc.)
- Understanding of the project's codebase and coding and documentation style

A new Maintainer must be proposed by an existing Maintainer by sending a message to the [maintainer mailing list](mailto:krkn.maintainers@gmail.com). A simple majority vote of existing Maintainers approves the application. Nominations will be evaluated without prejudice to employer or demographics.

Maintainers who are approved will be granted the necessary GitHub rights and invited to the [maintainer mailing list](mailto:krkn.maintainers@gmail.com).

## Removing a Maintainer

Maintainers may resign at any time if they feel they will not be able to continue fulfilling their project duties.

Maintainers may also be removed for inactivity, failure to fulfill their responsibilities, violating the Code of Conduct, or other reasons. Inactivity is defined as a period of very low or no activity in the project for a year or more, with no definite schedule to return to full Maintainer activity.

A Maintainer may be removed at any time by a 2/3 vote of the remaining Maintainers.

Depending on the reason for removal, a Maintainer may be converted to **Emeritus** status. Emeritus Maintainers will still be consulted on some project matters and can be rapidly returned to Maintainer status if their availability changes.

## Meetings

Maintainers are expected to participate in the public developer meeting, which occurs **once a month via Zoom**. Meeting details (link, agenda, and notes) are posted in the [#krkn channel on Kubernetes Slack](https://kubernetes.slack.com/messages/C05SFMHRWK1) prior to each meeting.

Maintainers will also hold closed meetings to discuss security reports or Code of Conduct violations. Such meetings should be scheduled by any Maintainer on receipt of a security issue or CoC report. All current Maintainers must be invited to such closed meetings, except for any Maintainer who is accused of a CoC violation.

## CNCF Resources

Any Maintainer may suggest a request for CNCF resources, either on the [mailing list](mailto:krkn.maintainers@gmail.com) or during a monthly meeting. A simple majority of Maintainers approves the request. The Maintainers may also choose to delegate working with the CNCF to non-Maintainer community members, who will then be added to the [CNCF's Maintainer List](https://github.com/cncf/foundation/blob/main/project-maintainers.csv) for that purpose.

## Code of Conduct

Krkn follows the [CNCF Code of Conduct](https://github.com/cncf/foundation/blob/master/code-of-conduct.md).

> As contributors and maintainers of this project, and in the interest of fostering an open and welcoming community, we pledge to respect all people who contribute through reporting issues, posting feature requests, updating documentation, submitting pull requests or patches, and other activities.

Code of Conduct violations by community members will be discussed and resolved on the [private maintainer mailing list](mailto:krkn.maintainers@gmail.com). If a Maintainer is directly involved in the report, two Maintainers will instead be designated to work with the CNCF Code of Conduct Committee in resolving it.

## Security Response Team

The Maintainers will appoint a Security Response Team to handle security reports. This committee may consist of the Maintainer Council itself. If this responsibility is delegated, the Maintainers will appoint a team of at least two contributors to handle it. The Maintainers will review the composition of this team at least once a year.

The Security Response Team is responsible for handling all reports of security holes and breaches according to the [security policy](SECURITY.md).

To report a security vulnerability, please follow the process outlined in [SECURITY.md](SECURITY.md) rather than filing a public GitHub issue.

## Voting

While most business in Krkn is conducted by "[lazy consensus](https://community.apache.org/committers/lazyConsensus.html)", periodically the Maintainers may need to vote on specific actions or changes. Any Maintainer may demand a vote be taken.

Votes on general project matters may be raised on the [maintainer mailing list](mailto:krkn.maintainers@gmail.com) or during a monthly meeting. Votes on security vulnerabilities or Code of Conduct violations must be conducted exclusively on the [private maintainer mailing list](mailto:krkn.maintainers@gmail.com) or in a closed Maintainer meeting, in order to prevent accidental public disclosure of sensitive information.

Most votes require a **simple majority** of all Maintainers to succeed, except where otherwise noted. Two-thirds majority votes mean at least two-thirds of all existing Maintainers.

| Action | Required Vote |
|--------|--------------|
| Adding a new Maintainer | Simple majority |
| Removing a Maintainer | 2/3 majority |
| Approving CNCF resource requests | Simple majority |
| Modifying this charter | 2/3 majority |

## Modifying this Charter

Changes to this Governance document and its supporting documents may be approved by a 2/3 vote of the Maintainers.
