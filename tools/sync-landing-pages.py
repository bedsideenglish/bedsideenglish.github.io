#!/usr/bin/env python3
"""Keep the two Android landing-page routes identical where intended."""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android.html"
INDEX = ROOT / "index.html"

# android.html is the source. These are the only root-route-specific values.
ROOT_ROUTE_REPLACEMENTS = {
    'content="https://boyskier.github.io/bedside-english/android.html"': 'content="https://boyskier.github.io/bedside-english/"',
    'href="https://boyskier.github.io/bedside-english/android.html"': 'href="https://boyskier.github.io/bedside-english/"',
    'class="brand" href="android.html"': 'class="brand" href="./"',
}


def expected_index() -> str:
    content = ANDROID.read_text(encoding="utf-8")
    for source, replacement in ROOT_ROUTE_REPLACEMENTS.items():
        if source not in content:
            raise RuntimeError(f"Expected Android-page value not found: {source}")
        content = content.replace(source, replacement)
    return content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite index.html from android.html, preserving root-route values",
    )
    args = parser.parse_args()

    expected = expected_index()
    actual = INDEX.read_text(encoding="utf-8")

    if args.write:
        if actual != expected:
            INDEX.write_text(expected, encoding="utf-8", newline="\n")
            print("Updated index.html from android.html.")
        else:
            print("index.html is already synchronized.")
        return 0

    if actual == expected:
        print("index.html and android.html are synchronized.")
        return 0

    print("index.html is out of sync with android.html. Run:")
    print("  python tools/sync-landing-pages.py --write")
    print("\n".join(difflib.unified_diff(
        actual.splitlines(), expected.splitlines(),
        fromfile="index.html", tofile="expected index.html", lineterm="",
    )))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
