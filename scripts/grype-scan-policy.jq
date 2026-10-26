# Exact findings already documented in SECURITY.md. Keep raw Grype reports intact.
def accepted_oc:
  (.artifact.language // "" | ascii_downcase) == "go"
  and any(.artifact.locations[]?; .path == "/usr/bin/oc")
  and (
    (.artifact.name == "github.com/moby/buildkit" and .artifact.version == "v0.12.5"
      and (.vulnerability.id == "GHSA-4c29-8rgm-jvjj"
        or .vulnerability.id == "GHSA-4vrq-3vrq-g6gg"
        or .vulnerability.id == "GHSA-7236-3392-c5c6"))
    or (.artifact.name == "github.com/moby/go-archive" and .artifact.version == "v0.1.0"
      and .vulnerability.id == "GHSA-hfg8-hc9c-6c3h")
    or (.artifact.name == "github.com/distribution/distribution/v3"
      and .artifact.version == "v3.0.0-20230519140516-983358f8e250"
      and (.vulnerability.id == "GHSA-3p65-76g6-3w7r"
        or .vulnerability.id == "GHSA-6pjf-3r9x-m592"
        or .vulnerability.id == "GHSA-685w-q87j-wqw3"))
  );

def accepted_python:
  (.artifact.name == "setuptools" and .artifact.version == "81.0.0"
    and (.vulnerability.id == "GHSA-h35f-9h28-mq5c"
      or .vulnerability.id == "GHSA-xmj3-9gf7-h52w"))
  or (.artifact.name == "cbor2" and .artifact.version == "5.6.5"
    and (.vulnerability.id == "GHSA-9q9c-vjxh-p795"
      or .vulnerability.id == "GHSA-3c37-wwvx-h642"
      or .vulnerability.id == "GHSA-wcj4-jw5j-44wh"));

def fixable: .vulnerability.fix.state == "fixed";
def accepted: accepted_oc or accepted_python;
def go_package: (.artifact.language // "" | ascii_downcase) == "go";

{
  total: ([.matches[]? | select(fixable)] | length),
  accepted: ([.matches[]? | select(fixable and accepted)] | length),
  actionable: ([.matches[]? | select(fixable and (accepted | not))] | length),
  actionable_findings: [.matches[]? | select(fixable and (accepted | not))
    | {id: .vulnerability.id, name: .artifact.name, version: .artifact.version,
       location: .artifact.locations[0].path}],
  go_total: ([.matches[]? | select(fixable and go_package)] | length),
  go_accepted: ([.matches[]? | select(fixable and go_package and accepted_oc)] | length),
  go_actionable: ([.matches[]? | select(fixable and go_package and (accepted_oc | not))] | length)
}
