"""Check that ConfigWorkflow.rst stays in sync with config_defaults.yaml changes."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SAFE_DIRECTORY = REPO_ROOT.as_posix()
CONFIG_PATH = Path("ush/config_defaults.yaml")
DOC_PATH = Path("doc/UsersGuide/CustomizingTheWorkflow/ConfigWorkflow.rst")
COMMENT_MARKER = "<!-- configworkflow-doc-check -->"
VAR_LINE_RE = re.compile(r"^[+-](?![+-])\s*([A-Z][A-Z0-9_]+):\s*(.*?)\s*$")


@dataclass(frozen=True)
class VariableChange:
    """A changed config variable."""

    name: str
    old: str | None = None
    new: str | None = None


def run_git(*args: str) -> str:
    """Run git in the repository root and return stdout."""

    result = subprocess.run(
        ["git", "-c", f"safe.directory={SAFE_DIRECTORY}", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def get_merge_base(base_ref: str) -> str:
    """Return the merge-base between HEAD and the base ref."""

    return run_git("merge-base", "HEAD", base_ref).strip()


def get_diff_text(base_ref: str) -> str:
    """Return the config diff against the merge base."""

    merge_base = get_merge_base(base_ref)
    return run_git("diff", "--unified=0", f"{merge_base}...HEAD", "--", str(CONFIG_PATH))


def parse_changed_variables(diff_text: str) -> tuple[list[VariableChange], list[VariableChange], list[VariableChange]]:
    """Parse added, removed, and modified variables from a git diff."""

    removed: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}

    for line in diff_text.splitlines():
        match = VAR_LINE_RE.match(line)
        if not match:
            continue
        name, value = match.groups()
        if line.startswith("-"):
            removed.setdefault(name, []).append(value)
        elif line.startswith("+"):
            added.setdefault(name, []).append(value)

    added_changes: list[VariableChange] = []
    removed_changes: list[VariableChange] = []
    modified_changes: list[VariableChange] = []

    for name in sorted(set(removed) | set(added)):
        old_vals = removed.get(name, [])
        new_vals = added.get(name, [])
        if old_vals and new_vals:
            modified_changes.append(VariableChange(name=name, old=old_vals[-1], new=new_vals[-1]))
        elif new_vals:
            added_changes.append(VariableChange(name=name, new=new_vals[-1]))
        else:
            removed_changes.append(VariableChange(name=name, old=old_vals[-1]))

    return added_changes, removed_changes, modified_changes


def load_doc_text() -> str:
    """Load the documentation file."""

    return (REPO_ROOT / DOC_PATH).read_text(encoding="utf-8")


def has_variable_doc(doc_text: str, name: str) -> bool:
    """Return True if the RST contains an explicit entry for the variable."""

    return f"``{name}``" in doc_text


def extract_doc_default(doc_text: str, name: str) -> str | None:
    """Extract the inline documented default for a variable if present."""

    pattern = re.compile(
        rf"^``{re.escape(name)}``:\s+\(Default:\s*(.*?)\)\s*$",
        re.MULTILINE,
    )
    match = pattern.search(doc_text)
    if not match:
        return None
    return match.group(1).strip()


def normalize_default(value: str | None) -> str | None:
    """Normalize config and documentation defaults for comparison."""

    if value is None:
        return None
    normalized = value.strip()
    if normalized.endswith(","):
        normalized = normalized[:-1].rstrip()
    normalized = normalized.replace("``", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def format_default(value: str | None) -> str:
    """Format a default value for human-readable output."""

    if value is None:
        return "unknown"
    return value


def build_snippet(name: str, value: str | None) -> str:
    """Generate a minimal RST placeholder snippet."""

    return (
        f"``{name}``: (Default: ``{format_default(value)}``)\n"
        f"   TODO: document ``{name}``.\n"
    )


def render_report(
    added_changes: list[VariableChange],
    removed_changes: list[VariableChange],
    modified_changes: list[VariableChange],
    doc_text: str,
    base_ref: str,
) -> tuple[str, bool]:
    """Create a Markdown report and return whether issues were found."""

    missing_entries: list[VariableChange] = []
    stale_defaults: list[tuple[str, str, str]] = []
    stale_removed: list[VariableChange] = []

    for change in [*added_changes, *modified_changes]:
        if not has_variable_doc(doc_text, change.name):
            missing_entries.append(change)
            continue
        doc_default = extract_doc_default(doc_text, change.name)
        if doc_default is None:
            continue
        expected = normalize_default(change.new)
        actual = normalize_default(doc_default)
        if expected != actual:
            stale_defaults.append((change.name, format_default(change.new), doc_default))

    for change in removed_changes:
        if has_variable_doc(doc_text, change.name):
            stale_removed.append(change)

    issues_found = bool(missing_entries or stale_defaults or stale_removed)

    lines = [
        COMMENT_MARKER,
        "## Config/Doc Sync Check",
        "",
        f"Compared `{CONFIG_PATH}` against `{DOC_PATH}` using base ref `{base_ref}`.",
        "",
    ]

    if not (added_changes or removed_changes or modified_changes):
        lines.extend(
            [
                "No changes detected in `ush/config_defaults.yaml` for this PR.",
                "",
            ]
        )
        return "\n".join(lines), False

    lines.extend(
        [
            "**Changed variables**",
            "",
            f"- Added: {', '.join(change.name for change in added_changes) or 'none'}",
            f"- Removed: {', '.join(change.name for change in removed_changes) or 'none'}",
            f"- Modified: {', '.join(change.name for change in modified_changes) or 'none'}",
            "",
        ]
    )

    if not issues_found:
        lines.extend(
            [
                "No documentation drift detected.",
                "",
            ]
        )
        return "\n".join(lines), False

    lines.append("### Documentation Issues")
    lines.append("")
    if missing_entries:
        lines.append("- Missing entries:")
        for change in missing_entries:
            lines.append(f"  - `{change.name}`")
        lines.append("")
    if stale_defaults:
        lines.append("- Stale defaults:")
        for name, expected, actual in stale_defaults:
            lines.append(f"  - `{name}`: docs show `{actual}`, config default is `{expected}`")
        lines.append("")
    if stale_removed:
        lines.append("- Removed variables still documented:")
        for change in stale_removed:
            lines.append(f"  - `{change.name}`")
        lines.append("")

    if missing_entries:
        lines.append("### Suggested RST Snippets")
        lines.append("")
        lines.append("```rst")
        for change in missing_entries:
            lines.append(build_snippet(change.name, change.new).rstrip())
            lines.append("")
        lines.append("```")
        lines.append("")

    return "\n".join(lines), True


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        required=True,
        help="Git ref to compare against, e.g. origin/develop",
    )
    parser.add_argument(
        "--report-file",
        help="Optional path to write the Markdown report to.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""

    args = parse_args()
    diff_text = get_diff_text(args.base_ref)
    added_changes, removed_changes, modified_changes = parse_changed_variables(diff_text)
    doc_text = load_doc_text()
    report, issues_found = render_report(
        added_changes=added_changes,
        removed_changes=removed_changes,
        modified_changes=modified_changes,
        doc_text=doc_text,
        base_ref=args.base_ref,
    )
    print(report)
    if args.report_file:
        Path(args.report_file).write_text(report, encoding="utf-8")
    return 1 if issues_found else 0


if __name__ == "__main__":
    sys.exit(main())
