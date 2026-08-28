#!/usr/bin/env python3
"""Verify that every public HTML page contains the shared GA4 base tag once."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_ID = "G-FK1EXM7ZKH"
TAG_URL = f"https://www.googletagmanager.com/gtag/js?id={MEASUREMENT_ID}"
CONFIG_CALL = f"gtag('config', '{MEASUREMENT_ID}');"


# `out/` holds Instagram slide HTML, which is a render input for a PNG rather
# than a page anyone visits, so it carries no analytics tag.
NON_PUBLIC_DIRS = {"tools", "out"}


def public_html_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.html")
        if not NON_PUBLIC_DIRS & set(path.relative_to(ROOT).parts)
        and not path.name.startswith("google")
    )


def validate(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    label = path.relative_to(ROOT).as_posix()
    errors: list[str] = []
    if "<head" not in source.lower():
        return [f"{label}: missing <head>"]
    if source.count(TAG_URL) != 1:
        errors.append(f"{label}: expected one GA4 loader for {MEASUREMENT_ID}")
    if source.count(CONFIG_CALL) != 1:
        errors.append(f"{label}: expected one GA4 config call for {MEASUREMENT_ID}")
    return errors


def main() -> int:
    pages = public_html_files()
    errors = [error for page in pages for error in validate(page)]
    if errors:
        print("GA4 tracking check failed:")
        print("\n".join(f"  - {error}" for error in errors))
        return 1
    print(f"GA4 tracking is present exactly once on {len(pages)} public HTML pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
