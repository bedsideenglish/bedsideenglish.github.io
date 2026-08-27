#!/usr/bin/env python3
"""Validate generated model-interview HTML, static WAV audio, and source sync."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys


TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from model_interview_content import (  # noqa: E402
    DEFAULT_AUDIO_ROOT,
    DEFAULT_MANIFEST,
    DEFAULT_SOURCE_ROOT,
    SITE_ROOT,
    ContentError,
    load_audio_metadata,
    load_records,
)


class MarkupAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.links: list[str] = []
        self.scripts: list[dict[str, str | None]] = []
        self.audio_configs: list[str] = []
        self._audio_config_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.ids:
                self.duplicate_ids.add(element_id)
            self.ids.add(element_id)
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag == "script":
            self.scripts.append(values)
            if "data-audio-config" in values:
                self._audio_config_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._audio_config_depth:
            self._audio_config_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._audio_config_depth:
            self.audio_configs.append(data)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    args = parser.parse_args()
    errors: list[str] = []
    try:
        records = load_records(args.manifest, args.source_root)
        for record in records:
            item = record.item
            slug = item["slug"]
            page_path = SITE_ROOT / "model-interviews" / slug / "index.html"
            metadata = load_audio_metadata(record, args.audio_root)
            require(page_path.is_file(), f"missing page: {page_path}", errors)
            if not page_path.is_file():
                continue
            source = page_path.read_text(encoding="utf-8")
            parser_audit = MarkupAudit()
            parser_audit.feed(source)
            require(not parser_audit.duplicate_ids, f"{slug}: duplicate IDs {sorted(parser_audit.duplicate_ids)}", errors)
            require(source.count("G-FK1EXM7ZKH") >= 2, f"{slug}: GA4 tag is missing", errors)
            require(f'data-case-id="{record.case_id}"' in source, f"{slug}: case ID is stale", errors)
            require(f'data-source-sha256="{record.source_sha256}"' in source, f"{slug}: source hash is stale", errors)
            require(f'data-transcript-sha256="{record.transcript_sha256}"' in source, f"{slug}: transcript hash is stale", errors)
            require(f'data-audio-transcript-sha256="{record.transcript_sha256}"' in source, f"{slug}: audio transcript hash is stale", errors)
            require(source.count('class="turn ') == len(item["turns"]), f"{slug}: rendered turn count is wrong", errors)
            require(len(parser_audit.audio_configs) == 1, f"{slug}: expected one audio config", errors)
            if len(parser_audit.audio_configs) == 1:
                try:
                    config = json.loads(parser_audit.audio_configs[0])
                    require(config.get("transcript_sha256") == record.transcript_sha256, f"{slug}: player transcript hash is stale", errors)
                    require(len(config.get("segments", [])) == len(metadata["segments"]), f"{slug}: player segment count is stale", errors)
                except json.JSONDecodeError as error:
                    errors.append(f"{slug}: invalid player JSON: {error}")
            require("generativelanguage.googleapis.com" not in source, f"{slug}: public page must not call Gemini", errors)
            require("GEMINI_API_KEY" not in source, f"{slug}: public page exposes an API key name", errors)
            require(re.search(r'<link rel="canonical" href="https://bedsideenglish\.github\.io/model-interviews/[^/]+/">', source) is not None, f"{slug}: canonical URL missing", errors)

        index_path = SITE_ROOT / "model-interviews" / "index.html"
        require(index_path.is_file(), "model-interviews/index.html is missing", errors)
        if index_path.is_file():
            index_source = index_path.read_text(encoding="utf-8")
            for record in records:
                require(f'href="{record.item["slug"]}/"' in index_source, f"index: missing {record.item['slug']}", errors)
        sitemap = (SITE_ROOT / "sitemap.xml").read_text(encoding="utf-8")
        for record in records:
            require(f"https://bedsideenglish.github.io/model-interviews/{record.item['slug']}/" in sitemap, f"sitemap: missing {record.item['slug']}", errors)
    except ContentError as error:
        errors.append(str(error))
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("model interview pages: content, source hashes, transcript hashes, and WAV checksums verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
