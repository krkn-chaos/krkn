# Use with --slurpfile policy <trivy-scan-policy output> and --arg target <binary path>.
# An empty target includes all Go binaries for summary/reporting.
# Keep only actionable Go findings in the Trivy shape required by Copa.
.Results |= [
  .[]
  | select((.Type == "gobinary" or .Type == "gomod") and ($target == "" or .Target == $target))
  | . as $result
  | .Vulnerabilities |= [
      .[]? as $vulnerability
      | select(any($policy[0].go_actionable_findings[];
          .target == $result.Target
          and .package == $vulnerability.PkgName
          and .installed == $vulnerability.InstalledVersion
          and .id == $vulnerability.VulnerabilityID))
      | $vulnerability
    ]
  | select(.Vulnerabilities | length > 0)
]
