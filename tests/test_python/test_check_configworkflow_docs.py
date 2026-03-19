"""Tests for check_configworkflow_docs.py."""

import os
import sys
import unittest


TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(TEST_DIR, "..", "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from check_configworkflow_docs import parse_changed_variables, render_report  # pylint: disable=wrong-import-position


class TestCheckConfigWorkflowDocs(unittest.TestCase):
    """Unit tests for config/doc sync checks."""

    def test_parse_changed_variables(self):
        """Classify added, removed, and modified variables from a diff."""

        diff_text = """
+  NEW_VAR: false
-  OLD_VAR: ""
-  MOD_VAR: "old"
+  MOD_VAR: "new"
"""
        added_changes, removed_changes, modified_changes = parse_changed_variables(diff_text)

        self.assertEqual([change.name for change in added_changes], ["NEW_VAR"])
        self.assertEqual([change.name for change in removed_changes], ["OLD_VAR"])
        self.assertEqual([change.name for change in modified_changes], ["MOD_VAR"])
        self.assertEqual(modified_changes[0].old, '"old"')
        self.assertEqual(modified_changes[0].new, '"new"')

    def test_render_report_flags_missing_and_stale_defaults(self):
        """Detect missing doc entries and default mismatches."""

        added_changes, removed_changes, modified_changes = parse_changed_variables(
            """
+  NEW_VAR: false
-  MOD_VAR: "old"
+  MOD_VAR: "new"
"""
        )
        doc_text = """
``MOD_VAR``: (Default: ``"old"``)
   Existing text.
"""

        report, issues_found = render_report(
            added_changes=added_changes,
            removed_changes=removed_changes,
            modified_changes=modified_changes,
            doc_text=doc_text,
            base_ref="origin/develop",
        )

        self.assertTrue(issues_found)
        self.assertIn("Missing entries", report)
        self.assertIn("`NEW_VAR`", report)
        self.assertIn("Stale defaults", report)
        self.assertIn("docs show", report)


if __name__ == "__main__":
    unittest.main()
