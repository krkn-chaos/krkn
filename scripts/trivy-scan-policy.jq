# Only installed Go/Python dependencies with published fixes can request a rebuild.
def installed_python($result; $vulnerability):
  [$result.Packages[]? | select(.Identifier.UID == $vulnerability.PkgIdentifier.UID)] as $matches
  | ($matches | length) == 0
    or any($matches[]; .AnalyzedBy == "python-pkg" or .AnalyzedBy != "sbom");

def accepted_python($vulnerability):
  ($vulnerability.PkgName == "setuptools" and $vulnerability.InstalledVersion == "81.0.0"
    and ($vulnerability.VulnerabilityID == "GHSA-xmj3-9gf7-h52w"
      or $vulnerability.VulnerabilityID == "CVE-2026-59890"))
  or ($vulnerability.PkgName == "cbor2" and $vulnerability.InstalledVersion == "5.6.5"
    and ($vulnerability.VulnerabilityID == "CVE-2025-64076"
      or $vulnerability.VulnerabilityID == "CVE-2026-26209"
      or $vulnerability.VulnerabilityID == "CVE-2025-68131"));

def accepted_go($result; $vulnerability):
  $result.Target == "usr/bin/oc"
  and (
    ($vulnerability.PkgName == "github.com/moby/buildkit" and $vulnerability.InstalledVersion == "v0.12.5"
      and any($vulnerability.References[]?; test("GHSA-(4c29-8rgm-jvjj|4vrq-3vrq-g6gg|7236-3392-c5c6)")))
    or ($vulnerability.PkgName == "github.com/moby/go-archive" and $vulnerability.InstalledVersion == "v0.1.0"
      and any($vulnerability.References[]?; contains("GHSA-hfg8-hc9c-6c3h")))
    or ($vulnerability.PkgName == "github.com/distribution/distribution/v3"
      and $vulnerability.InstalledVersion == "v3.0.0-20230519140516-983358f8e250"
      and any($vulnerability.References[]?; test("GHSA-(3p65-76g6-3w7r|6pjf-3r9x-m592|685w-q87j-wqw3)")))
  );

[
  .Results[]? as $result
  | select($result.Type == "gobinary" or $result.Type == "gomod" or $result.Type == "python-pkg")
  | $result.Vulnerabilities[]? as $vulnerability
  | select(($vulnerability.FixedVersion // "") != "")
  | select($result.Type != "python-pkg" or installed_python($result; $vulnerability))
  | {
      language: (if $result.Type == "python-pkg" then "python" else "go" end),
      accepted: (if $result.Type == "python-pkg" then accepted_python($vulnerability) else accepted_go($result; $vulnerability) end)
    }
] as $matches
| {
    total: ($matches | length),
    accepted: ([$matches[] | select(.accepted)] | length),
    actionable: ([$matches[] | select(.accepted | not)] | length),
    go_actionable: ([$matches[] | select(.language == "go" and (.accepted | not))] | length),
    python_actionable: ([$matches[] | select(.language == "python" and (.accepted | not))] | length)
  }
