#!/usr/bin/env python3
"""Build the sitemap from generated, indexable static pages."""

from __future__ import annotations

import html
import re
from pathlib import Path


SITE_ORIGIN = "https://bedsideenglish.github.io"
FIXED_ROUTES = ("/", "/android.html", "/android-everyday.html", "/desktop/", "/privacy.html")
REVIEWED_RE = re.compile(r'data-reviewed-on="(\d{4}-\d{2}-\d{2})"')


def _generated_routes(site_root: Path, section: str) -> list[tuple[str, str | None]]:
    section_root = site_root / section
    if not (section_root / "index.html").is_file():
        return []
    routes: list[tuple[str, str | None]] = [(f"/{section}/", None)]
    for page in sorted(section_root.glob("*/index.html")):
        source = page.read_text(encoding="utf-8")
        match = REVIEWED_RE.search(source)
        routes.append((f"/{section}/{page.parent.name}/", match.group(1) if match else None))
    return routes


def build_sitemap(site_root: Path) -> str:
    routes: list[tuple[str, str | None]] = [(route, None) for route in FIXED_ROUTES]
    routes.extend(_generated_routes(site_root, "learning"))
    routes.extend(_generated_routes(site_root, "communication"))
    routes.extend(_generated_routes(site_root, "everyday-english"))
    rows = []
    for route, reviewed_on in routes:
        lastmod = f"<lastmod>{reviewed_on}</lastmod>" if reviewed_on else ""
        url = html.escape(f"{SITE_ORIGIN}{route}", quote=True)
        rows.append(f"  <url><loc>{url}</loc>{lastmod}</url>")
    body = "\n".join(rows)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )
