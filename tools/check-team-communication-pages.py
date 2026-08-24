#!/usr/bin/env python3
"""Validate generated team-communication pages and their publication contract."""

from __future__ import annotations

import html
import json
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
REQUIRED_META_NAMES = {"description", "robots", "twitter:card", "twitter:title", "twitter:description"}
REQUIRED_META_PROPERTIES = {"og:type", "og:site_name", "og:title", "og:description", "og:url"}


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.text_by_id: dict[str, list[str]] = {}
        self.hrefs: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.h1_count = 0
        self.title_count = 0
        self.canonicals: list[str] = []
        self.json_ld: list[str] = []
        self.html_langs: list[str] = []
        self.meta_names: dict[str, list[str]] = {}
        self.meta_properties: dict[str, list[str]] = {}
        self._capture_json = False
        self._json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.errors.append(f"duplicate id #{element_id}")
            self.ids.add(element_id)
            self.text_by_id[element_id] = []
        if values.get("href") is not None:
            self.hrefs.append(values["href"] or "")
        if tag == "img":
            self.images.append(values)
        if tag == "h1":
            self.h1_count += 1
        if tag == "html" and values.get("lang"):
            self.html_langs.append(values["lang"] or "")
        if tag == "title":
            self.title_count += 1
        if tag == "link" and values.get("rel") == "canonical" and values.get("href"):
            self.canonicals.append(values["href"] or "")
        if tag == "meta" and values.get("name"):
            self.meta_names.setdefault(values["name"] or "", []).append(values.get("content") or "")
        if tag == "meta" and values.get("property"):
            self.meta_properties.setdefault(values["property"] or "", []).append(values.get("content") or "")
        if tag == "script" and values.get("type") == "application/ld+json":
            self._capture_json = True
            self._json_parts = []
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, element_id))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            self.errors.append(f"unexpected closing </{tag}>")
        elif self.stack[-1][0] != tag:
            self.errors.append(f"closing </{tag}> while <{self.stack[-1][0]}> is open")
            if any(open_tag == tag for open_tag, _ in self.stack):
                while self.stack and self.stack[-1][0] != tag:
                    self.stack.pop()
                if self.stack:
                    self.stack.pop()
        else:
            self.stack.pop()
        if tag == "script" and self._capture_json:
            self.json_ld.append("".join(self._json_parts))
            self._capture_json = False

    def handle_data(self, data: str) -> None:
        if self._capture_json:
            self._json_parts.append(data)
        if data.strip():
            for _, element_id in self.stack:
                if element_id:
                    self.text_by_id[element_id].append(data.strip())

    def close(self) -> None:
        super().close()
        if self.stack:
            self.errors.append("unclosed elements: " + ", ".join(tag for tag, _ in self.stack))


def parse_document(path: Path, cache: dict[Path, DocumentParser]) -> DocumentParser:
    resolved = path.resolve()
    if resolved not in cache:
        parser = DocumentParser()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        cache[resolved] = parser
    return cache[resolved]


def target_file(page_path: Path, href: str) -> tuple[Path, str] | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith(("mailto:", "tel:")):
        return None
    fragment = unquote(parsed.fragment)
    if not parsed.path:
        return page_path, fragment
    raw_target = (page_path.parent / unquote(parsed.path)).resolve()
    try:
        raw_target.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"link escapes the site root: {href}") from exc
    if raw_target.is_dir() or parsed.path.endswith("/"):
        raw_target = raw_target / "index.html"
    return raw_target, fragment


def check_document(path: Path, expected_canonical: str, cache: dict[Path, DocumentParser]) -> list[str]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    if re.search(r"{{[A-Z0-9_]+}}", source):
        errors.append("contains an unresolved template marker")
    if "Lorem ipsum" in source or "TODO" in source:
        errors.append("contains placeholder copy")
    parser = parse_document(path, cache)
    errors.extend(parser.errors)
    if parser.h1_count != 1:
        errors.append(f"expected one h1, found {parser.h1_count}")
    if parser.title_count != 1:
        errors.append(f"expected one title, found {parser.title_count}")
    if parser.canonicals != [expected_canonical]:
        errors.append(f"canonical mismatch: {parser.canonicals}")
    if parser.html_langs != ["en-US"]:
        errors.append(f"expected html lang=en-US, found {parser.html_langs}")
    for name in REQUIRED_META_NAMES:
        if len(parser.meta_names.get(name, [])) != 1 or not parser.meta_names[name][0]:
            errors.append(f"expected one non-empty meta name={name!r}")
    for prop in REQUIRED_META_PROPERTIES:
        if len(parser.meta_properties.get(prop, [])) != 1 or not parser.meta_properties[prop][0]:
            errors.append(f"expected one non-empty meta property={prop!r}")
    for image in parser.images:
        if image.get("alt") is None:
            errors.append(f"image is missing alt text: {image.get('src', '')}")
    for payload in parser.json_ld:
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON-LD: {exc}")
    if not parser.json_ld:
        errors.append("missing JSON-LD")
    for href in parser.hrefs:
        try:
            target = target_file(path, href)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if target is None:
            continue
        target_path, fragment = target
        if not target_path.is_file():
            errors.append(f"broken local link {href!r} -> {target_path}")
        elif fragment and fragment not in parse_document(target_path, cache).ids:
            errors.append(f"missing fragment for {href!r}: #{fragment}")
    return errors


def find_type(graph: list[object], expected: str) -> dict[str, object] | None:
    for node in graph:
        if not isinstance(node, dict):
            continue
        types = node.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if expected in types:
            return node
    return None


def main() -> int:
    manifest = json.loads((ROOT / "team-communication-pages.json").read_text(encoding="utf-8"))
    pages = manifest["pages"]
    expected_slugs = {page["slug"] for page in pages}
    actual_slugs = {path.parent.name for path in (ROOT / "communication").glob("*/index.html")}
    errors: list[str] = []
    if actual_slugs != expected_slugs:
        errors.append(f"published directories differ from manifest: expected {sorted(expected_slugs)}, found {sorted(actual_slugs)}")

    cache: dict[Path, DocumentParser] = {}
    hub = ROOT / "communication" / "index.html"
    for error in check_document(hub, "https://bedsideenglish.github.io/communication/", cache):
        errors.append(f"communication/index.html: {error}")
    hub_parser = cache[hub.resolve()]
    hub_source = hub.read_text(encoding="utf-8")
    ordered_pages = sorted(pages, key=lambda item: item["library_order"])
    card_positions = [hub_source.find(f'href="{page["slug"]}/"') for page in ordered_pages]
    if any(position < 0 for position in card_positions) or card_positions != sorted(card_positions):
        errors.append("communication/index.html: guide cards do not follow manifest library_order")
    if hub_parser.meta_properties.get("og:image") != ["https://bedsideenglish.github.io/assets/social/team-communication-og.png"]:
        errors.append("communication/index.html: hub social image is missing or incorrect")
    if hub_parser.meta_names.get("twitter:image") != ["https://bedsideenglish.github.io/assets/social/team-communication-og.png"]:
        errors.append("communication/index.html: hub X social image is missing or incorrect")

    for page in pages:
        slug = page["slug"]
        path = ROOT / "communication" / slug / "index.html"
        canonical = f"https://bedsideenglish.github.io/communication/{slug}/"
        if not path.is_file():
            errors.append(f"missing generated document: {path}")
            continue
        for error in check_document(path, canonical, cache):
            errors.append(f"communication/{slug}/index.html: {error}")
        source = path.read_text(encoding="utf-8")
        parsed = cache[path.resolve()]
        title_match = re.search(r"<title>(.*?)</title>", source, re.DOTALL)
        if not title_match or html.unescape(title_match.group(1).strip()) != page["title"]:
            errors.append(f"communication/{slug}/index.html: title differs from manifest")
        expected_image = "https://bedsideenglish.github.io/assets/social/team-communication-og.png"
        expected_meta = {
            "description": page["meta_description"],
            "twitter:title": page["h1"],
            "twitter:description": page["meta_description"],
        }
        if page["framework"]["name"] == "SBAR":
            expected_meta.update({
                "twitter:image": expected_image,
                "twitter:image:alt": "A fictional chart flowing through the four SBAR steps into a spoken team handoff",
            })
        for name, expected in expected_meta.items():
            if parsed.meta_names.get(name) != [expected]:
                errors.append(f"communication/{slug}/index.html: meta {name!r} differs from visible source record")
        expected_properties = {
            "og:title": page["h1"],
            "og:description": page["meta_description"],
            "og:url": canonical,
        }
        if page["framework"]["name"] == "SBAR":
            expected_properties.update({
                "og:image": expected_image,
                "og:image:alt": "A fictional chart flowing through the four SBAR steps into a spoken team handoff",
                "og:image:width": "1731",
                "og:image:height": "909",
            })
        for prop, expected in expected_properties.items():
            if parsed.meta_properties.get(prop) != [expected]:
                errors.append(f"communication/{slug}/index.html: meta property {prop!r} differs from visible source record")
        if source.count('class="framework-step"') != len(page["steps"]):
            errors.append(f"communication/{slug}/index.html: visible framework steps differ from manifest")
        if source.count('class="language-contrast"') != len(page["steps"]):
            errors.append(f"communication/{slug}/index.html: wording comparisons differ from manifest steps")
        expected_visuals = 1 if page["framework"]["name"] == "SBAR" else 0
        if source.count('class="cta-visual"') != expected_visuals:
            errors.append(f"communication/{slug}/index.html: CTA visual does not match the framework-specific image rule")
        if page["framework"]["name"] != "SBAR":
            for image_key in ("twitter:image", "twitter:image:alt"):
                if image_key in parsed.meta_names:
                    errors.append(f"communication/{slug}/index.html: non-SBAR detail page must not inherit {image_key}")
            for image_key in ("og:image", "og:image:alt", "og:image:width", "og:image:height"):
                if image_key in parsed.meta_properties:
                    errors.append(f"communication/{slug}/index.html: non-SBAR detail page must not inherit {image_key}")
        must_count = sum(fact["priority"] == "must" for fact in page["facts"])
        if source.count('class="priority-dot"') != must_count:
            errors.append(f"communication/{slug}/index.html: must-say chart markers do not match manifest")
        quick_text = " ".join(parsed.text_by_id.get("quick-answer", []))
        if page["quick_answer"] not in html.unescape(quick_text):
            errors.append(f"communication/{slug}/index.html: direct answer differs from manifest")
        if "Fictional training scenario" not in source or "Educational use only" not in source:
            errors.append(f"communication/{slug}/index.html: safety boundary is missing")
        for external_source in page["sources"]:
            if external_source["url"] not in parsed.hrefs:
                errors.append(f"communication/{slug}/index.html: source link is missing: {external_source['url']}")
        if len(parsed.json_ld) != 1:
            errors.append(f"communication/{slug}/index.html: expected one JSON-LD graph")
        else:
            payload = json.loads(parsed.json_ld[0])
            graph = payload.get("@graph", []) if isinstance(payload, dict) else []
            article = find_type(graph, "Article")
            breadcrumb = find_type(graph, "BreadcrumbList")
            if not article or not breadcrumb:
                errors.append(f"communication/{slug}/index.html: JSON-LD requires Article and BreadcrumbList nodes")
            elif article.get("headline") != page["h1"] or article.get("dateModified") != page["reviewed_on"]:
                errors.append(f"communication/{slug}/index.html: JSON-LD headline or review date differs from visible content")
            elif set(article.get("citation", [])) != {item["url"] for item in page["sources"]}:
                errors.append(f"communication/{slug}/index.html: JSON-LD citations differ from visible sources")

    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    for slug in expected_slugs:
        url = f"https://bedsideenglish.github.io/communication/{slug}/"
        if sitemap.count(url) != 1:
            errors.append(f"sitemap must contain exactly one {url}")
    if sitemap.count("https://bedsideenglish.github.io/communication/") != len(expected_slugs) + 1:
        errors.append("sitemap communication URL count is inconsistent")

    social_image = ROOT / "assets" / "social" / "team-communication-og.png"
    if not social_image.is_file():
        errors.append("team communication social preview image is missing")
    else:
        header = social_image.read_bytes()[:24]
        if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append("team communication social preview must be a PNG")
        else:
            width, height = struct.unpack(">II", header[16:24])
            if (width, height) != (1731, 909):
                errors.append(f"social preview metadata expects 1731x909, found {width}x{height}")

    if errors:
        print("Team-communication validation failed:")
        for error in errors:
            print(f"  ERROR {error}")
        return 1
    print(f"Team-communication validation passed ({len(expected_slugs)} guide page(s) plus hub).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
