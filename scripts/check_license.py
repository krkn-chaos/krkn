#!/usr/bin/env python3
"""
License header linter for krkn source files.

Checks that all non-test Python source files contain the Apache 2.0 license header.
Test files (in tests/ or named test_*.py) are excluded.

Usage:
    # Check only (exit 1 if any files are missing the header)
    python scripts/check_license.py

    # Auto-fix: prepend header to files that are missing it
    python scripts/check_license.py --fix

    # Check specific files (e.g. from pre-commit)
    python scripts/check_license.py path/to/file.py [...]
"""

import argparse
import sys
from pathlib import Path

LICENSE_HEADER = """\
# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License."""

# Check for the copyright line only — allows year/author variation
LICENSE_MARKER = "# Copyright 2025 The Krkn Authors"

REPO_ROOT = Path(__file__).parent.parent


def is_test_file(path: Path) -> bool:
    parts = path.parts
    return "tests" in parts or path.name.startswith("test_")


def collect_source_files() -> list[Path]:
    return [
        p
        for p in REPO_ROOT.rglob("*.py")
        if not is_test_file(p)
        and not any(part.startswith(".") or part in ("venv", "venv3111", "build", "dist", "__pycache__") for part in p.parts)
    ]


def has_license(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
        return LICENSE_MARKER in content
    except (OSError, UnicodeDecodeError):
        return True  # skip unreadable files silently


def add_license(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    # Preserve shebang on the first line if present
    if content.startswith("#!"):
        shebang, rest = content.split("\n", 1)
        path.write_text(f"{shebang}\n{LICENSE_HEADER}\n{rest}", encoding="utf-8")
    else:
        path.write_text(f"{LICENSE_HEADER}\n{content}", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check/add Apache 2.0 license headers")
    parser.add_argument("files", nargs="*", help="Files to check (defaults to all source files)")
    parser.add_argument("--fix", action="store_true", help="Prepend license header to files missing it")
    args = parser.parse_args()

    if args.files:
        paths = [Path(f) for f in args.files if not is_test_file(Path(f)) and f.endswith(".py")]
    else:
        paths = collect_source_files()

    missing = [p for p in paths if not has_license(p)]

    if not missing:
        print("All files have the license header.")
        return 0

    if args.fix:
        for p in missing:
            add_license(p)
            print(f"  fixed: {p.relative_to(REPO_ROOT)}")
        print(f"\nAdded license header to {len(missing)} file(s).")
        return 0

    print("Missing license header in the following files:")
    for p in missing:
        print(f"  {p.relative_to(REPO_ROOT)}")
    print(f"\nRun with --fix to add the header automatically.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
