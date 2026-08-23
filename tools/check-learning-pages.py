#!/usr/bin/env python3
"""Validate generated learning pages, local links, and publication boundaries."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = ROOT.parent / "Medvoicetrainer-android-app-version" / "data" / "cases"
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
EXCLUDED_FIELDS = {
    "patient_name", "age", "gender", "hpi_details", "ideas", "concerns", "expectations",
    "pmh", "medications", "social_hx", "clinical_knowledge", "doorknob_disclosure",
    "doorknob_probability", "reference_soap", "learning_objectives",
}
EXCLUDED_TEACHING_FIELDS = {"diagnosis", "one_liner", "differentials", "red_flags", "closing"}


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.h1_count = 0
        self.title_count = 0
        self.canonicals: list[str] = []
        self.json_ld: list[str] = []
        self._capture_json = False
        self._json_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.errors.append(f"duplicate id #{element_id}")
            self.ids.add(element_id)
        if values.get("href") is not None:
            self.hrefs.append(values["href"] or "")
        if tag == "h1":
            self.h1_count += 1
        if tag == "title":
            self.title_count += 1
        if tag == "link" and values.get("rel") == "canonical" and values.get("href"):
            self.canonicals.append(values["href"])
        if tag == "script" and values.get("type") == "application/ld+json":
            self._capture_json = True
            self._json_parts = []
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            self.errors.append(f"unexpected closing </{tag}>")
        elif self.stack[-1] != tag:
            self.errors.append(f"closing </{tag}> while <{self.stack[-1]}> is open")
            if tag in self.stack:
                while self.stack and self.stack[-1] != tag:
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

    def close(self) -> None:
        super().close()
        if self.stack:
            self.errors.append("unclosed elements: " + ", ".join(self.stack))


def strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if len(value.strip()) >= 12 else []
    if isinstance(value, list):
        return [item for child in value for item in strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in strings(child)]
    return []


def target_file(page_path: Path, href: str, site_root: Path) -> tuple[Path, str] | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith(("mailto:", "tel:")):
        return None
    fragment = unquote(parsed.fragment)
    if not parsed.path:
        return page_path, fragment
    raw_target = (page_path.parent / unquote(parsed.path)).resolve()
    try:
        raw_target.relative_to(site_root.resolve())
    except ValueError:
        raise ValueError(f"link escapes the site root: {href}")
    if raw_target.is_dir() or parsed.path.endswith("/"):
        raw_target = raw_target / "index.html"
    return raw_target, fragment


def parse_document(path: Path, cache: dict[Path, DocumentParser]) -> DocumentParser:
    resolved = path.resolve()
    if resolved not in cache:
        parser = DocumentParser()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        cache[resolved] = parser
    return cache[resolved]


def check_page(path: Path, site_root: Path, cache: dict[Path, DocumentParser]) -> list[str]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    if re.search(r"{{[A-Z0-9_]+}}", source):
        errors.append("contains an unresolved template marker")
    parser = parse_document(path, cache)
    errors.extend(parser.errors)
    if parser.h1_count != 1:
        errors.append(f"expected one h1, found {parser.h1_count}")
    if parser.title_count != 1:
        errors.append(f"expected one title, found {parser.title_count}")
    if len(parser.canonicals) != 1:
        errors.append(f"expected one canonical link, found {len(parser.canonicals)}")
    for payload in parser.json_ld:
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON-LD: {exc}")
    for href in parser.hrefs:
        try:
            target = target_file(path, href, site_root)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if target is None:
            continue
        target_path, fragment = target
        if not target_path.is_file():
            errors.append(f"broken local link {href!r} -> {target_path}")
            continue
        if fragment and fragment not in parse_document(target_path, cache).ids:
            errors.append(f"missing fragment for {href!r}: #{fragment}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "learning-pages.json").read_text(encoding="utf-8"))
    entries = manifest["pages"]
    expected_slugs = {entry["slug"] for entry in entries}
    actual_slugs = {path.parent.name for path in (ROOT / "learning").glob("*/index.html")}
    errors: list[str] = []
    if actual_slugs != expected_slugs:
        errors.append(f"published scenario directories differ from the manifest: expected {sorted(expected_slugs)}, found {sorted(actual_slugs)}")

    documents = [ROOT / "learning" / "index.html"] + [ROOT / "learning" / slug / "index.html" for slug in sorted(expected_slugs)]
    cache: dict[Path, DocumentParser] = {}
    for document in documents:
        if not document.is_file():
            errors.append(f"missing generated document: {document}")
            continue
        for error in check_page(document, ROOT, cache):
            errors.append(f"{document.relative_to(ROOT)}: {error}")

    source_root = args.source_root.resolve()
    for entry in entries:
        case_path = (source_root / entry["case"]).resolve()
        case = json.loads(case_path.read_text(encoding="utf-8"))
        forbidden: list[str] = []
        for field in EXCLUDED_FIELDS:
            forbidden.extend(strings(case.get(field)))
        teaching = case.get("teaching", {})
        for field in EXCLUDED_TEACHING_FIELDS:
            forbidden.extend(strings(teaching.get(field)))
        output_path = ROOT / "learning" / entry["slug"] / "index.html"
        output = html.unescape(output_path.read_text(encoding="utf-8"))
        leaked = sorted({value for value in forbidden if value and value in output})
        if leaked:
            preview = "; ".join(repr(value[:80]) for value in leaked[:3])
            errors.append(f"learning/{entry['slug']}/index.html: excluded source content found: {preview}")
        expected_hash = hashlib.sha256(case_path.read_bytes()).hexdigest()
        if f"source-sha256: {expected_hash}" not in output:
            errors.append(f"learning/{entry['slug']}/index.html: source hash is missing or stale")
        coaching_count = output.count('class="wording-coach"')
        if coaching_count < 2:
            errors.append(f"learning/{entry['slug']}/index.html: expected at least two wording-coaching blocks, found {coaching_count}")
        if "Learning level" in output or "educationalLevel" in output:
            errors.append(f"learning/{entry['slug']}/index.html: ambiguous case difficulty is exposed as a learning level")

    if errors:
        print("Learning-page validation failed:")
        for error in errors:
            print(f"  ERROR {error}")
        return 1
    print(f"Learning-page validation passed ({len(expected_slugs)} scenario pages, {len(documents)} HTML documents).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
