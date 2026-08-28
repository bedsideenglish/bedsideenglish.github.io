#!/usr/bin/env python3
"""Publication QA for the generated Instagram cards.

Three questions, in order of how badly a wrong answer would hurt:

1. Is every clinical sentence on a card still exactly what the published guide
   says? This is the whole safety argument for the pipeline. It compares the
   card metadata's recorded source fingerprint against the live guide, then
   re-derives each slide and confirms the quoted text is source text.
2. Do the PNGs exist, at the right size, one per slide?
3. Does the authored copy — the hook, the caption — stay out of clinical
   claims? A card may promise better wording; it may not promise an outcome.

    python3 tools/check-instagram-cards.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent


def load_generator():
    """Import the hyphenated generator module by path."""
    path = TOOLS_ROOT / "generate-instagram-cards.py"
    spec = importlib.util.spec_from_file_location("generate_instagram_cards", path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging accident
        raise SystemExit(f"error: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_generator()

MANIFEST = ROOT / "instagram-cards.json"
ASSET_ROOT = ROOT / "assets" / "instagram"
EXPECTED_SIZE = (1080, 1350)

# The site's own guides forbid these in editorial copy; the cards inherit the
# rule, because a card is the most quotable thing the project publishes.
OVERCLAIM_RULES = (
    (re.compile(r"\bguarantee(s|d)?\b", re.IGNORECASE), "do not guarantee an outcome"),
    (re.compile(r"\bsave(s)? lives\b", re.IGNORECASE), "do not claim a clinical outcome"),
    (re.compile(r"\b(cure|diagnose|treat)s?\b", re.IGNORECASE), "the cards teach wording, not clinical management"),
    (re.compile(r"\bnever fail(s)?\b", re.IGNORECASE), "do not promise infallibility"),
    (re.compile(r"\b(always|every time) works?\b", re.IGNORECASE), "do not promise infallibility"),
)

BRITISH_RULES = (
    (re.compile(r"\bpractis(e|ed|ing)\b", re.IGNORECASE), "use US `practice`"),
    (re.compile(r"\b(organis|recognis|prioritis)\w*\b", re.IGNORECASE), "use US spelling"),
    (re.compile(r"\bwhilst\b", re.IGNORECASE), "use US `while`"),
)


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def authored_strings(card: dict[str, Any]) -> list[tuple[str, str]]:
    """Every string a human or a model wrote, as opposed to quoted from a guide."""
    found = [
        (f"{card['slug']}.hook.eyebrow", card["hook"]["eyebrow"]),
        (f"{card['slug']}.hook.footer", card["hook"]["footer"]),
        (f"{card['slug']}.script.eyebrow", card["script"]["eyebrow"]),
        (f"{card['slug']}.script.footer", card["script"]["footer"]),
        (f"{card['slug']}.cta.eyebrow", card["cta"]["eyebrow"]),
        (f"{card['slug']}.cta.footer", card["cta"]["footer"]),
    ]
    for index, line in enumerate(card["hook"]["headline"]):
        found.append((f"{card['slug']}.hook.headline[{index}]", line["text"]))
    for index, line in enumerate(card["cta"]["headline"]):
        found.append((f"{card['slug']}.cta.headline[{index}]", line["text"]))
    for index, paragraph in enumerate(card["caption"]):
        found.append((f"{card['slug']}.caption[{index}]", paragraph))
    return found


def check_card(card: dict[str, Any], page: dict[str, Any], problems: list[str]) -> None:
    slug = card["slug"]
    asset_dir = ASSET_ROOT / slug
    metadata_path = asset_dir / "metadata.json"

    if not metadata_path.exists():
        problems.append(f"{slug}: assets/instagram/{slug}/metadata.json is missing — run the generator")
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    live = generator.page_fingerprint(page)
    if metadata.get("source_page_sha256") != live:
        problems.append(
            f"{slug}: '{card['source_page']}' changed since the cards were built "
            "— regenerate and re-render before posting"
        )

    documents = generator.build_documents(card, page)
    if len(documents) != len(metadata.get("slides", [])):
        problems.append(f"{slug}: metadata records {len(metadata.get('slides', []))} slides, the manifest builds {len(documents)}")
        return

    for document, record in zip(documents, metadata["slides"]):
        if generator.sha256_text(document["html"]) != record.get("html_sha256"):
            problems.append(f"{slug}/{document['name']}: slide content no longer matches the recorded hash")
        png = asset_dir / record["png"]
        if not png.exists():
            problems.append(f"{slug}/{record['png']}: not rendered — run tools/render-instagram-cards.py")
            continue
        try:
            size = png_size(png)
        except ValueError as error:
            problems.append(f"{slug}/{record['png']}: {error}")
            continue
        if size != EXPECTED_SIZE:
            problems.append(f"{slug}/{record['png']}: is {size[0]}x{size[1]}, expected {EXPECTED_SIZE[0]}x{EXPECTED_SIZE[1]}")

    # Source fidelity: each quoted sentence must appear verbatim in the guide.
    quoted = []
    for position in card["contrast_steps"]:
        note = page["steps"][position]["language_note"]
        quoted.extend([note["less_clear"], note["preferred"], note["reason"]])
    slide_html = "\n".join(document["html"] for document in documents)
    for sentence in quoted:
        if generator.esc(sentence) not in slide_html:
            problems.append(f"{slug}: card text drifted from the guide — {sentence!r} is not on any slide")

    caption = generator.build_caption(card)
    for where, text in [*authored_strings(card), (f"{slug}.caption", caption)]:
        for pattern, reason in OVERCLAIM_RULES:
            if pattern.search(text):
                problems.append(f"{where}: {reason}")
        for pattern, reason in BRITISH_RULES:
            if pattern.search(text):
                problems.append(f"{where}: {reason}")


def main() -> int:
    problems: list[str] = []
    try:
        pages = generator.source_pages()
        manifest = generator.load_json(MANIFEST)
        cards = [
            generator.validate_card(card, index, pages)
            for index, card in enumerate(manifest["cards"])
        ]
    except generator.ManifestError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    for card in cards:
        check_card(card, pages[card["source_page"]], problems)

    if problems:
        for problem in problems:
            print(f"fail: {problem}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1

    slides = sum(len(card["contrast_steps"]) + 3 for card in cards)
    print(f"instagram cards: {len(cards)} card(s), {slides} slides, all source-checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
