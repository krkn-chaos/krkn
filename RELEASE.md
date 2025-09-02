### Release Protocol: The Community-First Cycle

This document outlines the project's release protocol, a methodology designed to ensure a responsive and transparent development process that is closely aligned with the needs of our users and contributors. This protocol is tailored for projects in their early stages, prioritizing agility and community feedback over a rigid, time-boxed schedule.

#### 1. Key Principles

* **Community as the Compass:** The primary driver for all development is feedback from our user and contributor community.
* **Prioritization by Impact:** Tasks are prioritized based on their impact on user experience, the urgency of bug fixes, and the value of community-contributed features.
* **Event-Driven Releases:** Releases are not bound by a fixed calendar. New versions are published when a significant body of work is complete, a critical issue is resolved, or a new feature is ready for adoption.
* **Transparency and Communication:** All development decisions, progress, and plans are communicated openly through our issue tracker, pull requests, and community channels.

#### 2. The Release Lifecycle

The release cycle is a continuous flow of activities rather than a series of sequential phases.

**2.1. Discovery & Prioritization**
* New features and bug fixes are identified through user feedback on our issue tracker, community discussions, and direct contributions.
* The core maintainers, in collaboration with the community, continuously evaluate and tag issues to create an open and dynamic backlog.

**2.2. Development & Code Review**
* Work is initiated based on the highest-priority items in the backlog.
* All code contributions are made via pull requests (PRs).
* PRs are reviewed by maintainers and other contributors to ensure code quality, adherence to project standards, and overall stability.

**2.3. Release Readiness**
A new release is considered ready when one of the following conditions is met:
* A major new feature has been completed and thoroughly tested.
* A critical security vulnerability or bug has been addressed.
* A sufficient number of smaller improvements and fixes have been merged, providing meaningful value to users.

**2.4. Versioning**
We adhere to [**Semantic Versioning 2.0.0**](https://semver.org/).
* **Major version (`X.y.z`)**: Reserved for releases that introduce breaking changes.
* **Minor version (`x.Y.z`)**: Used for new features or significant non-breaking changes.
* **Patch version (`x.y.Z`)**: Used for bug fixes and small, non-functional improvements.

#### 3. Roles and Responsibilities

* **Maintainers:** The [core team](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md) responsible for the project's health. Their duties include:
    * Facilitating community discussions and prioritization.
    * Reviewing and merging pull requests.
    * Cutting and announcing official releases.
* **Contributors:** The community. Their duties include:
    * Reporting bugs and suggesting new features.
    * Contributing code and documentation via pull requests.
    * Engaging in discussions and providing feedback.

#### 4. Adoption and Future Evolution

This protocol is designed for the current stage of the project. As the project matures and the contributor base grows, the maintainers will evaluate the need for a more structured methodology to ensure continued scalability and stability.

