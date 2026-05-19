# Security Policy

We attach great importance to code security. We are very grateful to the users, security vulnerability researchers, etc. for reporting security vulnerabilities to the Krkn community. All reported security vulnerabilities will be carefully assessed and addressed in a timely manner.


## Security Approach

Krkn follows a proactive security strategy based on continuous vulnerability scanning and risk assessment. Our approach ensures that security issues are identified, evaluated, and remediated as part of our development and release process.

### Vulnerability Scanning with Grype

We use [Grype](https://github.com/anchore/grype), an industry-standard vulnerability scanner, to detect known vulnerabilities in our container images and dependencies. Grype scans are integrated into our CI/CD pipeline and run automatically on:

- **Every pull request**: Scans detect newly introduced vulnerabilities before code is merged
- **Every commit to main branch**: Ensures the main branch maintains our security baseline
- **Container image builds**: Multi-architecture images (amd64, arm64) are scanned before publication
- **Regular scheduled scans**: Weekly scans of published images to detect newly disclosed CVEs

All scan results are published in GitHub Actions summaries with severity breakdowns (Critical, High, Medium, Low) and include both fixed and unfixed vulnerabilities.

### Security Baseline

As of May 2026, we have established a **security baseline** for the Krkn project:

- **Critical CVEs**: 0 (zero tolerance policy)
- **High CVEs**: 7 (all from indirect dependencies, see Accepted Risks below)
- **Medium CVEs**: 3 (all from indirect dependencies, see Accepted Risks below)
- **Low CVEs**: 0 (zero tolerance policy)
- **Total known CVEs**: 12 (91% reduction from previous baseline of 130+ CVEs)

This baseline represents the current state after comprehensive dependency upgrades (Go 1.25.10, Python packages, system libraries). We continuously monitor for new vulnerabilities and commit to maintaining or improving this baseline with each release.

### Risk Assessment and Acceptance Criteria

Not all detected vulnerabilities can be immediately remediated due to dependency constraints or breaking changes. When a vulnerability cannot be fixed, we follow this process:

1. **Impact Analysis**: Assess the actual exploitability in the Krkn container context
2. **Mitigation Evaluation**: Determine if compensating controls or workarounds exist
3. **Upstream Tracking**: Monitor upstream projects for fixes or compatible versions
4. **Documentation**: Explicitly document accepted risks in this security policy
5. **Regular Review**: Re-evaluate accepted risks quarterly and after major dependency releases

We accept vulnerabilities **only when**:
- They exist in transitive dependencies of essential binaries (e.g., OpenShift CLI `oc`)
- Upgrading would introduce breaking changes that render the tool unusable
- The vulnerability is not exploitable in Krkn's container execution model
- We have no control over the vendored dependency versions

All accepted risks are documented below and will be remediated as soon as compatible upstream versions are available.


## Current Security Baseline

**Total Vulnerabilities**: 12 CVEs (reduced from 130+ in previous baseline - 91% reduction)

**Breakdown by Severity**:
- Critical: 0
- High: 7
- Medium: 3  
- Low: 0
- Negligible: 0

**Breakdown by Type**:
- Python direct dependencies: 0
- Python transitive dependencies: 2 (cbor2 - constraint by arcaflow-plugin-sdk)
- Go stdlib: 0 (all binaries compiled with Go 1.25.10)
- Go vendored dependencies (oc): 10 (embedded in OpenShift CLI binary)


## Known Accepted Risks

The following vulnerabilities are **accepted risks** due to dependency constraints in essential third-party binaries. These are **not vulnerabilities in Krkn code**, but rather in transitive dependencies of tools we depend on. We are actively monitoring upstream projects and will upgrade as soon as compatible versions are available.

### Python Transitive Dependencies (2 CVEs)

**cbor2 5.6.5** - Pinned by arcaflow-plugin-sdk==0.14.3
- GHSA-3c37-wwvx-h642 (High): Buffer overflow in CBOR decoder
- GHSA-wcj4-jw5j-44wh (Medium): Uncontrolled resource consumption

**Why Accepted**: The arcaflow-plugin-sdk dependency requires cbor2 <5.7.0. Upgrading arcaflow-plugin-sdk to a version compatible with cbor2 >=5.9.0 would require Python 3.12+, but Krkn maintains Python 3.11 compatibility for broader platform support.

**Mitigation**: CBOR decoding is not used in Krkn's core chaos scenarios. The vulnerability is isolated to optional arcaflow plugin integration.

**Remediation Plan**: Upgrade to Python 3.12 and arcaflow-plugin-sdk 0.14.4+ in the next major version release.

---

### OpenShift CLI (oc) Vendored Dependencies (10 CVEs)

The OpenShift CLI (`oc`) binary is compiled from source with vendored Go dependencies. These dependencies are embedded in the `oc` binary and cannot be independently upgraded without modifying the `oc` source code, which would break compatibility with OpenShift clusters.

**moby/buildkit v0.12.5** - Requires v0.28.1 for CVE fixes
- GHSA-4c29-8rgm-jvjj (High): Buildkit mount cache race condition
- GHSA-4vrq-3vrq-g6gg (High): Privilege escalation in buildkit

**Why Accepted**: Upgrading to moby/buildkit v0.28.1 introduces breaking API changes (`undefined: archive.Compression`) incompatible with docker/docker v28.5.2 vendored in `oc`. The `oc` CLI uses these APIs for image layer manipulation.

**Mitigation**: Krkn does not use buildkit functionality. These vulnerabilities are not exploitable in the Krkn container execution model.

**Remediation Plan**: Will upgrade when OpenShift `oc` upstream adopts moby/buildkit v0.28.1+ or provides a compatible workaround.

---

**distribution/distribution v3.0.0** - Requires v3.1.0+ for CVE fixes
- GHSA-f2g3-hh2r-cwgc (High): Registry API authentication bypass
- GHSA-3p65-76g6-3w7r (High): Path traversal in image layers
- GHSA-6pjf-3r9x-m592 (Medium): Denial of service in manifest parsing

**Why Accepted**: The distribution/distribution v3.1.0+ release removed several packages (`registry/client`, `manifest/schema1`, `reference`) that `oc` depends on for OCI image operations. Upgrading breaks `oc` compilation.

**Mitigation**: Krkn does not expose container registry APIs. The `oc` CLI usage in Krkn is limited to Kubernetes/OpenShift cluster operations, not image distribution.

**Remediation Plan**: Will upgrade when OpenShift `oc` migrates to distribution/distribution v3.1.0+ API.

---

**docker/docker v28.5.2** - Unfixed vulnerabilities in Docker engine
- GHSA-pxq6-2prw-chj9 (Medium): Docker daemon API access control
- GHSA-rg2x-37c3-w2rh (High): Container escape via runc
- GHSA-vp62-88p7-qqf5 (Medium): Symlink-exchange attack in docker cp
- GHSA-x744-4wpc-v9h2 (High): Docker daemon privilege escalation
- GHSA-x86f-5xw2-fm2r (High): Docker socket access control bypass

**Why Accepted**: These are vendored in the OpenShift `oc` binary and cannot be updated independently. Krkn does not run the Docker daemon or expose Docker APIs - we only use the Docker SDK client library for node chaos scenarios (start/stop/restart nodes).

**Mitigation**: 
- Krkn containers run rootless when possible
- Docker socket access is restricted to chaos scenario execution (node power cycling)
- No Docker daemon is run inside Krkn containers
- Docker SDK is used only for API calls to external Docker daemons on cluster nodes

**Remediation Plan**: Will upgrade when OpenShift `oc` adopts a patched docker/docker version.

---

### Commitment to Remediation

We are committed to eliminating these accepted risks as soon as technically feasible:

1. **Quarterly Review**: We review all accepted risks every quarter to check for upstream fixes
2. **Upstream Engagement**: We actively track OpenShift `oc` releases and dependency updates
3. **Automated Monitoring**: GitHub Dependabot alerts notify us of new patches
4. **Prompt Updates**: When compatible versions become available, we upgrade within one release cycle

**Last Reviewed**: 2026-05-19  
**Next Review**: 2026-08-19


## Vulnerability Remediation History

### 2026-05-18: Major Dependency Upgrade

**Result**: Reduced from 130+ CVEs to 12 CVEs (91% reduction)

We conducted a comprehensive security audit and dependency upgrade, fixing all Critical and Low severity CVEs, and reducing High/Medium severity CVEs by over 85%.

**Key Improvements**:
- ✅ Fixed all Python Critical CVEs (requests, urllib3 upgrades)
- ✅ Eliminated all Go stdlib CVEs (compiled all binaries with Go 1.25.10)
- ✅ Fixed 118+ High/Medium/Low CVEs across Python and Go dependencies
- ✅ Upgraded docker SDK to 7.0+ (native Unix socket support, enables requests>=2.32)
- ✅ Compiled yq v4.44.6 from source with Go 1.25.10 (Fedora package uses vulnerable Go 1.26rc2)
- ✅ Pinned security-critical Go modules (go-git, fulcio, sigstore, spdystream, AWS SDK components)

**Remaining Risks**: 12 CVEs in transitive dependencies of essential third-party binaries (documented above)


## Security Checks

Krkn leverages multiple security scanning tools to ensure comprehensive vulnerability detection:

- **[Grype](https://github.com/anchore/grype)**: Primary vulnerability scanner for container images and dependencies, integrated into CI/CD
- **[Snyk](https://snyk.io/)**: Additional dependency scanning with curated vulnerability database
- **GitHub Dependabot**: Automated dependency update alerts for Python and Go modules

Security vulnerability checks are enabled for each pull request, giving developers immediate feedback on newly introduced vulnerabilities. All security scan results are published in GitHub Actions job summaries for transparency.

 
## Reporting a Vulnerability

The Krkn project treats security vulnerabilities seriously, and we strive to take action quickly when required.

The project requests that security issues be disclosed in a responsible manner to allow adequate time to respond. If a security issue or vulnerability has been found, please disclose the details to our dedicated email address:

**cncf-krkn-maintainers@lists.cncf.io**

You can also use the [GitHub vulnerability report mechanism](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability#privately-reporting-a-security-vulnerability) to report the security vulnerability.

Please include as much information as possible with the report. The following details assist with analysis efforts:
  - Description of the vulnerability
  - Affected component (version, commit, branch, etc.)
  - Affected code (file path, line numbers)
  - Proof-of-concept or exploit code (if available)
  - Impact assessment (confidentiality, integrity, availability)


## Security Team

The security team currently consists of the [Maintainers of Krkn](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md).

All security issues are reviewed by at least two maintainers, and critical vulnerabilities are escalated to the full maintainer team for immediate triage.


## Process and Supported Releases

The Krkn security team will investigate and provide a fix in a timely manner depending on the severity:

- **Critical vulnerabilities**: Patched within 7 days, emergency release if needed
- **High vulnerabilities**: Patched within 30 days, included in next scheduled release
- **Medium vulnerabilities**: Patched within 90 days, bundled with feature releases
- **Low vulnerabilities**: Addressed in regular maintenance cycles

Fixes will be included in new releases of Krkn, and details will be documented in release notes and this security policy. We maintain security updates for the current major version and the previous major version (N and N-1).
