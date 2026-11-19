
### Kraken image

Container image gets automatically built by quay.io at [Kraken image](https://quay.io/redhat-chaos/krkn).


### Run containerized version

Refer [instructions](https://krkn-chaos.dev/docs/installation/) for information on how to run the containerized version of kraken.


### Run Custom Kraken Image

Refer to [instructions](https://github.com/redhat-chaos/krkn/blob/main/containers/build_own_image-README.md) for information on how to run a custom containerized version of kraken using podman.


### Automated vulnerability remediation

Two workflows handle the separate scan and remediation steps:

- **Scan Krkn Base Image** runs every day at 09:00 Eastern time, scans
  `quay.io/krkn-chaos/krkn:latest` with Grype, uploads the JSON report and a
  unique-ID severity summary, and sends Slack counts for Critical, High,
  Medium, Low, Negligible, and Unknown findings with a link to
  **Patch Krkn Base Image**. It can also be run manually for a scan on demand.
- **Patch Krkn Base Image** is a manual workflow. Select the Krkn source ref
  and a publish target. The default `beta` target publishes to `quay.io/krkn-chaos/krkn-beta`
  without updating production tags or rebuilding krkn-hub. Select `production`
  only for an approved release; it promotes both production repositories and
  rebuilds krkn-hub after all gates pass. It scans the three Go tool source trees
  with govulncheck, applies fixed module versions with `go get` (allowing required
  transitive bumps), recompiles the binaries for amd64 and arm64, and uploads the
  binaries, Go manifests, and scan reports as workflow artifacts. It then applies
  `pip-audit --fix` to the selected Krkn source ref's `requirements.txt`, builds
  the remediated Python dependency image and both candidate architectures, runs
  the full functional v2 suite on amd64, and performs runtime checks on arm64.
  After the gates pass it signs and promotes a `patch-<run>-<attempt>` tag and
  `latest` in the selected repository. The beta target stops there; the production
  target also promotes the redhat-chaos mirror and rebuilds `krkn-hub`. Production
  manifests are both staged and verified before public tags change; the manual and
  standard release workflows share a publication lock, and a failed second-registry
  promotion restores prior `latest` digests where possible.

The image build in this workflow is separate from the existing tag-triggered
release workflow. The standard release flow is unchanged; both publishing paths
share a lock so they cannot race while updating public image tags.

The workflows require the existing Quay and Cosign secrets used by
`docker-image.yml`, plus `KRKN_IMAGE_SECURITY_REPORT_SLACK_WEBHOOK_URL` for
scheduled scan and final remediation notifications.
`pip-audit` and Grype JSON reports are uploaded as artifacts. Remaining
vulnerabilities are reported without failing solely because they remain; image
builds and `pip check` must succeed, and the functional v2 suite is the release
gate. Slack receives a summary of unique vulnerability IDs by severity from the
final amd64 and arm64 candidate scans. The temporary requirements update is
packaged in the candidate image and does not modify the source repository.
