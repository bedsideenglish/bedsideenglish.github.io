#!/usr/bin/env python3
"""Blocking output QA for generated everyday-English listening guides."""

from __future__ import annotations

import json
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE_ORIGIN = "https://bedsideenglish.github.io"
PLAY_URL = "https://play.google.com/store/apps/details?id=com.boyskier.bedsideenglish"
REQUIRED_IDS = {
    "main", "quick-answer", "quick-answer-steps", "listening-practice", "accent-profile", "voice-status", "play-clip",
    "repeat-clip", "slow-clip", "lab-status", "listening-answer-form", "commit-answer",
    "listening-result", "result-headline", "result-meta", "revealed-transcript", "try-again",
    "listening-lab-config", "response-ladder", "decision-guide", "common-mistakes", "transfer-practice", "faq", "related-guides",
}
TEMPLATE_MARKER_RE = re.compile(r"{{[A-Z0-9_]+}}")
PLACEHOLDER_COPY_RE = re.compile(r"\b(?:TODO|Lorem ipsum)\b")


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.ids: dict[str, dict[str, str | None]] = {}
        self.hrefs: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.h1_count = 0
        self.titles: list[str] = []
        self.canonicals: list[str] = []
        self.html_langs: list[str] = []
        self.meta_names: dict[str, list[str]] = {}
        self.meta_properties: dict[str, list[str]] = {}
        self.json_ld: list[str] = []
        self.configs: list[str] = []
        self.visible_text: list[str] = []
        self.errors: list[str] = []
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.errors.append(f"duplicate id #{element_id}")
            self.ids[element_id] = values
        if tag == "html" and values.get("lang"):
            self.html_langs.append(values["lang"] or "")
        if tag == "h1":
            self.h1_count += 1
        if tag == "a" and values.get("href") is not None:
            self.hrefs.append(values.get("href") or "")
        if tag == "img":
            self.images.append(values)
        if tag == "link" and values.get("rel") == "canonical" and values.get("href"):
            self.canonicals.append(values["href"] or "")
        if tag == "meta" and values.get("name"):
            self.meta_names.setdefault(values["name"] or "", []).append(values.get("content") or "")
        if tag == "meta" and values.get("property"):
            self.meta_properties.setdefault(values["property"] or "", []).append(values.get("content") or "")
        if tag == "script" and values.get("type") == "application/ld+json":
            self._capture = "json_ld"
            self._parts = []
        elif tag == "script" and values.get("id") == "listening-lab-config":
            self._capture = "config"
            self._parts = []
        self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture:
            payload = "".join(self._parts)
            if self._capture == "json_ld":
                self.json_ld.append(payload)
            else:
                self.configs.append(payload)
            self._capture = None
            self._parts = []
        if self.stack:
            if self.stack[-1] == tag:
                self.stack.pop()
            elif tag in self.stack:
                while self.stack and self.stack[-1] != tag:
                    self.stack.pop()
                if self.stack:
                    self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)
        elif self.stack and self.stack[-1] == "title":
            self.titles.append(data.strip())
        elif not any(tag in {"script", "style"} for tag in self.stack) and data.strip():
            self.visible_text.append(data.strip())


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def target_file(page: Path, href: str) -> Path | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith(("mailto:", "tel:")):
        return None
    raw = (page.parent / unquote(parsed.path or "")).resolve()
    try:
        raw.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"link escapes site root: {href}") from exc
    if raw.is_dir() or not parsed.path or parsed.path.endswith("/"):
        raw = raw / "index.html"
    return raw


def parse(path: Path) -> DocumentParser:
    parser = DocumentParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def check_common(path: Path, canonical: str) -> tuple[DocumentParser, list[str]]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    parser = parse(path)
    errors.extend(parser.errors)
    if TEMPLATE_MARKER_RE.search(source):
        errors.append("unresolved template marker")
    if PLACEHOLDER_COPY_RE.search(source):
        errors.append("placeholder copy")
    if "In review" in source or "Coming soon" in source:
        errors.append("unpublished review placeholder")
    if "Under Google Play review" in source or "Google Play 심사 중" in source:
        errors.append("stale Google Play review copy")
    if parser.html_langs != ["en-US"]:
        errors.append(f"expected html lang en-US, found {parser.html_langs}")
    if parser.h1_count != 1:
        errors.append(f"expected one h1, found {parser.h1_count}")
    if len(parser.titles) != 1 or not parser.titles[0]:
        errors.append("expected one non-empty title")
    if parser.canonicals != [canonical]:
        errors.append(f"canonical mismatch: {parser.canonicals}")
    for name in ("description", "robots", "twitter:card", "twitter:title", "twitter:description", "twitter:image", "twitter:image:alt"):
        if len(parser.meta_names.get(name, [])) != 1 or not parser.meta_names[name][0]:
            errors.append(f"missing or duplicate meta name={name}")
    for prop in ("og:type", "og:site_name", "og:title", "og:description", "og:url", "og:image", "og:image:alt", "og:image:width", "og:image:height"):
        if len(parser.meta_properties.get(prop, [])) != 1 or not parser.meta_properties[prop][0]:
            errors.append(f"missing or duplicate meta property={prop}")
    for payload in parser.json_ld:
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON-LD: {exc}")
    if len(parser.json_ld) != 1:
        errors.append(f"expected one JSON-LD script, found {len(parser.json_ld)}")
    for image in parser.images:
        if image.get("alt") is None:
            errors.append(f"image is missing alt text: {image.get('src', '')}")
        if image.get("width") is None or image.get("height") is None:
            errors.append(f"image is missing width/height: {image.get('src', '')}")
    if PLAY_URL not in parser.hrefs:
        errors.append("Google Play download link is missing")
    for href in parser.hrefs:
        try:
            target = target_file(path, href)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if target is not None and not target.is_file():
            errors.append(f"broken local link {href!r} -> {target}")
    return parser, errors


def main() -> int:
    manifest = json.loads((ROOT / "everyday-english-pages.json").read_text(encoding="utf-8"))
    source = json.loads((ROOT / "everyday-listening-drills.json").read_text(encoding="utf-8"))
    drills = {drill["id"]: drill for drill in source["drills"]}
    pages = manifest["pages"]
    expected_slugs = {page["slug"] for page in pages}
    actual_slugs = {path.parent.name for path in (ROOT / "everyday-english").glob("*/index.html")}
    errors: list[str] = []
    if actual_slugs != expected_slugs:
        errors.append(f"published directories differ from manifest: expected {sorted(expected_slugs)}, found {sorted(actual_slugs)}")

    image = ROOT / "assets" / "social" / "everyday-listening-og.png"
    if not image.is_file():
        errors.append("social image is missing")
    else:
        try:
            if png_size(image) != (1200, 630):
                errors.append(f"social image must be 1200x630, found {png_size(image)}")
        except ValueError as exc:
            errors.append(f"invalid social image: {exc}")

    hub = ROOT / "everyday-english" / "index.html"
    if not hub.is_file():
        errors.append("everyday-english/index.html is missing")
    else:
        _, hub_errors = check_common(hub, f"{SITE_ORIGIN}/everyday-english/")
        errors.extend(f"everyday-english/index.html: {error}" for error in hub_errors)

    for page in pages:
        slug = page["slug"]
        path = ROOT / "everyday-english" / slug / "index.html"
        if not path.is_file():
            errors.append(f"missing generated page: everyday-english/{slug}/index.html")
            continue
        parser, page_errors = check_common(path, f"{SITE_ORIGIN}/everyday-english/{slug}/")
        errors.extend(f"everyday-english/{slug}/index.html: {error}" for error in page_errors)
        missing_ids = REQUIRED_IDS - set(parser.ids)
        if missing_ids:
            errors.append(f"everyday-english/{slug}/index.html: missing interactive IDs: {', '.join(sorted(missing_ids))}")
        if len(parser.configs) != 1:
            errors.append(f"everyday-english/{slug}/index.html: expected one lab config")
            continue
        try:
            config = json.loads(parser.configs[0])
        except json.JSONDecodeError as exc:
            errors.append(f"everyday-english/{slug}/index.html: invalid lab config: {exc}")
            continue
        drill = drills[page["source_drill_id"]]
        if config.get("drill", {}).get("id") != drill["id"]:
            errors.append(f"everyday-english/{slug}/index.html: source drill id mismatch")
        if config.get("drill", {}).get("transcript") != drill["transcript"]:
            errors.append(f"everyday-english/{slug}/index.html: transcript differs from app source")
        if config.get("drill", {}).get("details") != [
            {"key": detail["key"], "label": detail["label"], "answers": detail["answers"]} for detail in drill["details"]
        ]:
            errors.append(f"everyday-english/{slug}/index.html: detail scoring contract differs from app source")
        profile_ids = [profile["id"] for profile in config.get("profiles", [])]
        if profile_ids != drill["accent_candidates"]:
            errors.append(f"everyday-english/{slug}/index.html: speaker profiles differ from app source")
        audio_sources = config.get("drill", {}).get("audio_sources")
        if not isinstance(audio_sources, dict):
            errors.append(f"everyday-english/{slug}/index.html: audio_sources must be an object")
        else:
            for profile_id, relative_path in audio_sources.items():
                if profile_id not in drill["accent_candidates"]:
                    errors.append(f"everyday-english/{slug}/index.html: audio source uses an unapproved profile {profile_id}")
                    continue
                target = (path.parent / relative_path).resolve()
                if not target.is_file():
                    errors.append(f"everyday-english/{slug}/index.html: reviewed audio is missing: {relative_path}")
        visible = " ".join(parser.visible_text)
        if page["quick_answer"] not in visible:
            errors.append(f"everyday-english/{slug}/index.html: quick answer is not visible static text")
        for step in page["quick_answer_steps"]:
            if step["phrase"] not in visible:
                errors.append(f"everyday-english/{slug}/index.html: quick-answer phrase is not visible static text")
        for link in page["related_links"]:
            if link["href"] not in parser.hrefs:
                errors.append(f"everyday-english/{slug}/index.html: related internal link is missing: {link['href']}")
            if link["label"] not in visible:
                errors.append(f"everyday-english/{slug}/index.html: related-link anchor text is not visible: {link['label']}")
        if drill["transcript"] in visible:
            errors.append(f"everyday-english/{slug}/index.html: practice transcript is visible before commit")
        if "hidden" not in parser.ids.get("listening-result", {}):
            errors.append(f"everyday-english/{slug}/index.html: result panel is not initially hidden")

    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8") if (ROOT / "sitemap.xml").is_file() else ""
    expected_routes = [f"{SITE_ORIGIN}/everyday-english/"] + [f"{SITE_ORIGIN}/everyday-english/{page['slug']}/" for page in pages]
    for route in expected_routes:
        if sitemap.count(f"<loc>{route}</loc>") != 1:
            errors.append(f"sitemap must contain exactly one {route}")

    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"Everyday English QA passed: {len(pages)} guide(s), hub, interaction contract, links, metadata, and sitemap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
