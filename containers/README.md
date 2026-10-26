
### Kraken image

Container image gets automatically built by quay.io at [Kraken image](https://quay.io/redhat-chaos/krkn).


### Run containerized version

Refer [instructions](https://krkn-chaos.dev/docs/installation/) for information on how to run the containerized version of kraken.


### Run Custom Kraken Image

Refer to [instructions](https://github.com/redhat-chaos/krkn/blob/main/containers/build_own_image-README.md) for information on how to run a custom containerized version of kraken using podman.

### Check a built image without running a scenario

Set `KRKN_DEPENDENCY_CHECK=1` to check that the installed Python packages have
no declared dependency conflicts and that the Krkn CLI can start. This exits
before SSH setup and does not connect to a cluster or run a chaos scenario.

```sh
docker run --rm -e KRKN_DEPENDENCY_CHECK=1 quay.io/redhat-chaos/krkn:latest
```

Use the same command with the candidate image tag in CI after building or
patching it. This is a smoke check; functional tests still need a separate
disposable Kubernetes cluster.

### Build the base image locally

The Dockerfile expects architecture-matched `oc`, `virtctl`, and `yq` binaries in
`containers/tools/`. Build them before compiling the Dockerfile; `oc` requires
`libkrb5-dev` on Debian/Ubuntu. Use the latest stable Go toolchain supported by
the cloned sources.

```sh
scripts/build-container-tool.sh oc
scripts/build-container-tool.sh virtctl
scripts/build-container-tool.sh yq
./containers/compile_dockerfile.sh
docker build -t localhost/krkn:local containers/
```

The CI workflow builds these binaries in parallel, uploads them as artifacts,
then downloads them for each architecture before building and patching the local
base image.

### Release and security refresh

The Docker image workflow keeps the normal tag release path. Both releases and
security refreshes build the `oc`, `virtctl`, and `yq` binaries for amd64 and
arm64 outside the Dockerfile. The Fedora 45 Dockerfile runs `dnf upgrade
--refresh` before installing Krkn; after the image build, Copa applies available
Python dependency fixes. Grype checks Fedora and Go packages, Trivy supplies
the Python report for Copa, and both platforms must complete the image scans and
pass functional tests before publication. Remaining CVEs do not block
publication. The run summary records vulnerability
counts and the source commits of the Go tools; JSON reports are downloadable
as run artifacts.
The image labels record the Krkn release tag and the workflow source commit.
`setuptools` stays at 81.0.0 because the vSphere SDK still imports the
[`pkg_resources` module removed in 82.0.0](https://setuptools.pypa.io/en/stable/deprecated/pkg_resources.html).
The scanner's [GHSA-xmj3-9gf7-h52w](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)
and [CVE-2026-59890](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c)
findings affect Windows wheel installation and macOS source distributions,
respectively. They are shown separately in the run summary for this Linux image.
All findings remain in the raw reports.
The existing `arcaflow-plugin-sdk 0.14.3` constraint also keeps `cbor2` at
5.6.5 on Python 3.11. Its three documented findings are shown separately and
kept out of the Copa input: forcing `cbor2` to 5.9.0 makes `pip check` fail.
New findings outside these exact accepted versions and advisory IDs are
reported separately and remain eligible for Copa patching. See
[SECURITY.md](../SECURITY.md) for the risk assessment.
The same exact-match Grype policy is used by the daily scan, so accepted
findings alone do not schedule a rebuild. The raw reports always include them.
Add a `SLACK_WEBHOOK_URL` repository secret with an incoming webhook for the
desired channel to receive a concise report after each scheduled scan, manual
refresh or release, including scans that find CVEs but do not publish an image.
The message links to the run summary and downloadable full JSON reports. If the
secret is absent, the run summary records that Slack delivery was skipped.

Every day, the workflow scans both platforms of
`quay.io/krkn-chaos/krkn:latest`. If Grype reports a vulnerability with an
available fix, it rebuilds the recorded Krkn release tag and publishes a signed
multi-platform image as `vX.Y.Z-patch-YYYYMMDD-RUN_ID-ATTEMPT`. The release tag remains
unchanged; `latest` moves to the validated patch tag, followed by a krkn-hub
rebuild. A refresh can also be started with **Run workflow** on `main`. Set
`force_refresh` to rebuild without scanner findings, or `source_tag` to select
a release explicitly. The first tagged image built by this workflow records
its source version in `org.opencontainers.image.version`; before that first
release, a manual refresh needs `source_tag`.

To restore a prior signed release or patch, run the workflow on `main` with
`rollback_tag`. It verifies the manifest signatures in both Quay repositories,
repoints both `latest` tags to those digests, and rebuilds krkn-hub. Keep
`source_tag` empty and `force_refresh` off when rolling back. Release and
refresh runs share one concurrency group so they cannot promote `latest` at
the same time.
