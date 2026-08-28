#!/usr/bin/env python3
"""Generate Instagram carousel slides from already-published guides.

The rule this file enforces: every clinical English sentence on a card is copied
verbatim out of a published guide by field reference. The card manifest cannot
contain clinical wording at all — it carries slide selection, hook framing, and
caption copy. So a card can never say something the site has not already
reviewed, and rewording a guide breaks the recorded source fingerprint instead
of leaving a stale card in circulation.

Three libraries feed cards, and they differ in what makes their content hurt, so
each has an adapter that knows how to read it:

  team-communication  colleague to colleague; there is a wrong version, so slides
                      are marked contrasts and the hook quotes the wrong version.
  learning            doctor to patient; neither phrasing is wrong, so slides
                      carry the guide's own labels and the hook quotes the
                      clinical-term option.
  model-interview     a live encounter with no single wrong line, so slides are
                      the doctor's actual questions and the hook is a scene.
  case-presentation   chart to speech; the skill is what you leave out, so a
                      slide stamps one chart fact with the guide's verdict and
                      the hook is the fact nobody needs to hear.

The authoring standard, and the reasoning behind the hook, is in
`docs/instagram-card-system.md`.

Slide HTML is written to `out/instagram/<slug>/` as a render input. The
committed artifact is `assets/instagram/<slug>/` — the PNGs, the caption, and a
metadata file recording each source fingerprint and the SHA-256 of each slide's
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
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = TOOLS_ROOT / "instagram_card_templates"
DEFAULT_MANIFEST = ROOT / "instagram-cards.json"
HTML_ROOT = ROOT / "out" / "instagram"
ASSET_ROOT = ROOT / "assets" / "instagram"

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLACEHOLDER_RE = re.compile(r"{{([A-Z0-9_]+)}}")
HASHTAG_RE = re.compile(r"^[a-z0-9]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A card is a poster, not a paragraph. These caps are deliberately tighter than
# anything the browser would need to overflow: they are an editorial budget, and
# the renderer's own overflow check is the second, harder gate.
LIMITS = {
    "eyebrow": 26,
    "hero": 92,
    "consequence": 34,
    "headline_line": 20,
    "headline_lines": 4,
    "foot": 52,
    "swipe": 12,
    "label": 36,
    "quote": 92,
    "reason": 150,
    "reply": 140,
    "url": 40,
    "caption_paragraph": 320,
    "caption_total": 900,
    "hashtags": 20,
}

TONES = {"base", "accent"}
# Mirrored from tools/generate-case-presentation-pages.py, so a typo in a guide's
# verdict is caught here rather than printed onto a card.
DECISIONS = {"Lead", "Include", "Compress", "Omit"}
MAX_SLIDES = 10  # Instagram's carousel limit.


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


def exact_keys(data: Any, allowed: set[str], where: str) -> None:
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


def source_text(value: Any, where: str, limit: int) -> str:
    """Text taken from a guide. Over budget means pick a different item."""
    if not isinstance(value, str) or not value.strip():
        fail(f"{where}: the guide has no text here")
    value = value.strip()
    if len(value) > limit:
        fail(f"{where}: {len(value)} characters exceeds the {limit}-character card budget — select another item")
    return value


def load_json(path: Path) -> Any:
    if not path.exists():
        fail(f"{path.name}: not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{path.name}: invalid JSON ({error})")


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


# --------------------------------------------------------------------------
# Library adapters
#
# Each returns the same two shapes so the slide templates stay library-agnostic:
#
#   item  {badge, name, top_label, top_text, bottom_label, bottom_text, reason,
#          script_code, tone}  — one body slide. `badge` falls back to the slide
#          number and `script_code` to `badge`, so an adapter only sets what its
#          library actually has.
#   hero  the verbatim source text the hook is built on
# --------------------------------------------------------------------------


def team_communication_item(page: dict[str, Any], index: Any, where: str) -> dict[str, Any]:
    steps = page.get("steps") or []
    if not isinstance(index, int) or not 0 <= index < len(steps):
        fail(f"{where}: {index!r} is not a step index of '{page['slug']}'")
    step = steps[index]
    note = step.get("language_note")
    if not isinstance(note, dict):
        fail(f"{where}: step {index} of '{page['slug']}' has no language_note to contrast")
    return {
        "badge": source_text(step.get("code"), f"{where}.code", 4),
        "name": source_text(step.get("name"), f"{where}.name", LIMITS["label"]),
        "top_label": "&#10007;",
        "top_text": source_text(note.get("less_clear"), f"{where}.less_clear", LIMITS["quote"]),
        "bottom_label": "&#10003;",
        "bottom_text": source_text(note.get("preferred"), f"{where}.preferred", LIMITS["quote"]),
        "reason": source_text(note.get("reason"), f"{where}.reason", LIMITS["reason"]),
        "script_code": "",
        "tone": "error",
    }


def team_communication_hero(page: dict[str, Any], index: Any, where: str) -> str:
    return team_communication_item(page, index, where)["top_text"]


def learning_item(page: dict[str, Any], index: Any, where: str) -> dict[str, Any]:
    edits = page.get("question_edits") or []
    if not isinstance(index, int) or not 0 <= index < len(edits):
        fail(f"{where}: {index!r} is not a question_edits index of '{page['slug']}'")
    edit = edits[index]
    alternatives = edit.get("alternatives") or []
    if len(alternatives) < 2:
        fail(f"{where}: question_edits[{index}] of '{page['slug']}' has fewer than two labelled alternatives")
    first, second = alternatives[0], alternatives[1]
    return {
        # No cross here: the guide presents these as labelled options, not as an
        # error and a correction, and marking one wrong would misstate the source.
        "badge": "",
        "name": source_text(edit.get("objective"), f"{where}.objective", LIMITS["label"]),
        "top_label": source_text(first.get("label"), f"{where}.alternatives[0].label", LIMITS["label"]),
        "top_text": source_text(first.get("phrase"), f"{where}.alternatives[0].phrase", LIMITS["quote"]),
        "bottom_label": source_text(second.get("label"), f"{where}.alternatives[1].label", LIMITS["label"]),
        "bottom_text": source_text(second.get("phrase"), f"{where}.alternatives[1].phrase", LIMITS["quote"]),
        "reason": source_text(edit.get("why_this_wording"), f"{where}.why_this_wording", LIMITS["reason"]),
        "script_code": "",
        "tone": "option",
    }


def learning_hero(page: dict[str, Any], index: Any, where: str) -> str:
    return learning_item(page, index, where)["top_text"]


def model_interview_item(page: dict[str, Any], index: Any, where: str) -> dict[str, Any]:
    """One doctor turn, labelled with the stage of the history it opens.

    `turn` and `flow` are both source data; pairing them is editorial selection,
    which is exactly what the manifest is for.
    """
    exact_keys(index, {"turn", "flow"}, where)
    turns = page.get("turns") or []
    flow = page.get("flow") or []
    turn_index, flow_index = index["turn"], index["flow"]
    if not isinstance(turn_index, int) or not 0 <= turn_index < len(turns):
        fail(f"{where}.turn: {turn_index!r} is not a turn index of '{page['slug']}'")
    if not isinstance(flow_index, int) or not 0 <= flow_index < len(flow):
        fail(f"{where}.flow: {flow_index!r} is not a flow index of '{page['slug']}'")
    turn = turns[turn_index]
    if turn.get("speaker") != "Doctor":
        fail(f"{where}.turn: turn {turn_index} of '{page['slug']}' is spoken by the patient, not the doctor")
    # The answer the question actually got is the point of a worked encounter, so
    # a selected turn must be one the patient replied to.
    if turn_index + 1 >= len(turns) or turns[turn_index + 1].get("speaker") == "Doctor":
        fail(f"{where}.turn: turn {turn_index} of '{page['slug']}' has no patient reply — select a turn that does")
    reply = turns[turn_index + 1]
    return {
        "badge": "",
        "name": source_text(flow[flow_index], f"{where}.flow", LIMITS["label"]),
        "top_label": source_text(page.get("voice", {}).get("patient_speaker"), f"{where}.patient_speaker", LIMITS["label"]),
        "top_text": source_text(reply.get("text"), f"{where}.reply", LIMITS["reply"]),
        "bottom_label": "",
        "bottom_text": source_text(turn.get("text"), f"{where}.turn", LIMITS["quote"]),
        "reason": "",
        "script_code": "",
        "tone": "ask",
    }


def model_interview_hero(page: dict[str, Any], index: Any, where: str) -> str:
    if index is not None:
        fail(f"{where}: a model-interview hook takes no index — its hero is the patient card")
    return source_text(page.get("patient_card"), f"{page['slug']}.patient_card", LIMITS["hero"])


def case_presentation_item(page: dict[str, Any], index: Any, where: str) -> dict[str, Any]:
    """One chart fact and the verdict the guide passed on it.

    An oral presentation is a compression problem, so the lesson is the verdict:
    lead with this fact, include it, compress it to a clause, or leave it out.
    Neither the fact nor the verdict is speech, so these slides carry no quote
    marks.
    """
    entries = page.get("compression") or []
    if not isinstance(index, int) or not 0 <= index < len(entries):
        fail(f"{where}: {index!r} is not a compression index of '{page['slug']}'")
    entry = entries[index]
    decision = source_text(entry.get("decision"), f"{where}.decision", 12)
    if decision not in DECISIONS:
        fail(f"{where}.decision: {decision!r} is not one of {', '.join(sorted(DECISIONS))}")
    return {
        "badge": "",
        "name": "",
        "top_label": "",
        "top_text": source_text(entry.get("source_detail"), f"{where}.source_detail", LIMITS["quote"]),
        "bottom_label": "",
        "bottom_text": decision,
        "reason": source_text(entry.get("why"), f"{where}.why", LIMITS["reason"]),
        "script_code": decision,
        "tone": "verdict",
    }


def case_presentation_hero(page: dict[str, Any], index: Any, where: str) -> str:
    return case_presentation_item(page, index, where)["top_text"]


LIBRARIES: dict[str, dict[str, Any]] = {
    "team-communication": {
        "manifest": "team-communication-pages.json",
        "item": team_communication_item,
        "hero": team_communication_hero,
        "hero_style": "quote",
    },
    "learning": {
        "manifest": "learning-pages.json",
        "item": learning_item,
        "hero": learning_hero,
        "hero_style": "quote",
    },
    "model-interview": {
        "manifest": "model-interview-pages.json",
        "item": model_interview_item,
        "hero": model_interview_hero,
        "hero_style": "scene",
    },
    "case-presentation": {
        "manifest": "case-presentation-pages.json",
        "item": case_presentation_item,
        "hero": case_presentation_hero,
        "hero_style": "fact",
    },
}


def library_pages(library: str) -> dict[str, dict[str, Any]]:
    name = LIBRARIES[library]["manifest"]
    data = load_json(ROOT / name)
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        fail(f"{name}: expected a non-empty `pages` list")
    return {page["slug"]: page for page in pages if isinstance(page, dict) and "slug" in page}


def resolve_page(pages: dict[str, dict[str, Any]], library: str, slug: Any, where: str) -> dict[str, Any]:
    if slug not in pages:
        fail(f"{where}: '{slug}' is not a published guide in {LIBRARIES[library]['manifest']}")
    return pages[slug]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def headline_markup(lines: Any, where: str) -> str:
    if not isinstance(lines, list) or not lines:
        fail(f"{where}: expected a non-empty list of headline lines")
    if len(lines) > LIMITS["headline_lines"]:
        fail(f"{where}: {len(lines)} lines exceeds the {LIMITS['headline_lines']}-line limit")
    parts = []
    for index, line in enumerate(lines):
        spot = f"{where}[{index}]"
        exact_keys(line, {"text", "tone"}, spot)
        text = require_text(line, "text", spot, LIMITS["headline_line"])
        if line.get("tone") not in TONES:
            fail(f"{spot}.tone: expected one of {', '.join(sorted(TONES))}")
        span = esc(text)
        parts.append(f'<span class="accent">{span}</span>' if line["tone"] == "accent" else span)
    return "<br>".join(parts)


def validate_card(card: Any, index: int, pages_by_library: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    where = f"cards[{index}]"
    exact_keys(
        card,
        {"slug", "library", "hook", "items", "script", "cta", "caption", "hashtags", "reviewed_on", "review"},
        where,
    )

    slug = card["slug"]
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        fail(f"{where}.slug: expected a lowercase hyphenated slug")
    where = f"cards[{slug}]"

    library = card["library"]
    if library not in LIBRARIES:
        fail(f"{where}.library: expected one of {', '.join(sorted(LIBRARIES))}")
    pages = pages_by_library[library]

    if not isinstance(card["reviewed_on"], str) or not DATE_RE.match(card["reviewed_on"]):
        fail(f"{where}.reviewed_on: expected an ISO date")

    exact_keys(card["review"], {
        "clinical_text_is_source_verbatim",
        "authored_copy_makes_no_clinical_claim",
        "source_pages_published",
        "language_standard_en_us",
    }, f"{where}.review")
    for flag, value in card["review"].items():
        if value is not True:
            fail(f"{where}.review.{flag}: must be explicitly true before the card is generated")

    # Hook. Its hero is source text, so the first slide sits inside the same
    # editorial gate as the rest of the carousel.
    hook = card["hook"]
    exact_keys(hook, {"eyebrow", "source", "consequence", "footer", "swipe"}, f"{where}.hook")
    require_text(hook, "eyebrow", f"{where}.hook", LIMITS["eyebrow"])
    require_text(hook, "consequence", f"{where}.hook", LIMITS["consequence"])
    require_text(hook, "footer", f"{where}.hook", LIMITS["foot"])
    require_text(hook, "swipe", f"{where}.hook", LIMITS["swipe"])
    exact_keys(hook["source"], {"page", "index"}, f"{where}.hook.source")
    hook_page = resolve_page(pages, library, hook["source"]["page"], f"{where}.hook.source.page")
    LIBRARIES[library]["hero"](hook_page, hook["source"]["index"], f"{where}.hook.source")

    # Body items.
    items = card["items"]
    if not isinstance(items, list) or not items:
        fail(f"{where}.items: expected a non-empty list")
    total = len(items) + 3
    if total > MAX_SLIDES:
        fail(f"{where}.items: {len(items)} items make {total} slides, over Instagram's limit of {MAX_SLIDES}")
    seen = set()
    for position, item in enumerate(items):
        spot = f"{where}.items[{position}]"
        exact_keys(item, {"page", "index"}, spot)
        key = (item["page"], json.dumps(item["index"], sort_keys=True))
        if key in seen:
            fail(f"{spot}: repeats an earlier item")
        seen.add(key)
        page = resolve_page(pages, library, item["page"], f"{spot}.page")
        LIBRARIES[library]["item"](page, item["index"], spot)

    exact_keys(card["script"], {"eyebrow", "footer"}, f"{where}.script")
    require_text(card["script"], "eyebrow", f"{where}.script", LIMITS["eyebrow"])
    require_text(card["script"], "footer", f"{where}.script", LIMITS["foot"])

    exact_keys(card["cta"], {"eyebrow", "headline", "url", "footer", "swipe"}, f"{where}.cta")
    require_text(card["cta"], "eyebrow", f"{where}.cta", LIMITS["eyebrow"])
    headline_markup(card["cta"]["headline"], f"{where}.cta.headline")
    require_text(card["cta"], "url", f"{where}.cta", LIMITS["url"])
    require_text(card["cta"], "footer", f"{where}.cta", LIMITS["foot"])
    require_text(card["cta"], "swipe", f"{where}.cta", LIMITS["swipe"])

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


# --------------------------------------------------------------------------
# Slides
# --------------------------------------------------------------------------


def card_items(card: dict[str, Any], pages: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    adapter: Callable[..., dict[str, Any]] = LIBRARIES[card["library"]]["item"]
    return [
        adapter(pages[item["page"]], item["index"], f"{card['slug']}.items[{position}]")
        for position, item in enumerate(card["items"])
    ]


def build_slides(card: dict[str, Any], pages: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Return the ordered slides, each as {kind, body_class, html}.

    Slide order is the retention argument: the hook opens a loop on one specific
    sentence, every body slide pays a little of it back, the script slide is the
    screenshot, and only then does the card ask for anything.
    """
    library = LIBRARIES[card["library"]]
    items = card_items(card, pages)
    total = len(items) + 3
    slides: list[dict[str, str]] = []

    def pager(number: int) -> str:
        return esc(f"{number} / {total}")

    hook = card["hook"]
    hero = library["hero"](pages[hook["source"]["page"]], hook["source"]["index"], "hook")
    style = library["hero_style"]
    slides.append({
        "kind": "hook",
        "body_class": f"hook on-ink hero-{style}",
        "html": render_template("slide-hook.html", {
            "EYEBROW": esc(hook["eyebrow"]),
            # Only a quoted hero is something somebody said; a scene or a chart
            # fact takes no quote marks.
            "HERO_TAG": "q" if style == "quote" else "p",
            "HERO": esc(hero),
            "CONSEQUENCE": esc(hook["consequence"]),
            "FOOTER": esc(hook["footer"]),
            "SWIPE": esc(hook["swipe"]) + " &rarr;",
        }),
    })

    for offset, item in enumerate(items):
        number = offset + 2
        badge = item["badge"] or str(number - 1)
        if item["tone"] == "ask":
            slides.append({
                "kind": "ask",
                "body_class": "ask on-ink",
                "html": render_template("slide-ask.html", {
                    "BADGE": esc(badge),
                    "NAME": esc(item["name"]),
                    "TEXT": esc(item["bottom_text"]),
                    "REPLY_LABEL": esc(item["top_label"]),
                    "REPLY": esc(item["top_text"]),
                    "PAGER": pager(number),
                }),
            })
            continue
        slides.append({
            "kind": "contrast",
            "body_class": f"contrast tone-{item['tone']}",
            "html": render_template("slide-contrast.html", {
                "BADGE": esc(badge),
                "NAME": esc(item["name"]),
                # Marks arrive as entities from the adapter; source labels do not.
                "TOP_LABEL": item["top_label"] if item["tone"] == "error" else esc(item["top_label"]),
                "TOP_TEXT": esc(item["top_text"]),
                "BOTTOM_LABEL": item["bottom_label"] if item["tone"] == "error" else esc(item["bottom_label"]),
                "BOTTOM_TEXT": esc(item["bottom_text"]),
                "REASON": esc(item["reason"]),
                "PAGER": pager(number),
            }),
        })

    script_codes = [item["script_code"] or item["badge"] or str(position + 1)
                    for position, item in enumerate(items)]
    # A verdict reads as a word, not a letter, so widen the column for it.
    wide = any(len(code) > 3 for code in script_codes)
    say_lines = "\n".join(
        '<div class="say"><span class="code">{code}</span><p>{text}</p></div>'.format(
            code=esc(code),
            # On a verdict card the fact is the line and the verdict is the code.
            text=esc(item["top_text"] if item["tone"] == "verdict" else item["bottom_text"]),
        )
        for code, item in zip(script_codes, items)
    )
    slides.append({
        "kind": "script",
        "body_class": "script on-ink" + (" wide-codes" if wide else ""),
        "html": render_template("slide-script.html", {
            "EYEBROW": esc(card["script"]["eyebrow"]),
            "SAY_LINES": say_lines,
            "FOOTER": esc(card["script"]["footer"]),
            "PAGER": pager(total - 1),
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


def build_documents(card: dict[str, Any], pages: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    documents = []
    for number, slide in enumerate(build_slides(card, pages), start=1):
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


def referenced_pages(card: dict[str, Any]) -> list[str]:
    """Every guide this card cuts from, hook included — a card may compile several."""
    slugs = {card["hook"]["source"]["page"], *(item["page"] for item in card["items"])}
    return sorted(slugs)


def build_metadata(
    card: dict[str, Any],
    pages: dict[str, dict[str, Any]],
    documents: list[dict[str, str]],
    caption: str,
) -> str:
    metadata = {
        "schema_version": 2,
        "slug": card["slug"],
        "library": card["library"],
        "source_manifest": LIBRARIES[card["library"]]["manifest"],
        "source_pages": {slug: page_fingerprint(pages[slug]) for slug in referenced_pages(card)},
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
    manifest = load_json(manifest_path)
    exact_keys(manifest, {"schema_version", "cards"}, manifest_path.name)
    if manifest["schema_version"] != 2:
        fail(f"{manifest_path.name}: unsupported schema_version {manifest['schema_version']!r}")

    pages_by_library = {name: library_pages(name) for name in LIBRARIES}
    cards = [validate_card(card, index, pages_by_library) for index, card in enumerate(manifest["cards"])]
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
        pages = pages_by_library[card["library"]]
        documents = build_documents(card, pages)
        caption = build_caption(card)

        for document in documents:
            write_or_check(HTML_ROOT / card["slug"] / document["name"], document["html"], check, mismatches)
        write_or_check(ASSET_ROOT / card["slug"] / "caption.txt", caption, check, mismatches)
        write_or_check(
            ASSET_ROOT / card["slug"] / "metadata.json",
            build_metadata(card, pages, documents, caption),
            check,
            mismatches,
        )
        written += 1
        if not check:
            print(f"{card['slug']} ({card['library']}): {len(documents)} slides -> out/instagram/{card['slug']}/")

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
