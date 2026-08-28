#!/usr/bin/env python3
"""Render generated Instagram slide HTML to 1080x1350 PNGs.

Authoring-time only, like the model-interview audio generator: it needs a
headless browser, and it is never run by the published site. Run
`generate-instagram-cards.py` first — this script only rasterises what that one
wrote to `out/instagram/`.

Overflow is the failure this catches. The manifest's character budgets are a
guess about how much text fits; the browser knows. Any slide whose content
escapes the 1080x1350 frame or the safe padding is reported and not written, so
a too-long sentence can never reach a PNG.

    python3 tools/render-instagram-cards.py
    python3 tools/render-instagram-cards.py --card sbar-nursing-handoff
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_ROOT = ROOT / "out" / "instagram"
ASSET_ROOT = ROOT / "assets" / "instagram"

WIDTH = 1080
HEIGHT = 1350
CHROMIUM = Path("/opt/pw-browsers/chromium")

# Measured in the page: every laid-out box must sit inside the padded frame.
OVERFLOW_PROBE = """
() => {
  // Text must stay inside this inset on every side. It is a little tighter than
  // the card padding, so a line that only just fits still reads as deliberate.
  const SAFE = 70;
  const problems = [];
  const frame = { w: document.documentElement.clientWidth, h: document.documentElement.clientHeight };
  if (document.body.scrollWidth > frame.w) problems.push(`page scrolls to ${document.body.scrollWidth}px wide`);
  if (document.body.scrollHeight > frame.h) problems.push(`page scrolls to ${document.body.scrollHeight}px tall`);
  for (const el of document.body.querySelectorAll('h1, h2, p, q, span')) {
    if (!el.getClientRects().length) continue;
    if (!el.textContent.trim()) continue;
    const r = el.getBoundingClientRect();
    if (r.left < SAFE - 1 || r.right > frame.w - SAFE + 1 || r.top < SAFE - 1 || r.bottom > frame.h - SAFE + 1) {
      const name = el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ').join('.') : '');
      problems.push(`<${name}> "${el.textContent.trim().slice(0, 40)}" `
        + `escapes the safe area (${Math.round(r.left)},${Math.round(r.top)} to ${Math.round(r.right)},${Math.round(r.bottom)})`);
    }
  }
  return problems;
}
"""


def slugs_to_render(only: list[str]) -> list[Path]:
    if not HTML_ROOT.exists():
        print("error: out/instagram/ is empty — run tools/generate-instagram-cards.py first", file=sys.stderr)
        return []
    directories = sorted(d for d in HTML_ROOT.iterdir() if d.is_dir())
    if only:
        wanted = set(only)
        directories = [d for d in directories if d.name in wanted]
        missing = sorted(wanted - {d.name for d in directories})
        if missing:
            print(f"error: no generated slides for {', '.join(missing)}", file=sys.stderr)
            return []
    return directories


def render(only: list[str], strict: bool) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("error: playwright is not installed (pip install playwright)", file=sys.stderr)
        return 1
    if not CHROMIUM.exists():
        print(f"error: no chromium at {CHROMIUM}", file=sys.stderr)
        return 1

    directories = slugs_to_render(only)
    if not directories:
        return 1

    failures = 0
    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path=str(CHROMIUM))
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        for directory in directories:
            out_dir = ASSET_ROOT / directory.name
            out_dir.mkdir(parents=True, exist_ok=True)
            for source in sorted(directory.glob("*.html")):
                page.goto(source.as_uri())
                page.evaluate("() => document.fonts.ready")
                problems = page.evaluate(OVERFLOW_PROBE)
                target = out_dir / f"{source.stem}.png"
                if problems:
                    failures += 1
                    print(f"overflow: {directory.name}/{source.name}", file=sys.stderr)
                    for problem in problems:
                        print(f"  - {problem}", file=sys.stderr)
                    if strict:
                        continue
                page.screenshot(path=str(target))
                print(f"{directory.name}/{target.name}")
        browser.close()

    if failures:
        print(f"\n{failures} slide(s) overflow the card frame", file=sys.stderr)
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", action="append", default=[], help="render only this slug; may be repeated")
    parser.add_argument(
        "--write-overflowing",
        action="store_true",
        help="still write a PNG for an overflowing slide, for inspection",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return render(args.card, strict=not args.write_overflowing)


if __name__ == "__main__":
    raise SystemExit(main())
