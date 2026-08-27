#!/usr/bin/env python3
"""Generate source-locked oral case-presentation learning guides."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from site_map import build_sitemap  # noqa: E402


DEFAULT_MANIFEST = ROOT / "case-presentation-pages.json"
DEFAULT_SOURCE_ROOT = ROOT.parent / "Medvoicetrainer-android-app-version" / "data" / "cases"
TEMPLATE_ROOT = TOOLS_ROOT / "case_presentation_templates"
OUTPUT_ROOT = ROOT / "case-presentations"
SITE_ORIGIN = "https://bedsideenglish.github.io"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PLACEHOLDER_RE = re.compile(r"{{([A-Z0-9_]+)}}")
US_STYLE_RULES = (
    (re.compile(r"\bdyspnoea\b", re.IGNORECASE), "use US dyspnea"),
    (re.compile(r"\bhaemoptysis\b", re.IGNORECASE), "use US hemoptysis"),
    (re.compile(r"\b(?:organisation|recognise|prioritise|hospitalisation)\w*\b", re.IGNORECASE), "use US spelling"),
    (re.compile(r"\bBD\b|\bOD\b|\bTDS\b", re.IGNORECASE), "expand non-US dosing abbreviations in public prose"),
)
OVERCLAIM_RULES = (
    (re.compile(r"\bguarantees?\b", re.IGNORECASE), "do not guarantee an outcome"),
    (re.compile(r"\balways rules? (?:in|out)\b", re.IGNORECASE), "avoid absolute diagnostic claims"),
    (re.compile(r"\bdefinitively (?:diagnoses|excludes)\b", re.IGNORECASE), "avoid unsupported diagnostic certainty"),
)


class GenerationError(RuntimeError):
    """The reviewed content contract was not met."""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def words(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def exact_keys(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(data) - allowed
    missing = allowed - set(data)
    if unknown:
        raise GenerationError(f"{where} has unsupported keys: {', '.join(sorted(unknown))}")
    if missing:
        raise GenerationError(f"{where} is missing keys: {', '.join(sorted(missing))}")


def require_text(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GenerationError(f"{where}.{key} must be non-empty text")
    return value.strip()


def require_text_list(data: dict[str, Any], key: str, where: str, minimum: int = 1) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or len(value) < minimum or any(not isinstance(item, str) or not item.strip() for item in value):
        raise GenerationError(f"{where}.{key} must contain at least {minimum} non-empty strings")
    return [item.strip() for item in value]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GenerationError(f"JSON file not found: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"Invalid UTF-8 JSON in {path}: {exc}") from exc


def get_path(value: Any, dotted_path: str) -> Any:
    current = value
    for token in dotted_path.split("."):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise KeyError(dotted_path)
    return current


def render_template(path: Path, values: dict[str, str]) -> str:
    source = path.read_text(encoding="utf-8")
    expected = set(PLACEHOLDER_RE.findall(source))
    missing = expected - values.keys()
    if missing:
        raise GenerationError(f"Missing template values for {path.name}: {', '.join(sorted(missing))}")
    rendered = PLACEHOLDER_RE.sub(lambda match: values[match.group(1)], source)
    if PLACEHOLDER_RE.search(rendered):
        raise GenerationError(f"Unresolved template marker in {path.name}")
    return rendered.rstrip() + "\n"


def validate_page(page: Any, source_root: Path, where: str) -> dict[str, Any]:
    if not isinstance(page, dict):
        raise GenerationError(f"{where} must be an object")
    required = {
        "slug", "title", "h1", "meta_description", "lede", "published_on", "reviewed_on", "library_order",
        "search", "source", "scenario", "quick_question", "quick_answer", "sections", "known_gaps",
        "compression", "follow_ups", "checklist", "mistakes", "faq", "sources", "review",
    }
    exact_keys(page, required, where)
    for key in ("slug", "title", "h1", "meta_description", "lede", "published_on", "reviewed_on", "quick_question", "quick_answer"):
        require_text(page, key, where)
    if not SLUG_RE.fullmatch(page["slug"]):
        raise GenerationError(f"{where}.slug must be lowercase kebab-case")
    if not 35 <= len(page["title"]) <= 70:
        raise GenerationError(f"{where}.title must be 35-70 characters")
    if not 110 <= len(page["meta_description"]) <= 170:
        raise GenerationError(f"{where}.meta_description must be 110-170 characters")
    if not 35 <= words(page["quick_answer"]) <= 95:
        raise GenerationError(f"{where}.quick_answer must be 35-95 words")
    for key in ("published_on", "reviewed_on"):
        try:
            date.fromisoformat(page[key])
        except ValueError as exc:
            raise GenerationError(f"{where}.{key} must use YYYY-MM-DD") from exc
    if page["reviewed_on"] < page["published_on"]:
        raise GenerationError(f"{where}.reviewed_on cannot predate publication")
    if not isinstance(page["library_order"], int) or page["library_order"] < 1:
        raise GenerationError(f"{where}.library_order must be a positive integer")

    search = page["search"]
    if not isinstance(search, dict):
        raise GenerationError(f"{where}.search must be an object")
    exact_keys(search, {"primary_query", "supporting_queries", "reader_task"}, f"{where}.search")
    primary = require_text(search, "primary_query", f"{where}.search").lower()
    require_text(search, "reader_task", f"{where}.search")
    require_text_list(search, "supporting_queries", f"{where}.search", 3)
    if primary not in f"{page['title']} {page['h1']}".lower():
        raise GenerationError(f"{where}: primary query must appear in title or h1")

    source = page["source"]
    if not isinstance(source, dict):
        raise GenerationError(f"{where}.source must be an object")
    exact_keys(source, {"case_id", "relative_path", "facts"}, f"{where}.source")
    case_id = require_text(source, "case_id", f"{where}.source")
    relative = require_text(source, "relative_path", f"{where}.source")
    source_path = (source_root / relative).resolve()
    if source_root.resolve() not in source_path.parents:
        raise GenerationError(f"{where}.source.relative_path leaves the source root")
    case = read_json(source_path)
    if not isinstance(case, dict) or case.get("id") != case_id:
        raise GenerationError(f"{where}: source case id does not match {case_id}")
    facts = source["facts"]
    if not isinstance(facts, list) or len(facts) < 10:
        raise GenerationError(f"{where}.source.facts must contain at least 10 facts")
    fact_values: dict[str, Any] = {}
    fact_paths: set[str] = set()
    for index, fact in enumerate(facts):
        fact_where = f"{where}.source.facts[{index}]"
        if not isinstance(fact, dict):
            raise GenerationError(f"{fact_where} must be an object")
        exact_keys(fact, {"id", "label", "path"}, fact_where)
        for key in fact:
            require_text(fact, key, fact_where)
        if not ID_RE.fullmatch(fact["id"]):
            raise GenerationError(f"{fact_where}.id must be lowercase snake_case")
        if fact["id"] in fact_values:
            raise GenerationError(f"{fact_where}.id is duplicated")
        if fact["path"] in fact_paths:
            raise GenerationError(f"{fact_where}.path is duplicated")
        try:
            value = get_path(case, fact["path"])
        except KeyError as exc:
            raise GenerationError(f"{fact_where}.path is absent from source case: {fact['path']}") from exc
        if not isinstance(value, (str, int, float)):
            raise GenerationError(f"{fact_where}.path must resolve to a scalar source value")
        fact_values[fact["id"]] = value
        fact_paths.add(fact["path"])

    scenario = page["scenario"]
    if not isinstance(scenario, dict):
        raise GenerationError(f"{where}.scenario must be an object")
    exact_keys(scenario, {"setting", "audience", "available_data", "target_duration"}, f"{where}.scenario")
    for key in scenario:
        require_text(scenario, key, f"{where}.scenario")

    sections = page["sections"]
    expected_sections = (("opening", "Opening one-liner"), ("hpi", "History of present illness"), ("history", "Relevant background"), ("data", "Objective data"), ("assessment", "Assessment"), ("plan", "Plan"))
    if not isinstance(sections, list) or len(sections) != len(expected_sections):
        raise GenerationError(f"{where}.sections must contain the six required presentation sections")
    referenced: set[str] = set()
    all_spoken = []
    for index, (section, expected) in enumerate(zip(sections, expected_sections)):
        section_where = f"{where}.sections[{index}]"
        if not isinstance(section, dict):
            raise GenerationError(f"{section_where} must be an object")
        exact_keys(section, {"id", "name", "job", "spoken", "fact_refs", "why", "language_note"}, section_where)
        if (section.get("id"), section.get("name")) != expected:
            raise GenerationError(f"{section_where} must be {expected[0]} / {expected[1]}")
        for key in ("job", "spoken", "why"):
            require_text(section, key, section_where)
        refs = require_text_list(section, "fact_refs", section_where)
        unknown = set(refs) - fact_values.keys()
        if unknown:
            raise GenerationError(f"{section_where} references unknown facts: {', '.join(sorted(unknown))}")
        referenced.update(refs)
        all_spoken.append(section["spoken"])
        note = section["language_note"]
        if not isinstance(note, dict):
            raise GenerationError(f"{section_where}.language_note must be an object")
        exact_keys(note, {"less_clear", "preferred", "why"}, f"{section_where}.language_note")
        for key in note:
            require_text(note, key, f"{section_where}.language_note")
        if section["id"] == "data":
            numeric_source = " ".join(str(fact_values[ref]) for ref in refs)
            required_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", numeric_source))
            spoken_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", section["spoken"]))
            missing_numbers = required_numbers - spoken_numbers
            ignored = {"0", "1", "2", "3", "4", "5", "6", "7", "10", "14"}
            if missing_numbers - ignored:
                raise GenerationError(f"{section_where}.spoken omits source result number(s): {', '.join(sorted(missing_numbers - ignored))}")
    if len(referenced) < 10:
        raise GenerationError(f"{where}: presentation must ground itself in at least 10 source facts")

    gaps = page["known_gaps"]
    if not isinstance(gaps, list) or len(gaps) < 2:
        raise GenerationError(f"{where}.known_gaps must contain at least two explicit omissions")
    for index, gap in enumerate(gaps):
        gap_where = f"{where}.known_gaps[{index}]"
        if not isinstance(gap, dict):
            raise GenerationError(f"{gap_where} must be an object")
        exact_keys(gap, {"label", "missing_paths", "say", "why"}, gap_where)
        for key in ("label", "say", "why"):
            require_text(gap, key, gap_where)
        for missing_path in require_text_list(gap, "missing_paths", gap_where):
            try:
                get_path(case, missing_path)
            except KeyError:
                continue
            raise GenerationError(f"{gap_where}: claimed-missing path exists in source: {missing_path}")

    compression = page["compression"]
    if not isinstance(compression, list) or len(compression) < 4:
        raise GenerationError(f"{where}.compression must contain at least four editorial decisions")
    for index, item in enumerate(compression):
        item_where = f"{where}.compression[{index}]"
        if not isinstance(item, dict):
            raise GenerationError(f"{item_where} must be an object")
        exact_keys(item, {"source_detail", "decision", "why"}, item_where)
        for key in item:
            require_text(item, key, item_where)
        if item["decision"] not in {"Lead", "Include", "Compress", "Omit"}:
            raise GenerationError(f"{item_where}.decision is unsupported")

    follow_ups = page["follow_ups"]
    if not isinstance(follow_ups, list) or len(follow_ups) < 3:
        raise GenerationError(f"{where}.follow_ups must contain at least three items")
    for index, item in enumerate(follow_ups):
        item_where = f"{where}.follow_ups[{index}]"
        if not isinstance(item, dict):
            raise GenerationError(f"{item_where} must be an object")
        exact_keys(item, {"question", "answer", "fact_refs"}, item_where)
        require_text(item, "question", item_where)
        require_text(item, "answer", item_where)
        unknown = set(require_text_list(item, "fact_refs", item_where)) - fact_values.keys()
        if unknown:
            raise GenerationError(f"{item_where} references unknown facts: {', '.join(sorted(unknown))}")

    checklist = require_text_list(page, "checklist", where, 7)
    if len(checklist) > 10:
        raise GenerationError(f"{where}.checklist must contain no more than 10 items")
    for collection, minimum in (("mistakes", 3), ("faq", 3), ("sources", 3)):
        value = page[collection]
        if not isinstance(value, list) or len(value) < minimum:
            raise GenerationError(f"{where}.{collection} must contain at least {minimum} items")
    for index, item in enumerate(page["mistakes"]):
        exact_keys(item, {"problem", "repair"}, f"{where}.mistakes[{index}]")
        require_text(item, "problem", f"{where}.mistakes[{index}]")
        require_text(item, "repair", f"{where}.mistakes[{index}]")
    for index, item in enumerate(page["faq"]):
        exact_keys(item, {"question", "answer"}, f"{where}.faq[{index}]")
        require_text(item, "question", f"{where}.faq[{index}]")
        require_text(item, "answer", f"{where}.faq[{index}]")
    for index, item in enumerate(page["sources"]):
        source_where = f"{where}.sources[{index}]"
        exact_keys(item, {"title", "publisher", "url", "accessed_on"}, source_where)
        for key in item:
            require_text(item, key, source_where)
        parsed = urlsplit(item["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise GenerationError(f"{source_where}.url must be an HTTPS URL")
        date.fromisoformat(item["accessed_on"])

    review = page["review"]
    expected_review = {
        "source_case_checked", "no_facts_invented", "clinical_reasoning_checked", "presentation_flow_read_aloud",
        "us_english_checked", "search_intent_checked", "human_value_checked", "safety_boundary_checked",
    }
    if not isinstance(review, dict):
        raise GenerationError(f"{where}.review must be an object")
    exact_keys(review, expected_review, f"{where}.review")
    unchecked = [key for key, value in review.items() if value is not True]
    if unchecked:
        raise GenerationError(f"{where}.review has unchecked attestations: {', '.join(unchecked)}")

    corpus = "\n".join(all_text(page))
    for pattern, message in (*US_STYLE_RULES, *OVERCLAIM_RULES):
        if pattern.search(corpus):
            raise GenerationError(f"{where}: {message}; found {pattern.pattern}")

    validated = deepcopy(page)
    validated["_case"] = case
    validated["_source_path"] = source_path
    validated["_source_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    validated["_fact_values"] = fact_values
    return validated


def all_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for child in value for text in all_text(child)]
    if isinstance(value, dict):
        return [text for key, child in value.items() if not key.startswith("_") for text in all_text(child)]
    return []


def load_pages(manifest_path: Path, source_root: Path) -> list[dict[str, Any]]:
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or set(manifest) != {"pages"} or not isinstance(manifest["pages"], list) or not manifest["pages"]:
        raise GenerationError("Manifest must be an object with a non-empty pages list")
    pages = [validate_page(page, source_root, f"pages[{index}]") for index, page in enumerate(manifest["pages"])]
    slugs = [page["slug"] for page in pages]
    orders = [page["library_order"] for page in pages]
    if len(slugs) != len(set(slugs)) or len(orders) != len(set(orders)):
        raise GenerationError("Page slugs and library_order values must be unique")
    return sorted(pages, key=lambda page: page["library_order"])


def section_cards(page: dict[str, Any]) -> str:
    cards = []
    for index, section in enumerate(page["sections"], 1):
        note = section["language_note"]
        cards.append(
            f'<article class="presentation-step" id="step-{esc(section["id"])}">'
            f'<header><span>{index:02d}</span><div><p>{esc(section["name"])}</p><h3>{esc(section["job"])}</h3></div></header>'
            f'<blockquote><p>“{esc(section["spoken"])}”</p></blockquote>'
            f'<p class="why"><strong>Why it belongs:</strong> {esc(section["why"])}</p>'
            f'<div class="language-contrast"><div><span>Less clear</span><p>{esc(note["less_clear"])}</p></div>'
            f'<div><span>Prefer</span><p>{esc(note["preferred"])}</p></div>'
            f'<p><strong>Why:</strong> {esc(note["why"])}</p></div></article>'
        )
    return "".join(cards)


def full_script(page: dict[str, Any]) -> str:
    return "".join(f'<p data-part="{esc(section["id"])}">{esc(section["spoken"])}</p>' for section in page["sections"])


def render_page(page: dict[str, Any]) -> str:
    canonical = f"{SITE_ORIGIN}/case-presentations/{page['slug']}/"
    citations = [item["url"] for item in page["sources"]]
    structured = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": ["Article", "LearningResource"], "headline": page["h1"], "description": page["meta_description"],
                "url": canonical, "datePublished": page["published_on"], "dateModified": page["reviewed_on"],
                "inLanguage": "en-US", "educationalUse": "Clinical English oral case-presentation practice",
                "audience": {"@type": "EducationalAudience", "educationalRole": page["scenario"]["audience"]},
                "isPartOf": {"@type": "WebSite", "name": "Bedside English", "url": f"{SITE_ORIGIN}/"},
                "citation": citations,
            },
            {
                "@type": "BreadcrumbList", "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_ORIGIN}/"},
                    {"@type": "ListItem", "position": 2, "name": "Case presentations", "item": f"{SITE_ORIGIN}/case-presentations/"},
                    {"@type": "ListItem", "position": 3, "name": page["h1"], "item": canonical},
                ],
            },
        ],
    }
    gaps = "".join(
        f'<article><h3>{esc(item["label"])}</h3><p class="say">Say: “{esc(item["say"])}”</p><p>{esc(item["why"])}</p></article>'
        for item in page["known_gaps"]
    )
    compression = "".join(
        f'<tr><td>{esc(item["source_detail"])}</td><td><span class="decision decision-{item["decision"].lower()}">{esc(item["decision"])}</span></td><td>{esc(item["why"])}</td></tr>'
        for item in page["compression"]
    )
    follow_ups = "".join(
        f'<article><h3>{esc(item["question"])}</h3><p>{esc(item["answer"])}</p></article>' for item in page["follow_ups"]
    )
    mistakes = "".join(
        f'<article><p class="mistake">{esc(item["problem"])}</p><p><strong>Repair:</strong> {esc(item["repair"])}</p></article>' for item in page["mistakes"]
    )
    faq = "".join(f'<details><summary>{esc(item["question"])}</summary><p>{esc(item["answer"])}</p></details>' for item in page["faq"])
    sources = "".join(
        f'<li><a href="{esc(item["url"])}" target="_blank" rel="noopener noreferrer">{esc(item["title"])}</a><span>{esc(item["publisher"])} · accessed {esc(item["accessed_on"])}</span></li>'
        for item in page["sources"]
    )
    values = {
        "PAGE_TITLE": esc(page["title"]), "H1": esc(page["h1"]), "META_DESCRIPTION": esc(page["meta_description"]),
        "LEDE": esc(page["lede"]), "CANONICAL_URL": esc(canonical), "PUBLISHED_ON": esc(page["published_on"]),
        "REVIEWED_ON": esc(page["reviewed_on"]), "QUICK_QUESTION": esc(page["quick_question"]),
        "QUICK_ANSWER": esc(page["quick_answer"]), "SETTING": esc(page["scenario"]["setting"]),
        "AUDIENCE": esc(page["scenario"]["audience"]), "AVAILABLE_DATA": esc(page["scenario"]["available_data"]),
        "TARGET_DURATION": esc(page["scenario"]["target_duration"]), "CASE_ID": esc(page["source"]["case_id"]),
        "SOURCE_SHA256": esc(page["_source_sha256"]), "SECTION_CARDS": section_cards(page), "FULL_SCRIPT": full_script(page),
        "KNOWN_GAPS": gaps, "COMPRESSION_ROWS": compression, "FOLLOW_UPS": follow_ups,
        "CHECKLIST_ITEMS": "".join(f"<li>{esc(item)}</li>" for item in page["checklist"]),
        "MISTAKES": mistakes, "FAQ_ITEMS": faq, "SOURCE_ITEMS": sources,
        "STRUCTURED_DATA": json.dumps(structured, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
        "OG_IMAGE_URL": f"{SITE_ORIGIN}/assets/social/og-cover.png",
    }
    return render_template(TEMPLATE_ROOT / "page.html", values)


def render_hub(pages: list[dict[str, Any]]) -> str:
    cards = "".join(
        f'<a class="guide-card" href="{esc(page["slug"])}/"><span class="card-index">{index:02d} · {esc(page["_case"].get("system", "clinical"))}</span>'
        f'<h2>{esc(page["h1"])}</h2><p>{esc(page["lede"])}</p><span class="card-link">Study the presentation <span aria-hidden="true">→</span></span></a>'
        for index, page in enumerate(pages, 1)
    )
    return render_template(TEMPLATE_ROOT / "index.html", {"GUIDE_CARDS": cards, "HUB_URL": f"{SITE_ORIGIN}/case-presentations/", "OG_IMAGE_URL": f"{SITE_ORIGIN}/assets/social/og-cover.png"})


def expected_outputs(pages: list[dict[str, Any]]) -> dict[Path, str]:
    outputs = {OUTPUT_ROOT / "index.html": render_hub(pages)}
    outputs.update({OUTPUT_ROOT / page["slug"] / "index.html": render_page(page) for page in pages})
    return outputs


def write_or_check(outputs: dict[Path, str], check: bool) -> None:
    errors = []
    for path, expected in outputs.items():
        if check:
            actual = path.read_text(encoding="utf-8") if path.is_file() else None
            if actual != expected:
                errors.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8", newline="\n")
    if check and errors:
        raise GenerationError("Generated output is stale or missing: " + ", ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--page", help="generate or check one slug")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        pages = load_pages(args.manifest.resolve(), args.source_root.resolve())
        if args.page:
            pages = [page for page in pages if page["slug"] == args.page]
            if not pages:
                raise GenerationError(f"Unknown page slug: {args.page}")
            outputs = {OUTPUT_ROOT / pages[0]["slug"] / "index.html": render_page(pages[0])}
        else:
            outputs = expected_outputs(pages)
        write_or_check(outputs, args.check)
        if not args.page:
            sitemap = build_sitemap(ROOT)
            sitemap_path = ROOT / "sitemap.xml"
            if args.check:
                if sitemap_path.read_text(encoding="utf-8") != sitemap:
                    raise GenerationError("sitemap.xml is stale")
            else:
                sitemap_path.write_text(sitemap, encoding="utf-8", newline="\n")
        action = "Checked" if args.check else "Generated"
        print(f"{action} {len(pages)} case-presentation page(s){' plus hub' if not args.page else ''}.")
        return 0
    except GenerationError as exc:
        print(f"Case-presentation generation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
