# Beta Features Policy

## Overview

Beta features provide users early access to new capabilities before they reach full stability and general availability (GA). These features allow maintainers to gather feedback, validate usability, and improve functionality based on real-world usage.

Beta features are intended for experimentation and evaluation. While they are functional, they may not yet meet the stability, performance, or backward compatibility guarantees expected from generally available features.

---

## What is a Beta Feature

A **Beta feature** is a feature that is released for user evaluation but is still under active development and refinement.

Beta features may have the following characteristics:

- Functionally usable but still evolving
- APIs or behavior may change between releases
- Performance optimizations may still be in progress
- Documentation may be limited or evolving
- Edge cases may not be fully validated

Beta features should be considered **experimental and optional**.

---

## User Expectations

Users trying Beta features should understand the following:

- Stability is not guaranteed
- APIs and functionality may change without notice
- Backward compatibility is not guaranteed
- The feature may evolve significantly before GA
- Production use should be evaluated carefully

We strongly encourage users to provide feedback to help improve the feature before it becomes generally available.

---

## Beta Feature Identification

All Beta features are clearly identified to ensure transparency.

### In Release Notes

Beta features will be marked with a **[BETA]** tag.

Example: [BETA] Krkn Resilience Score


### In Documentation

Beta features will include a notice similar to:

> **Beta Feature**  
> This feature is currently in Beta and is intended for early user feedback. Behavior, APIs, and stability may change in future releases.

---

## Feature Lifecycle

Features typically progress through the following lifecycle stages.

### 1. Development
The feature is under active development and may not yet be visible to users.

### 2. Beta
The feature is released for early adoption and feedback.

Characteristics:

- Feature is usable
- Feedback is encouraged
- Stability improvements are ongoing

### 3. Stabilization
Based on user feedback and testing, the feature is improved to meet stability and usability expectations.

### 4. General Availability (GA)

The feature is considered stable and production-ready.

GA features provide:

- Stable APIs
- Backward compatibility guarantees
- Complete documentation
- Full CI test coverage

---

## Promotion to General Availability

A Beta feature may be promoted to GA once the following criteria are met:

- Critical bugs are resolved
- Feature stability has improved through testing
- APIs and behavior are stable
- Documentation is complete
- Community feedback has been incorporated

The promotion will be announced in the release notes.

Example: Feature promoted from Beta to GA


---

## Deprecation of Beta Features

In some cases, a Beta feature may be redesigned or discontinued.

If this happens:

- The feature will be marked as **Deprecated**
- A removal timeline will be provided
- Alternative approaches will be documented when possible

Example: [DEPRECATED] This feature will be removed in a future release.

---

## Contributing Feedback
User feedback plays a critical role in improving Beta features.

Users are encouraged to report:

- Bugs
- Usability issues
- Performance concerns
- Feature suggestions

Feedback can be submitted through:

- Krkn GitHub Issues
- Krkn GitHub Discussions
- Krkn Community channels

Please include **Beta feature context** when reporting issues.
Your feedback helps guide the roadmap and ensures features are production-ready before GA.
