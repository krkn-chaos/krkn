
### Kraken image

Container image gets automatically built by quay.io at [Kraken image](https://quay.io/redhat-chaos/krkn).


### Run containerized version

Refer [instructions](https://krkn-chaos.dev/docs/installation/) for information on how to run the containerized version of kraken.


### Run Custom Kraken Image

Refer to [instructions](https://github.com/redhat-chaos/krkn/blob/main/containers/build_own_image-README.md) for information on how to run a custom containerized version of kraken using podman.


### Automated vulnerability remediation

Two workflows handle the separate scan and remediation steps:

- **Scan Krkn Base Image** runs every day at 09:00 Eastern time, scans
  `quay.io/krkn-chaos/krkn:latest` with Grype, uploads the JSON report, and
  sends a Slack message with a link to **Patch Krkn Base Image**. It can also
  be run manually for a scan on demand.
- **Patch Krkn Base Image** is a manual workflow. Select the Krkn source ref and
  the maximum Go/Python update level (`patch`, `minor`, or `major`). It patches
  the three Go tool source trees with Copa and Grype, recompiles the binaries
  for amd64 and arm64, and uploads the binaries plus the original and patched
  Go manifests and scan reports as workflow artifacts. It then patches the
  Python runtime dependencies in an intermediate image, builds both candidate
  architectures, runs the full functional v2 suite on amd64, and performs
  runtime checks on arm64. Only after the gates pass does it sign and promote a
  `patch-<run>-<attempt>` tag and `latest` in both existing Quay repositories,
  then rebuild `krkn-hub`.

The image build in this workflow is separate from the existing tag-triggered
release workflow. It does not change the standard release path.

The workflows require the existing Quay and Cosign secrets used by
`docker-image.yml`, plus `SLACK_WEBHOOK_URL` for the scheduled notification.
Copa language dependency patching remains experimental; the workflow checks the
selected update level, runs `pip check`, rescans after patching, and uses the
functional suite as the release gate. Python package versions are captured in
a `pip freeze` artifact because Copa patches the installed dependency set; it
does not rewrite Krkn's `requirements.txt`.
