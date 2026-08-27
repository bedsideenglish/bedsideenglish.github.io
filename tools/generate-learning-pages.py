#!/usr/bin/env python3
"""Generate reviewed clinical-English learning pages from selected case JSON.

The generator deliberately has no "all cases" mode. A page must be named in the
editorial manifest or passed explicitly with --case.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from site_map import build_sitemap  # noqa: E402


TEMPLATE_ROOT = TOOLS_ROOT / "learning_templates"
DEFAULT_SOURCE_ROOT = ROOT.parent / "Medvoicetrainer-android-app-version" / "data" / "cases"
DEFAULT_MANIFEST = ROOT / "learning-pages.json"
SITE_ORIGIN = "https://bedsideenglish.github.io"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLACEHOLDER_RE = re.compile(r"{{([A-Z0-9_]+)}}")
PAGE_META_RE = re.compile(
    r'<article class="learning-page" data-case-id="([^"]+)" '
    r'data-page-title="([^"]+)" data-summary="([^"]+)"[^>]*>'
)

GROUPS = (
    ("The symptom story", {"location", "radiation", "onset_duration", "character", "progression", "severity", "aggravating", "relieving"}),
    ("Associated symptoms", {"associated_symptoms"}),
    ("Health background", {"pmh", "medications", "allergies", "family_hx", "smoking", "alcohol", "drugs"}),
    ("The patient's perspective", {"ideas", "concerns", "expectations"}),
    ("Daily life and context", {"living_work", "diet", "travel", "sexual_hx"}),
)

US_STYLE_RULES = (
    (re.compile(r"\bpractis(?:e|ed|ing)\b", re.IGNORECASE), "use US `practice/practiced/practicing`"),
    (re.compile(r"\bdiarrhoea\b", re.IGNORECASE), "use US `diarrhea`"),
    (re.compile(r"\bhaemorrhage\b", re.IGNORECASE), "use US `hemorrhage`"),
    (re.compile(r"\boesophag\w*\b", re.IGNORECASE), "use US `esophag-` spelling"),
    (re.compile(r"\bpaediatric\w*\b", re.IGNORECASE), "use US `pediatric`"),
    (re.compile(r"\banaesth\w*\b", re.IGNORECASE), "use US `anesth-` spelling"),
    (re.compile(r"\b(?:colour|behaviour|favour)\w*\b", re.IGNORECASE), "use the corresponding US `-or` spelling"),
    (re.compile(r"\bcentre\b", re.IGNORECASE), "use US `center`"),
    (re.compile(r"\bmetres?\b", re.IGNORECASE), "use US `meter/meters`"),
    (re.compile(r"\blitres?\b", re.IGNORECASE), "use US `liter/liters`"),
    (re.compile(r"\b(?:recognise|organise|realise)(?:d|s|ing)?\b", re.IGNORECASE), "use the corresponding US `-ize` spelling"),
    (re.compile(r"\b(?:labelled|travelling|counselling)\b", re.IGNORECASE), "use US single-l spelling"),
    (re.compile(r"\b(?:melaena|oedema|foetus)\b", re.IGNORECASE), "use the corresponding US medical spelling"),
    (re.compile(r"\bwhilst\b", re.IGNORECASE), "use US `while`"),
    (re.compile(r"\bopen your bowels\b", re.IGNORECASE), "use `have a bowel movement` for US-facing patient language"),
    (re.compile(r"\bfelt sick\b", re.IGNORECASE), "use `felt nauseated` when nausea is intended"),
)

PRESUPPOSITION_RULES = (
    (re.compile(r"\beach time\b", re.IGNORECASE), "may assume the symptom is episodic"),
    (re.compile(r"\byou (?:mentioned|said)\b", re.IGNORECASE), "assumes a patient answer not present on the public page"),
    (re.compile(r"\bas (?:you|we) (?:discussed|said)\b", re.IGNORECASE), "assumes an earlier answer or discussion"),
    (re.compile(r"\bwhen it happens again\b", re.IGNORECASE), "assumes the symptom will recur"),
)


class GenerationError(RuntimeError):
    """A case cannot be safely converted to the supported public schema."""


@dataclass(frozen=True)
class PageSpec:
    source: Path
    slug: str
    h1: str
    meta_description: str
    lede: str = "Use clear, patient-friendly questions to explore this scenario, understand what each phrase clarifies, and then say it aloud."
    scenario: str = "A patient presents for a clinical history."
    quick_answer: str = "Start with an open question, then use the selected patient-friendly questions below to explore the symptom and the patient's concerns."
    reviewed_on: str = ""
    related_slug: str | None = None
    question_edits: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class PageMeta:
    case_id: str
    slug: str
    title: str
    summary: str


def escaped(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_template(path: Path, values: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    expected = set(PLACEHOLDER_RE.findall(text))
    missing = expected - values.keys()
    if missing:
        raise GenerationError(f"Template values missing for {path.name}: {', '.join(sorted(missing))}")
    rendered = PLACEHOLDER_RE.sub(lambda match: values[match.group(1)], text)
    leftovers = PLACEHOLDER_RE.findall(rendered)
    if leftovers:
        raise GenerationError(f"Unresolved placeholders in {path.name}: {', '.join(sorted(set(leftovers)))}")
    return rendered.rstrip() + "\n"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GenerationError(f"File not found: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"Invalid UTF-8 JSON in {path}: {exc}") from exc


def require_text(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GenerationError(f"{path}: required field `{key}` must be a non-empty string")
    return value.strip()


def resolve_case(selector: str, source_root: Path) -> Path:
    supplied = Path(selector)
    direct_candidates = [supplied, source_root / supplied]
    for candidate in direct_candidates:
        if candidate.is_file():
            return candidate.resolve()

    case_id = supplied.stem if supplied.suffix.lower() == ".json" else selector
    matches = sorted(source_root.rglob(f"{case_id}.json"))
    if not matches:
        raise GenerationError(f"No case matching `{selector}` under {source_root}")
    if len(matches) > 1:
        choices = ", ".join(str(path.relative_to(source_root)) for path in matches)
        raise GenerationError(f"Case ID `{case_id}` is ambiguous: {choices}")
    return matches[0].resolve()


def default_spec(source: Path, data: dict[str, Any], slug_override: str | None) -> PageSpec:
    case_id = require_text(data, "id", source)
    complaint = require_text(data, "chief_complaint", source)
    slug = slug_override or f"clinical-english-{case_id.lower().replace('_', '-')}"
    h1 = f"How to ask about {complaint} in English"
    description = f"Learn patient-friendly English questions for a clinical history involving {complaint}."
    return PageSpec(source=source, slug=slug, h1=h1, meta_description=description)


def validate_slug(slug: str, context: str) -> None:
    if not SLUG_RE.fullmatch(slug):
        raise GenerationError(f"{context}: slug must contain lowercase letters, numbers, and single hyphens: {slug!r}")


def enforce_us_style(texts: list[tuple[str, str]], context: str) -> None:
    for label, value in texts:
        for pattern, guidance in US_STYLE_RULES:
            if pattern.search(value):
                raise GenerationError(f"{context}.{label}: {guidance}; found {pattern.pattern!r}")


def enforce_assumption_safe_questions(questions: list[tuple[str, str]], context: str) -> None:
    for objective, phrase in questions:
        for pattern, guidance in PRESUPPOSITION_RULES:
            if pattern.search(phrase):
                raise GenerationError(
                    f"{context}: question for {objective!r} {guidance}: {phrase!r}. "
                    "Rewrite it in `question_edits` without assuming the patient's answer."
                )


def specs_from_manifest(path: Path, source_root: Path) -> list[PageSpec]:
    manifest = load_json(path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list):
        raise GenerationError(f"{path}: expected an object containing a `pages` list")
    specs: list[PageSpec] = []
    for index, item in enumerate(manifest["pages"]):
        where = f"{path}: pages[{index}]"
        if not isinstance(item, dict):
            raise GenerationError(f"{where} must be an object")
        for key in ("case", "slug", "h1", "meta_description", "lede", "scenario", "quick_answer", "reviewed_on"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise GenerationError(f"{where}.{key} must be a non-empty string")
        if item.get("language_standard") != "en-US":
            raise GenerationError(f"{where}.language_standard must be `en-US`")
        if item.get("patient_answer_assumptions_checked") is not True:
            raise GenerationError(f"{where}.patient_answer_assumptions_checked must be true after editorial QA")
        try:
            date.fromisoformat(item["reviewed_on"])
        except ValueError as exc:
            raise GenerationError(f"{where}.reviewed_on must use YYYY-MM-DD format") from exc
        source = resolve_case(item["case"], source_root)
        data = validate_case(load_json(source), source)
        slug = item["slug"].strip()
        validate_slug(slug, where)
        raw_related_slug = item.get("related_slug")
        related_slug: str | None = None
        if raw_related_slug is not None:
            if not isinstance(raw_related_slug, str) or not raw_related_slug.strip():
                raise GenerationError(f"{where}.related_slug must be a non-empty string when present")
            related_slug = raw_related_slug.strip()
            validate_slug(related_slug, f"{where}.related_slug")
        raw_edits = item.get("question_edits", [])
        if not isinstance(raw_edits, list):
            raise GenerationError(f"{where}.question_edits must be a list")
        source_objectives = {ask["objective"].strip() for ask in data["teaching"]["must_ask"]}
        edits: dict[str, dict[str, Any]] = {}
        coaching_count = 0
        allowed_edit_keys = {"objective", "phrases", "purpose", "why_this_wording", "alternatives"}
        for edit_index, edit in enumerate(raw_edits):
            edit_where = f"{where}.question_edits[{edit_index}]"
            if not isinstance(edit, dict):
                raise GenerationError(f"{edit_where} must be an object")
            unknown = set(edit) - allowed_edit_keys
            if unknown:
                raise GenerationError(f"{edit_where} contains unsupported keys: {', '.join(sorted(unknown))}")
            objective = edit.get("objective")
            if not isinstance(objective, str) or objective.strip() not in source_objectives:
                raise GenerationError(f"{edit_where}.objective must exactly match a source must_ask objective")
            objective = objective.strip()
            if objective in edits:
                raise GenerationError(f"{edit_where}: duplicate edit for objective {objective!r}")
            phrases = edit.get("phrases")
            if phrases is not None and (
                not isinstance(phrases, list)
                or not phrases
                or any(not isinstance(phrase, str) or not phrase.strip() for phrase in phrases)
            ):
                raise GenerationError(f"{edit_where}.phrases must be a non-empty list of strings")
            for text_key in ("purpose", "why_this_wording"):
                if text_key in edit and (not isinstance(edit[text_key], str) or not edit[text_key].strip()):
                    raise GenerationError(f"{edit_where}.{text_key} must be a non-empty string")
            alternatives = edit.get("alternatives", [])
            if not isinstance(alternatives, list):
                raise GenerationError(f"{edit_where}.alternatives must be a list")
            if alternatives and not edit.get("why_this_wording"):
                raise GenerationError(f"{edit_where}.alternatives requires `why_this_wording`")
            for alt_index, alternative in enumerate(alternatives):
                if not isinstance(alternative, dict) or set(alternative) != {"label", "phrase"}:
                    raise GenerationError(f"{edit_where}.alternatives[{alt_index}] requires only `label` and `phrase`")
                if any(not isinstance(alternative[key], str) or not alternative[key].strip() for key in ("label", "phrase")):
                    raise GenerationError(f"{edit_where}.alternatives[{alt_index}] values must be non-empty strings")
            if edit.get("why_this_wording"):
                coaching_count += 1
            edits[objective] = edit
        if coaching_count < 2:
            raise GenerationError(f"{where}: reviewed pages require at least two `why_this_wording` coaching notes")
        final_questions: list[tuple[str, str]] = []
        editorial_texts = [
            ("h1", item["h1"].strip()),
            ("meta_description", item["meta_description"].strip()),
            ("lede", item["lede"].strip()),
            ("scenario", item["scenario"].strip()),
            ("quick_answer", item["quick_answer"].strip()),
        ]
        for ask in data["teaching"]["must_ask"]:
            objective = ask["objective"].strip()
            edit = edits.get(objective, {})
            phrases = edit.get("phrases") or [ask["say"].strip()]
            final_questions.extend((objective, phrase.strip()) for phrase in phrases)
            for key in ("purpose", "why_this_wording"):
                if edit.get(key):
                    editorial_texts.append((f"question_edits[{objective}].{key}", edit[key].strip()))
            for alternative in edit.get("alternatives", []):
                editorial_texts.append((f"question_edits[{objective}].alternative", alternative["phrase"].strip()))
        editorial_texts.extend((f"question[{objective}]", phrase) for objective, phrase in final_questions)
        enforce_us_style(editorial_texts, where)
        enforce_assumption_safe_questions(final_questions, where)
        specs.append(PageSpec(
            source=source,
            slug=slug,
            h1=item["h1"].strip(),
            meta_description=item["meta_description"].strip(),
            lede=item["lede"].strip(),
            scenario=item["scenario"].strip(),
            quick_answer=item["quick_answer"].strip(),
            reviewed_on=item["reviewed_on"].strip(),
            related_slug=related_slug,
            question_edits=edits,
        ))
    if not specs:
        raise GenerationError(f"{path}: the manifest contains no selected pages")
    return specs


def validate_case(data: Any, source: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise GenerationError(f"{source}: top-level JSON must be an object")
    for key in ("id", "system", "chief_complaint"):
        require_text(data, key, source)
    teaching = data.get("teaching")
    if not isinstance(teaching, dict):
        raise GenerationError(f"{source}: supported patient-history cases require a `teaching` object")
    asks = teaching.get("must_ask")
    if not isinstance(asks, list) or not asks:
        raise GenerationError(f"{source}: `teaching.must_ask` must be a non-empty list")
    for index, ask in enumerate(asks):
        where = f"{source}: teaching.must_ask[{index}]"
        if not isinstance(ask, dict):
            raise GenerationError(f"{where} must be an object")
        for key in ("objective", "say"):
            if not isinstance(ask.get(key), str) or not ask[key].strip():
                raise GenerationError(f"{where}.{key} must be a non-empty string")
        domains = ask.get("domains", [])
        if not isinstance(domains, list) or any(not isinstance(domain, str) for domain in domains):
            raise GenerationError(f"{where}.domains must be a list of strings when present")
    return data


def humanize(value: str) -> str:
    return value.replace("_", " ").strip().title()


def oxford_join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def question_group(ask: dict[str, Any]) -> str:
    domains = set(ask.get("domains", []))
    for label, group_domains in GROUPS:
        if domains & group_domains:
            return label
    return "Other useful questions"


def render_question_sections(asks: list[dict[str, Any]], edits: dict[str, dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ask in asks:
        grouped.setdefault(question_group(ask), []).append(ask)
    ordered_labels = [label for label, _ in GROUPS] + ["Other useful questions"]
    sections: list[str] = []
    for label in ordered_labels:
        rows = grouped.get(label)
        if not rows:
            continue
        cards = []
        for ask in rows:
            edit = edits.get(ask["objective"].strip(), {})
            phrases = edit.get("phrases") or [ask["say"].strip()]
            phrases_html = "\n".join(
                f'                  <p class="phrase">“{escaped(phrase.strip())}”</p>' for phrase in phrases
            )
            purpose = edit.get("purpose", ask["objective"].strip())
            coaching_html = ""
            why = edit.get("why_this_wording")
            alternatives = edit.get("alternatives", [])
            if why or alternatives:
                option_rows = ""
                if alternatives:
                    option_rows = (
                        '\n                  <dl class="wording-options">\n'
                        + "\n".join(
                            '                    <div>'
                            f'<dt>{escaped(option["label"].strip())}</dt>'
                            f'<dd>“{escaped(option["phrase"].strip())}”</dd></div>'
                            for option in alternatives
                        )
                        + "\n                  </dl>"
                    )
                coaching_html = (
                    '\n                <div class="wording-coach">\n'
                    '                  <h4>Why this wording</h4>\n'
                    f'                  <p>{escaped(why.strip())}</p>'
                    + option_rows
                    + "\n                </div>"
                )
            cards.append(
                '              <article class="question-card">\n'
                '                <div class="phrase-list">\n'
                f"{phrases_html}\n"
                '                </div>\n'
                f'                <p class="purpose"><strong>Purpose:</strong> {escaped(purpose.strip())}.</p>'
                f"{coaching_html}\n"
                "              </article>"
            )
        sections.append(
            '            <section class="question-group">\n'
            f"              <h3>{escaped(label)}</h3>\n"
            '              <div class="question-list">\n'
            + "\n".join(cards)
            + "\n              </div>\n            </section>"
        )
    return "\n".join(sections)


def structured_data(spec: PageSpec, data: dict[str, Any], canonical_url: str) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": ["WebPage", "LearningResource"],
        "name": spec.h1,
        "description": spec.meta_description,
        "url": canonical_url,
        "inLanguage": "en-US",
        "isAccessibleForFree": True,
        "learningResourceType": "Clinical communication guide",
        "teaches": spec.h1,
        "audience": {
            "@type": "EducationalAudience",
            "educationalRole": "Medical student or healthcare professional",
        },
        "isPartOf": {"@type": "WebSite", "name": "Bedside English", "url": f"{SITE_ORIGIN}/"},
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def existing_pages(learning_root: Path) -> dict[str, PageMeta]:
    pages: dict[str, PageMeta] = {}
    if not learning_root.exists():
        return pages
    for path in sorted(learning_root.glob("*/index.html")):
        match = PAGE_META_RE.search(path.read_text(encoding="utf-8"))
        if not match:
            continue
        case_id, title, summary = (html.unescape(value) for value in match.groups())
        pages[path.parent.name] = PageMeta(case_id, path.parent.name, title, summary)
    return pages


def build_page(spec: PageSpec, data: dict[str, Any], related: PageMeta | None) -> tuple[str, PageMeta]:
    case_id = data["id"].strip()
    asks = data["teaching"]["must_ask"]
    scenario = f"{spec.scenario} Your task is to explore the history in natural English without overwhelming the patient with clinical jargon."
    canonical_url = f"{SITE_ORIGIN}/learning/{spec.slug}/"
    has_radiation = any("radiation" in ask.get("domains", []) for ask in asks)
    language_note = (
        'A plain expression such as “Does it move anywhere else?” can be easier for a patient to understand than a technical term such as “Does it radiate?”'
        if has_radiation
        else "Short, direct questions are often easier to answer. Ask one idea at a time, then follow the patient's wording when you need more detail."
    )
    related_html = (
        f'<a href="../{escaped(related.slug)}/">{escaped(related.title)} <span aria-hidden="true">→</span></a>'
        if related
        else '<a href="../">Browse all clinical English guides <span aria-hidden="true">→</span></a>'
    )
    reviewed_date = date.fromisoformat(spec.reviewed_on) if spec.reviewed_on else None
    reviewed_display = (
        f"{reviewed_date.day} {reviewed_date.strftime('%B %Y')}"
        if reviewed_date
        else "Not yet reviewed"
    )
    values = {
        "PAGE_TITLE": escaped(f"{spec.h1} | Bedside English"),
        "META_DESCRIPTION": escaped(spec.meta_description),
        "CANONICAL_URL": escaped(canonical_url),
        "OG_IMAGE_URL": escaped(f"{SITE_ORIGIN}/assets/social/og-cover.png"),
        "STRUCTURED_DATA": structured_data(spec, data, canonical_url),
        "CASE_ID": escaped(case_id),
        "SOURCE_SHA256": hashlib.sha256(spec.source.read_bytes()).hexdigest(),
        "H1": escaped(spec.h1),
        "SYSTEM": escaped(humanize(data["system"])),
        "LEDE": escaped(spec.lede),
        "QUICK_ANSWER": escaped(spec.quick_answer),
        "FEATURED_QUESTION": escaped((spec.question_edits.get(asks[0]["objective"].strip(), {}).get("phrases") or [asks[0]["say"].strip()])[0]),
        "SCENARIO": escaped(scenario),
        "LANGUAGE_NOTE": escaped(language_note),
        "QUESTION_SECTIONS": render_question_sections(asks, spec.question_edits),
        "RELATED_LINK": related_html,
        "REVIEWED_ON_ISO": escaped(spec.reviewed_on),
        "REVIEWED_ON_DISPLAY": escaped(reviewed_display),
    }
    rendered = render_template(TEMPLATE_ROOT / "page.html", values)
    return rendered, PageMeta(case_id, spec.slug, spec.h1, spec.meta_description)


def build_hub(pages: list[PageMeta]) -> str:
    cards = []
    for index, page in enumerate(sorted(pages, key=lambda item: item.title.lower()), start=1):
        cards.append(
            f'<a class="guide-card" href="{escaped(page.slug)}/">'
            f'<span class="card-index">GUIDE {index:02d}</span>'
            f'<h3>{escaped(page.title)}</h3><p>{escaped(page.summary)}</p>'
            '<span class="card-link">Read the guide →</span></a>'
        )
    return render_template(
        TEMPLATE_ROOT / "index.html",
        {
            "HUB_URL": escaped(f"{SITE_ORIGIN}/learning/"),
            "OG_IMAGE_URL": escaped(f"{SITE_ORIGIN}/assets/social/og-cover.png"),
            "GUIDE_CARDS": "\n        ".join(cards),
        },
    )


def write_or_check(path: Path, content: str, check: bool, mismatches: list[Path]) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            mismatches.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def generate(specs: list[PageSpec], output_root: Path, check: bool) -> int:
    if not specs:
        raise GenerationError("Select at least one case")
    slugs = [spec.slug for spec in specs]
    if len(slugs) != len(set(slugs)):
        raise GenerationError("Selected pages contain duplicate slugs")

    learning_root = output_root / "learning"
    known = existing_pages(learning_root)
    loaded: list[tuple[PageSpec, dict[str, Any]]] = []
    case_ids: dict[str, str] = {meta.case_id: slug for slug, meta in known.items()}
    for spec in specs:
        validate_slug(spec.slug, str(spec.source))
        data = validate_case(load_json(spec.source), spec.source)
        case_id = data["id"].strip()
        occupant = known.get(spec.slug)
        if occupant and occupant.case_id != case_id:
            raise GenerationError(f"Slug collision: `{spec.slug}` already belongs to case `{occupant.case_id}`")
        other_slug = case_ids.get(case_id)
        if other_slug and other_slug != spec.slug:
            raise GenerationError(f"Case `{case_id}` is already published at slug `{other_slug}`")
        case_ids[case_id] = spec.slug
        loaded.append((spec, data))

    combined = dict(known)
    for spec, data in loaded:
        combined[spec.slug] = PageMeta(data["id"].strip(), spec.slug, spec.h1, spec.meta_description)
    all_pages = list(combined.values())

    mismatches: list[Path] = []
    pages_by_slug = {page.slug: page for page in all_pages}
    for spec, data in loaded:
        related: PageMeta | None = None
        if spec.related_slug:
            if spec.related_slug == spec.slug:
                raise GenerationError(f"{spec.slug}: `related_slug` cannot point to itself")
            related = pages_by_slug.get(spec.related_slug)
            if not related:
                raise GenerationError(f"{spec.slug}: unknown `related_slug` `{spec.related_slug}`")
        page, _ = build_page(spec, data, related)
        write_or_check(learning_root / spec.slug / "index.html", page, check, mismatches)
    write_or_check(learning_root / "index.html", build_hub(all_pages), check, mismatches)
    write_or_check(output_root / "sitemap.xml", build_sitemap(output_root), check, mismatches)

    if mismatches:
        print("Generated output is out of date:", file=sys.stderr)
        for path in mismatches:
            print(f"  {path}", file=sys.stderr)
        return 1
    verb = "Verified" if check else "Generated"
    print(f"{verb} {len(loaded)} learning page(s).")
    for spec, _ in loaded:
        print(f"  learning/{spec.slug}/index.html")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT, help="root directory containing case JSON files")
    parser.add_argument("--manifest", type=Path, help="editorial page-selection manifest (default when --case is omitted)")
    parser.add_argument("--case", action="append", default=[], help="case ID or JSON path; may be repeated")
    parser.add_argument("--slug", help="reviewed URL slug; only valid with one --case")
    parser.add_argument("--output-root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help="verify that generated files are current without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source_root = args.source_root.resolve()
        if args.check and not args.case and not source_root.is_dir():
            print(f"Skipping learning-page check: source root {source_root} not found")
            return 0
        if args.case and args.manifest:
            raise GenerationError("Use either --manifest or --case, not both")
        if args.slug and len(args.case) != 1:
            raise GenerationError("--slug requires exactly one --case")
        if args.case:
            specs = []
            for selector in args.case:
                source = resolve_case(selector, source_root)
                data = validate_case(load_json(source), source)
                specs.append(default_spec(source, data, args.slug))
        else:
            specs = specs_from_manifest((args.manifest or DEFAULT_MANIFEST).resolve(), source_root)
        return generate(specs, args.output_root.resolve(), args.check)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
