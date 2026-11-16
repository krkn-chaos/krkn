
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
- **Patch Krkn Base Image** is a manual workflow. Select the Krkn source ref,
  the maximum Go/Python update level (`patch`, `minor`, or `major`), and a publish
  target. The default `beta` target publishes to `quay.io/krkn-chaos/krkn-beta`
  without updating production tags or rebuilding krkn-hub. Select `production`
  only for an approved release; it promotes both production repositories and
  rebuilds krkn-hub after all gates pass. It patches
  the three Go tool source trees with Copa and Grype, recompiles the binaries
  for amd64 and arm64, and uploads the binaries plus the original and patched
  Go manifests and scan reports as workflow artifacts. It then patches the
  Python runtime dependencies in an intermediate image, builds both candidate
  architectures, runs the full functional v2 suite on amd64, and performs
  runtime checks on arm64. After the gates pass it signs and promotes a
  `patch-<run>-<attempt>` tag and `latest` in the selected repository. The beta
  target stops there; the production target also promotes the redhat-chaos mirror
  and rebuilds `krkn-hub`. Production manifests are both staged and verified
  before public tags change; the manual and standard release workflows share a
  publication lock, and a failed second-registry promotion restores prior
  `latest` digests where possible.

The image build in this workflow is separate from the existing tag-triggered
release workflow. The standard release flow is unchanged; both publishing paths
share a lock so they cannot race while updating public image tags.

The workflows require the existing Quay and Cosign secrets used by
`docker-image.yml`, plus `SLACK_WEBHOOK_URL` for both scheduled scan and final remediation notifications.
Copa language dependency patching remains experimental; the workflow applies
the selected update level where possible, records remaining findings in its
reports without failing solely because they remain, runs `pip check`, and uses
the functional suite as the release gate. At the end, Slack receives a summary
of unique vulnerability IDs by severity from the final amd64 and arm64 candidate
scans, and the full JSON is uploaded as a workflow artifact even when a gate
fails. Python package versions are captured in a `pip freeze` artifact because
Copa patches the installed dependency set; it does not rewrite Krkn's
`requirements.txt`.
