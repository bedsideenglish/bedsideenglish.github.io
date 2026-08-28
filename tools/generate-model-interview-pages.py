#!/usr/bin/env python3
"""Generate the ten audio-first model history-taking pages."""

from __future__ import annotations

import argparse
from datetime import date
import html
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
    PageRecord,
    load_audio_metadata,
    load_records,
)
from site_map import build_sitemap  # noqa: E402


TEMPLATE_ROOT = TOOLS_ROOT / "model_interview_templates"
OUTPUT_ROOT = SITE_ROOT / "model-interviews"
SITE_ORIGIN = "https://bedsideenglish.github.io"
PLACEHOLDER_RE = re.compile(r"{{([A-Z0-9_]+)}}")


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_template(path: Path, values: dict[str, str]) -> str:
    source = path.read_text(encoding="utf-8")
    missing = set(PLACEHOLDER_RE.findall(source)) - values.keys()
    if missing:
        raise ContentError(f"{path.name}: missing template values: {', '.join(sorted(missing))}")
    rendered = PLACEHOLDER_RE.sub(lambda match: values[match.group(1)], source)
    leftovers = PLACEHOLDER_RE.findall(rendered)
    if leftovers:
        raise ContentError(f"{path.name}: unresolved placeholders: {', '.join(sorted(set(leftovers)))}")
    return rendered.rstrip() + "\n"


def display_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return parsed.strftime("%B %d, %Y").replace(" 0", " ")


def render_transcript(record: PageRecord) -> str:
    rows = []
    for index, turn in enumerate(record.item["turns"]):
        css_speaker = turn["speaker"].lower()
        rows.append(
            f'<li class="turn {css_speaker}" data-turn="{index}">'
            f'<span class="speaker">{escaped(turn["speaker"])}</span>'
            f'<p>{escaped(turn["text"])}</p></li>'
        )
    return "\n            ".join(rows)


def render_list(values: list[str], tag: str = "li") -> str:
    return "\n".join(f"<{tag}>{escaped(value)}</{tag}>" for value in values)


def public_audio_config(record: PageRecord, metadata: dict[str, object]) -> dict[str, object]:
    segments = []
    for segment in metadata["segments"]:  # type: ignore[index]
        segments.append(
            {
                "file": f"../../assets/audio/model-interviews/{record.item['slug']}/{segment['file']}",
                "turn_start": segment["turn_start"],
                "turn_end": segment["turn_end"],
                "duration_seconds": segment["duration_seconds"],
            }
        )
    return {
        "transcript_sha256": record.transcript_sha256,
        "segments": segments,
        "prediction_pauses": record.item["prediction_pauses"],
    }


def render_page(record: PageRecord, audio_root: Path) -> str:
    item = record.item
    recall_turn = int(item["recall"]["patient_turn"])
    recall_answer = item["turns"][recall_turn]
    recall_follow_up = item["turns"][recall_turn + 1]
    metadata = load_audio_metadata(record, audio_root)
    duration = sum(float(segment["duration_seconds"]) for segment in metadata["segments"])
    minutes = int(duration // 60)
    seconds = int(round(duration % 60))
    duration_label = f"{minutes}:{seconds:02d}"
    canonical = f"{SITE_ORIGIN}/model-interviews/{item['slug']}/"
    sources = "\n".join(
        f'<li><a href="{escaped(source["url"])}" target="_blank" rel="noopener noreferrer">{escaped(source["title"])}</a></li>'
        for source in item["sources"]
    )
    structured = {
        "@context": "https://schema.org",
        "@type": "LearningResource",
        "name": item["h1"],
        "description": item["meta_description"],
        "url": canonical,
        "inLanguage": "en-US",
        "dateModified": item["reviewed_on"],
        "educationalUse": "Clinical communication practice",
        "isAccessibleForFree": True,
        "provider": {"@type": "Organization", "name": "Bedside English", "url": SITE_ORIGIN},
    }
    values = {
        "SOURCE_CASE": escaped(record.source_case),
        "SOURCE_SHA256": record.source_sha256,
        "TRANSCRIPT_SHA256": record.transcript_sha256,
        "AUDIO_TRANSCRIPT_SHA256": escaped(str(metadata["transcript_sha256"])),
        "PAGE_TITLE": escaped(f"{item['h1']} | Bedside English"),
        "META_DESCRIPTION": escaped(item["meta_description"]),
        "CANONICAL_URL": canonical,
        "H1": escaped(item["h1"]),
        "STRUCTURED_DATA": json.dumps(structured, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/"),
        "CASE_ID": escaped(record.case_id),
        "REVIEWED_ON": escaped(item["reviewed_on"]),
        "REVIEWED_ON_DISPLAY": escaped(display_date(item["reviewed_on"])),
        "SPECIALTY": escaped(item["specialty"]),
        "SETTING": escaped(item["setting"]),
        "PATIENT_CARD": escaped(item["patient_card"]),
        "ESTIMATED_MINUTES": escaped(item["estimated_minutes"]),
        "AUDIO_ROLE_LABEL": escaped(item["voice"]["patient_speaker"].lower()),
        "AUDIO_DURATION": duration_label,
        "PREDICTION_PAUSE_COUNT": str(len(item["prediction_pauses"])),
        "AUDIO_CONFIG": json.dumps(public_audio_config(record, metadata), ensure_ascii=False, separators=(",", ":")).replace("</", "<\/"),
        "RECALL_SPEAKER": escaped(recall_answer["speaker"]),
        "RECALL_ANSWER": escaped(recall_answer["text"]),
        "RECALL_CUE": escaped(item["recall"]["cue"]),
        "RECALL_FOLLOW_UP": escaped(recall_follow_up["text"]),
        "TRANSCRIPT": render_transcript(record),
        "FLOW": render_list(item["flow"]),
        "DO_NOT_MISS": render_list(item["do_not_miss"]),
        "SOURCES": sources,
    }
    return render_template(TEMPLATE_ROOT / "page.html", values)


def render_index(records: list[PageRecord]) -> str:
    cards = []
    for index, record in enumerate(records, start=1):
        item = record.item
        cards.append(
            f'<a class="interview-card" href="{escaped(item["slug"])}/">'
            f'<span class="card-top"><span>{escaped(item["specialty"])}</span><span>{escaped(item["estimated_minutes"])}</span></span>'
            f'<h3>{escaped(item["h1"])}</h3><p>{escaped(item["patient_card"])}</p>'
            f'<span class="card-link">Play model {index:02d} <span aria-hidden="true">→</span></span></a>'
        )
    return render_template(
        TEMPLATE_ROOT / "index.html",
        {"CARDS": "\n        ".join(cards), "HUB_JSONLD": build_hub_jsonld(records)},
    )


def build_hub_jsonld(records: list[PageRecord]) -> str:
    """CollectionPage + ItemList for the hub, matching the everyday-english hub.

    Order and titles come from the same records that render the cards, so the
    markup cannot drift away from what is visible on the page.
    """
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE_ORIGIN}/model-interviews/#collection",
                "url": f"{SITE_ORIGIN}/model-interviews/",
                "name": "Model Doctor-Patient Conversations in English",
                "description": (
                    "Complete doctor-patient history-taking conversations in clear "
                    "American English, with two-voice audio and clinical flow notes."
                ),
                "inLanguage": "en-US",
                "isPartOf": {"@type": "WebSite", "name": "Bedside English", "url": f"{SITE_ORIGIN}/"},
                "publisher": {"@id": f"{SITE_ORIGIN}/#organization"},
                "about": {"@type": "Thing", "name": "Doctor-patient conversation in English"},
                "audience": {
                    "@type": "EducationalAudience",
                    "educationalRole": (
                        "Medical students, international medical graduates, "
                        "and healthcare professionals"
                    ),
                },
            },
            {
                "@type": "ItemList",
                "@id": f"{SITE_ORIGIN}/model-interviews/#interviews",
                "numberOfItems": len(records),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": index,
                        "name": record.item["h1"],
                        "url": f"{SITE_ORIGIN}/model-interviews/{record.item['slug']}/",
                    }
                    for index, record in enumerate(records, start=1)
                ],
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{SITE_ORIGIN}/model-interviews/#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_ORIGIN}/"},
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Model interviews",
                        "item": f"{SITE_ORIGIN}/model-interviews/",
                    },
                ],
            },
        ],
    }
    return json.dumps(graph, ensure_ascii=False, separators=(",", ":"))


def write_or_check(path: Path, content: str, check: bool) -> bool:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            print(f"stale: {path.relative_to(SITE_ROOT)}")
            return False
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(SITE_ROOT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        records = load_records(args.manifest, args.source_root)
        expected_pages = {record.item["slug"] for record in records}
        existing_pages = {path.parent.name for path in OUTPUT_ROOT.glob("*/index.html")}
        unexpected = existing_pages - expected_pages
        if unexpected:
            raise ContentError(f"Unexpected generated model-interview directories: {', '.join(sorted(unexpected))}")
        ok = write_or_check(OUTPUT_ROOT / "index.html", render_index(records), args.check)
        for record in records:
            ok = write_or_check(OUTPUT_ROOT / record.item["slug"] / "index.html", render_page(record, args.audio_root), args.check) and ok
        ok = write_or_check(SITE_ROOT / "sitemap.xml", build_sitemap(SITE_ROOT), args.check) and ok
        return 0 if ok else 1
    except ContentError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
