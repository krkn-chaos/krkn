# Grype is the source of truth for Fedora RPM findings only.
def os_package: .artifact.type == "rpm";
def fixable: .vulnerability.fix.state == "fixed";

{
  total: ([.matches[]? | select(os_package and fixable)] | length),
  actionable: ([.matches[]? | select(os_package and fixable)] | length),
  actionable_findings: [.matches[]? | select(os_package and fixable)
    | {id: .vulnerability.id, name: .artifact.name, version: .artifact.version,
       location: .artifact.locations[0].path}]
}
