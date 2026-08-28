#!/usr/bin/env python3
"""Validate generated case-presentation pages, metadata, links, and provenance."""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT.parent / "Medvoicetrainer-android-app-version" / "data" / "cases"
ORIGIN = "https://bedsideenglish.github.io"
GA_URL = "https://www.googletagmanager.com/gtag/js?id=G-FK1EXM7ZKH"
GA_CONFIG = "gtag('config', 'G-FK1EXM7ZKH');"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.canonical: list[str] = []
        self.meta_names: dict[str, list[str]] = {}
        self.meta_properties: dict[str, list[str]] = {}
        self.json_ld: list[str] = []
        self._json_depth = 0
        self._json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")
        if tag == "link" and values.get("rel") == "canonical" and values.get("href"):
            self.canonical.append(values["href"] or "")
        if tag == "meta" and values.get("content"):
            if values.get("name"):
                self.meta_names.setdefault(values["name"] or "", []).append(values["content"] or "")
            if values.get("property"):
                self.meta_properties.setdefault(values["property"] or "", []).append(values["content"] or "")
        if tag == "script" and values.get("type") == "application/ld+json":
            self._json_depth = 1
            self._json_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_depth:
            self.json_ld.append("".join(self._json_parts))
            self._json_depth = 0

    def handle_data(self, data: str) -> None:
        if self._json_depth:
            self._json_parts.append(data)


def internal_target(page_path: Path, href: str) -> Path | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith(("mailto:", "tel:", "#")):
        return None
    target = (page_path.parent / parsed.path).resolve()
    if parsed.path.endswith("/") or not target.suffix:
        target /= "index.html"
    return target


def check_document(path: Path, canonical: str) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return ["file is missing"]
    source = path.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(source)
    if re.search(r"{{[A-Z0-9_]+}}", source):
        errors.append("contains unresolved template marker")
    if source.count(GA_URL) != 1 or source.count(GA_CONFIG) != 1:
        errors.append("GA4 base tag must appear exactly once")
    if parser.canonical != [canonical]:
        errors.append(f"canonical mismatch: {parser.canonical}")
    if parser.meta_names.get("description") is None:
        errors.append("meta description is missing")
    for href in parser.hrefs:
        parsed = urlsplit(href)
        if parsed.fragment and not parsed.path and parsed.fragment not in parser.ids:
            errors.append(f"missing local fragment: #{parsed.fragment}")
        target = internal_target(path, href)
        if target is not None and ROOT.resolve() in target.parents and not target.is_file():
            errors.append(f"broken internal link: {href}")
    if len(parser.json_ld) != 1:
        errors.append("expected exactly one JSON-LD block")
    else:
        try:
            json.loads(parser.json_ld[0])
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON-LD: {exc}")
    return errors


def graph_type(payload: object, expected: str) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    for node in payload.get("@graph", []):
        if not isinstance(node, dict):
            continue
        kinds = node.get("@type", [])
        if isinstance(kinds, str):
            kinds = [kinds]
        if expected in kinds:
            return node
    return None


def main() -> int:
    manifest = json.loads((ROOT / "case-presentation-pages.json").read_text(encoding="utf-8"))
    pages = manifest["pages"]
    expected_slugs = {page["slug"] for page in pages}
    actual_slugs = {path.parent.name for path in (ROOT / "case-presentations").glob("*/index.html")}
    errors: list[str] = []
    if actual_slugs != expected_slugs:
        errors.append(f"published directories differ from allowlist: expected {sorted(expected_slugs)}, found {sorted(actual_slugs)}")

    hub = ROOT / "case-presentations" / "index.html"
    for error in check_document(hub, f"{ORIGIN}/case-presentations/"):
        errors.append(f"case-presentations/index.html: {error}")
    hub_source = hub.read_text(encoding="utf-8") if hub.is_file() else ""
    ordered = sorted(pages, key=lambda page: page["library_order"])
    positions = [hub_source.find(f'href="{page["slug"]}/"') for page in ordered]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        errors.append("hub cards do not follow manifest library_order")

    for page in pages:
        slug = page["slug"]
        path = ROOT / "case-presentations" / slug / "index.html"
        canonical = f"{ORIGIN}/case-presentations/{slug}/"
        for error in check_document(path, canonical):
            errors.append(f"case-presentations/{slug}/index.html: {error}")
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(source)
        title = re.search(r"<title>(.*?)</title>", source, re.DOTALL)
        if not title or html.unescape(title.group(1).strip()) != page["title"]:
            errors.append(f"{slug}: title differs from manifest")
        expected_meta = {"description": page["meta_description"], "twitter:title": page["h1"], "twitter:description": page["meta_description"]}
        for name, expected in expected_meta.items():
            if parser.meta_names.get(name) != [expected]:
                errors.append(f"{slug}: meta {name} differs from manifest")
        expected_props = {"og:title": page["h1"], "og:description": page["meta_description"], "og:url": canonical}
        for name, expected in expected_props.items():
            if parser.meta_properties.get(name) != [expected]:
                errors.append(f"{slug}: property {name} differs from manifest")
        if source.count('class="presentation-step"') != 6:
            errors.append(f"{slug}: expected six visible presentation steps")
        if source.count('class="language-contrast"') != 6:
            errors.append(f"{slug}: expected six wording contrasts")
        if source.count('class="follow-ups"') != 1 or "Do not fill the blanks" not in source:
            errors.append(f"{slug}: original teaching or uncertainty section is missing")
        if "Fictional training case" not in source or "Educational use only" not in source:
            errors.append(f"{slug}: educational safety boundary is missing")
        source_path = SOURCE_ROOT / page["source"]["relative_path"]
        expected_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if f"source-case: {page['source']['case_id']}; source-sha256: {expected_hash}" not in source:
            errors.append(f"{slug}: source provenance hash is missing or stale")
        for citation in page["sources"]:
            if citation["url"] not in parser.hrefs:
                errors.append(f"{slug}: visible source link missing: {citation['url']}")
        if len(parser.json_ld) == 1:
            payload = json.loads(parser.json_ld[0])
            article = graph_type(payload, "Article")
            resource = graph_type(payload, "LearningResource")
            breadcrumb = graph_type(payload, "BreadcrumbList")
            if not article or not resource or not breadcrumb:
                errors.append(f"{slug}: JSON-LD requires Article, LearningResource, and BreadcrumbList")
            elif article.get("headline") != page["h1"] or article.get("dateModified") != page["reviewed_on"]:
                errors.append(f"{slug}: JSON-LD headline or review date differs")
            elif set(article.get("citation", [])) != {item["url"] for item in page["sources"]}:
                errors.append(f"{slug}: JSON-LD citations differ from visible sources")

    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    for route in [f"{ORIGIN}/case-presentations/", *[f"{ORIGIN}/case-presentations/{slug}/" for slug in expected_slugs]]:
        if sitemap.count(f"<loc>{route}</loc>") != 1:
            errors.append(f"sitemap must contain exactly one {route}")

    for landing in (ROOT / "index.html",):
        source = landing.read_text(encoding="utf-8")
        if source.count('href="case-presentations/"') != 2:
            errors.append(f"{landing.name}: expected resource-card and footer links to the case-presentation hub")

    if errors:
        print("Case-presentation validation failed:")
        for error in errors:
            print(f"  ERROR {error}")
        return 1
    print(f"Case-presentation validation passed ({len(pages)} guide pages plus hub).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
