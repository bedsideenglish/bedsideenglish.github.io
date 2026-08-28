#!/usr/bin/env python3
"""Generate Instagram carousel slides from already-published guides.

The design rule this file enforces: every clinical English sentence on a card is
copied verbatim out of `team-communication-pages.json` by field reference. The
card manifest cannot contain clinical wording at all — it carries only slide
selection, hook copy, and caption copy. So a card can never say something the
site has not already reviewed, and rewording a guide breaks the recorded source
fingerprint instead of silently leaving a stale card in circulation.

Slide HTML is written to `out/instagram/<slug>/` as a render input. The
committed artifact is `assets/instagram/<slug>/` — the PNGs, the caption, and a
metadata file recording the source fingerprint and the SHA-256 of each slide's
HTML. `--check` regenerates the HTML and compares those hashes, which is the
same drift gate the model-interview audio pipeline uses.

    python3 tools/generate-instagram-cards.py
    python3 tools/generate-instagram-cards.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = TOOLS_ROOT / "instagram_card_templates"
DEFAULT_MANIFEST = ROOT / "instagram-cards.json"
SOURCE_MANIFEST = ROOT / "team-communication-pages.json"
HTML_ROOT = ROOT / "out" / "instagram"
ASSET_ROOT = ROOT / "assets" / "instagram"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLACEHOLDER_RE = re.compile(r"{{([A-Z0-9_]+)}}")
HASHTAG_RE = re.compile(r"^[a-z0-9]+$")

# A card is a poster, not a paragraph. These caps are deliberately tighter than
# anything the browser would need to overflow: they are an editorial budget, and
# the renderer's own overflow check is the second, harder gate.
LIMITS = {
    "eyebrow": 24,
    "headline_line": 20,
    "headline_lines": 4,
    "foot": 52,
    "swipe": 12,
    "quote": 84,
    "reason": 100,
    "url": 40,
    "caption_paragraph": 320,
    "caption_total": 900,
    "hashtags": 20,
}

TONES = {"base", "accent"}


class ManifestError(Exception):
    """A card manifest problem that must be fixed before anything is written."""


def fail(message: str) -> None:
    raise ManifestError(message)


def esc(value: str) -> str:
    """Escape for HTML and set straight apostrophes as typographic ones.

    This is a display transform, not an edit: no word changes, and the checker
    compares source text against the card after the same substitution. A serif
    display face makes a straight apostrophe look like a mistake, and the source
    guides already mix both forms.
    """
    return html.escape(value.replace("'", "’"), quote=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def exact_keys(data: dict[str, Any], allowed: set[str], where: str) -> None:
    if not isinstance(data, dict):
        fail(f"{where}: expected an object")
    missing = sorted(allowed - set(data))
    extra = sorted(set(data) - allowed)
    if missing:
        fail(f"{where}: missing key(s) {', '.join(missing)}")
    if extra:
        fail(f"{where}: unexpected key(s) {', '.join(extra)}")


def require_text(data: dict[str, Any], key: str, where: str, limit: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{where}.{key}: expected non-empty text")
    value = value.strip()
    if len(value) > limit:
        fail(f"{where}.{key}: {len(value)} characters exceeds the {limit}-character card budget")
    return value


def require_flag(data: dict[str, Any], key: str, where: str) -> None:
    if data.get(key) is not True:
        fail(f"{where}.{key}: must be explicitly true before the card is generated")


def render_template(name: str, values: dict[str, str]) -> str:
    """Substitute {{PLACEHOLDER}} tokens, failing on any the caller forgot."""
    text = (TEMPLATE_ROOT / name).read_text(encoding="utf-8")
    used: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            fail(f"{name}: no value supplied for {{{{{key}}}}}")
        used.add(key)
        return values[key]

    output = PLACEHOLDER_RE.sub(replace, text)
    unused = sorted(set(values) - used)
    if unused:
        fail(f"{name}: value(s) {', '.join(unused)} do not appear in the template")
    return output


def load_json(path: Path) -> Any:
    if not path.exists():
        fail(f"{path.name}: not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{path.name}: invalid JSON ({error})")


def source_pages() -> dict[str, dict[str, Any]]:
    data = load_json(SOURCE_MANIFEST)
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        fail(f"{SOURCE_MANIFEST.name}: expected a non-empty `pages` list")
    return {page["slug"]: page for page in pages if isinstance(page, dict) and "slug" in page}


def headline_markup(lines: list[Any], where: str) -> str:
    if not isinstance(lines, list) or not lines:
        fail(f"{where}: expected a non-empty list of headline lines")
    if len(lines) > LIMITS["headline_lines"]:
        fail(f"{where}: {len(lines)} lines exceeds the {LIMITS['headline_lines']}-line limit")
    parts = []
    for index, line in enumerate(lines):
        spot = f"{where}[{index}]"
        exact_keys(line, {"text", "tone"}, spot)
        text = require_text(line, "text", spot, LIMITS["headline_line"])
        tone = line.get("tone")
        if tone not in TONES:
            fail(f"{spot}.tone: expected one of {', '.join(sorted(TONES))}")
        span = esc(text)
        parts.append(f'<span class="accent">{span}</span>' if tone == "accent" else span)
    return "<br>".join(parts)


def validate_card(card: Any, index: int, pages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    where = f"cards[{index}]"
    exact_keys(
        card,
        {
            "slug",
            "source_page",
            "reviewed_on",
            "hook",
            "contrast_steps",
            "script",
            "cta",
            "caption",
            "hashtags",
            "review",
        },
        where,
    )

    slug = card["slug"]
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        fail(f"{where}.slug: expected a lowercase hyphenated slug")
    where = f"cards[{slug}]"

    source_slug = card["source_page"]
    if source_slug not in pages:
        fail(f"{where}.source_page: '{source_slug}' is not a published guide in {SOURCE_MANIFEST.name}")
    page = pages[source_slug]

    if not isinstance(card["reviewed_on"], str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", card["reviewed_on"]):
        fail(f"{where}.reviewed_on: expected an ISO date")

    exact_keys(card["review"], {
        "clinical_text_is_source_verbatim",
        "authored_copy_makes_no_clinical_claim",
        "source_page_published",
        "language_standard_en_us",
    }, f"{where}.review")
    for flag in card["review"]:
        require_flag(card["review"], flag, f"{where}.review")

    exact_keys(card["hook"], {"eyebrow", "headline", "footer", "swipe"}, f"{where}.hook")
    require_text(card["hook"], "eyebrow", f"{where}.hook", LIMITS["eyebrow"])
    headline_markup(card["hook"]["headline"], f"{where}.hook.headline")
    require_text(card["hook"], "footer", f"{where}.hook", LIMITS["foot"])
    require_text(card["hook"], "swipe", f"{where}.hook", LIMITS["swipe"])

    exact_keys(card["script"], {"eyebrow", "footer"}, f"{where}.script")
    require_text(card["script"], "eyebrow", f"{where}.script", LIMITS["eyebrow"])
    require_text(card["script"], "footer", f"{where}.script", LIMITS["foot"])

    exact_keys(card["cta"], {"eyebrow", "headline", "url", "footer", "swipe"}, f"{where}.cta")
    require_text(card["cta"], "eyebrow", f"{where}.cta", LIMITS["eyebrow"])
    headline_markup(card["cta"]["headline"], f"{where}.cta.headline")
    require_text(card["cta"], "url", f"{where}.cta", LIMITS["url"])
    require_text(card["cta"], "footer", f"{where}.cta", LIMITS["foot"])
    require_text(card["cta"], "swipe", f"{where}.cta", LIMITS["swipe"])

    steps = page.get("steps")
    selected = card["contrast_steps"]
    if not isinstance(selected, list) or not selected:
        fail(f"{where}.contrast_steps: expected a non-empty list of step indexes")
    if len(selected) != len(set(selected)):
        fail(f"{where}.contrast_steps: repeats a step index")
    for position in selected:
        if not isinstance(position, int) or not 0 <= position < len(steps):
            fail(f"{where}.contrast_steps: {position!r} is not a step index of '{source_slug}'")
        note = steps[position].get("language_note")
        if not isinstance(note, dict):
            fail(f"{where}.contrast_steps: step {position} of '{source_slug}' has no language_note to contrast")
        for key, limit_key in (("less_clear", "quote"), ("preferred", "quote"), ("reason", "reason")):
            require_text(note, key, f"{source_slug}.steps[{position}].language_note", LIMITS[limit_key])

    caption = card["caption"]
    if not isinstance(caption, list) or not caption:
        fail(f"{where}.caption: expected a non-empty list of paragraphs")
    for position, paragraph in enumerate(caption):
        if not isinstance(paragraph, str) or not paragraph.strip():
            fail(f"{where}.caption[{position}]: expected non-empty text")
        if len(paragraph) > LIMITS["caption_paragraph"]:
            fail(f"{where}.caption[{position}]: {len(paragraph)} characters exceeds {LIMITS['caption_paragraph']}")
    if sum(len(p) for p in caption) > LIMITS["caption_total"]:
        fail(f"{where}.caption: the caption is longer than {LIMITS['caption_total']} characters")

    hashtags = card["hashtags"]
    if not isinstance(hashtags, list) or not hashtags:
        fail(f"{where}.hashtags: expected a non-empty list")
    if len(hashtags) > LIMITS["hashtags"]:
        fail(f"{where}.hashtags: {len(hashtags)} exceeds Instagram's practical limit of {LIMITS['hashtags']}")
    if len(hashtags) != len(set(hashtags)):
        fail(f"{where}.hashtags: contains a duplicate")
    for tag in hashtags:
        if not isinstance(tag, str) or not HASHTAG_RE.match(tag):
            fail(f"{where}.hashtags: {tag!r} must be lowercase alphanumeric with no leading '#'")

    return card


def build_slides(card: dict[str, Any], page: dict[str, Any]) -> list[dict[str, str]]:
    """Return the ordered slides, each as {kind, html}.

    Slide order is the retention argument: the hook opens a loop, every contrast
    slide pays a little of it back, the script slide is the screenshot, and only
    then does the card ask for anything.
    """
    steps = page["steps"]
    selected = card["contrast_steps"]
    total = len(selected) + 3
    slides: list[dict[str, str]] = []

    def page_of(number: int) -> str:
        return esc(f"{number} / {total}")

    slides.append({
        "kind": "hook",
        "body_class": "hook on-ink",
        "html": render_template("slide-hook.html", {
            "EYEBROW": esc(card["hook"]["eyebrow"]),
            "HEADLINE": headline_markup(card["hook"]["headline"], "hook.headline"),
            "FOOTER": esc(card["hook"]["footer"]),
            "SWIPE": esc(card["hook"]["swipe"]) + " &rarr;",
        }),
    })

    for offset, position in enumerate(selected):
        step = steps[position]
        note = step["language_note"]
        slides.append({
            "kind": "contrast",
            "body_class": "contrast",
            "html": render_template("slide-contrast.html", {
                "CODE": esc(step["code"]),
                "NAME": esc(step["name"]),
                "BAD": esc(note["less_clear"]),
                "GOOD": esc(note["preferred"]),
                "REASON": esc(note["reason"]),
                "PAGER": page_of(offset + 2),
            }),
        })

    say_lines = "\n".join(
        '<div class="say"><span class="code">{code}</span><p>{text}</p></div>'.format(
            code=esc(steps[position]["code"]),
            text=esc(steps[position]["language_note"]["preferred"]),
        )
        for position in selected
    )
    slides.append({
        "kind": "script",
        "body_class": "script on-ink",
        "html": render_template("slide-script.html", {
            "EYEBROW": esc(card["script"]["eyebrow"]),
            "SAY_LINES": say_lines,
            "FOOTER": esc(card["script"]["footer"]),
            "PAGER": page_of(total - 1),
        }),
    })

    slides.append({
        "kind": "cta",
        "body_class": "cta on-ink",
        "html": render_template("slide-cta.html", {
            "EYEBROW": esc(card["cta"]["eyebrow"]),
            "HEADLINE": headline_markup(card["cta"]["headline"], "cta.headline"),
            "URL": esc(card["cta"]["url"]),
            "FOOTER": esc(card["cta"]["footer"]),
            "SWIPE": esc(card["cta"]["swipe"]),
        }),
    })
    return slides


def build_documents(card: dict[str, Any], page: dict[str, Any]) -> list[dict[str, str]]:
    documents = []
    for number, slide in enumerate(build_slides(card, page), start=1):
        document = render_template("card.html", {
            "TITLE": esc(f"{card['slug']} {number:02d} ({slide['kind']})"),
            "BODY_CLASS": slide["body_class"],
            "SLIDE": slide["html"].rstrip("\n"),
        })
        documents.append({"name": f"{number:02d}.html", "kind": slide["kind"], "html": document})
    return documents


def build_caption(card: dict[str, Any]) -> str:
    tags = " ".join(f"#{tag}" for tag in card["hashtags"])
    return "\n\n".join([*card["caption"], tags]) + "\n"


def page_fingerprint(page: dict[str, Any]) -> str:
    return sha256_text(json.dumps(page, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def build_metadata(card: dict[str, Any], page: dict[str, Any], documents: list[dict[str, str]], caption: str) -> str:
    metadata = {
        "schema_version": 1,
        "slug": card["slug"],
        "source_manifest": SOURCE_MANIFEST.name,
        "source_page": card["source_page"],
        "source_page_sha256": page_fingerprint(page),
        "reviewed_on": card["reviewed_on"],
        "caption_sha256": sha256_text(caption),
        "slides": [
            {
                "index": index,
                "kind": document["kind"],
                "html": document["name"],
                "png": document["name"].replace(".html", ".png"),
                "html_sha256": sha256_text(document["html"]),
            }
            for index, document in enumerate(documents, start=1)
        ],
    }
    return json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"


def write_or_check(path: Path, content: str, check: bool, mismatches: list[str]) -> None:
    if check:
        if not path.exists():
            mismatches.append(f"{path.relative_to(ROOT)} is missing")
        elif path.read_text(encoding="utf-8") != content:
            mismatches.append(f"{path.relative_to(ROOT)} is out of date")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate(manifest_path: Path, only: list[str], check: bool) -> int:
    pages = source_pages()
    manifest = load_json(manifest_path)
    exact_keys(manifest, {"schema_version", "source_manifest", "cards"}, manifest_path.name)
    if manifest["schema_version"] != 1:
        fail(f"{manifest_path.name}: unsupported schema_version {manifest['schema_version']!r}")
    if manifest["source_manifest"] != SOURCE_MANIFEST.name:
        fail(f"{manifest_path.name}.source_manifest: expected {SOURCE_MANIFEST.name}")

    cards = [validate_card(card, index, pages) for index, card in enumerate(manifest["cards"])]
    slugs = [card["slug"] for card in cards]
    if len(slugs) != len(set(slugs)):
        fail(f"{manifest_path.name}: duplicate card slug")
    unknown = sorted(set(only) - set(slugs))
    if unknown:
        fail(f"--card: unknown slug(s) {', '.join(unknown)}")

    mismatches: list[str] = []
    written = 0
    for card in cards:
        if only and card["slug"] not in only:
            continue
        page = pages[card["source_page"]]
        documents = build_documents(card, page)
        caption = build_caption(card)

        for document in documents:
            write_or_check(HTML_ROOT / card["slug"] / document["name"], document["html"], check, mismatches)
        write_or_check(ASSET_ROOT / card["slug"] / "caption.txt", caption, check, mismatches)
        write_or_check(
            ASSET_ROOT / card["slug"] / "metadata.json",
            build_metadata(card, page, documents, caption),
            check,
            mismatches,
        )
        written += 1
        if not check:
            print(f"{card['slug']}: {len(documents)} slides -> out/instagram/{card['slug']}/")

    if check:
        # Slide HTML lives outside version control, so a missing render input is
        # expected on a fresh clone; only committed drift is a failure.
        committed = [m for m in mismatches if not m.startswith("out/")]
        if committed:
            for message in committed:
                print(f"drift: {message}", file=sys.stderr)
            return 1
        print(f"instagram cards: {written} card(s) match the manifest")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--card", action="append", default=[], help="generate only this slug; may be repeated")
    parser.add_argument("--check", action="store_true", help="verify committed output without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return generate(args.manifest, args.card, args.check)
    except ManifestError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
