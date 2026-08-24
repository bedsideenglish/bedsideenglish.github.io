#!/usr/bin/env python3
"""Generate source-checked healthcare team-communication guides.

The manifest is an editorial allowlist. Content is generated only after its
source, safety, language, and discoverability attestations are explicitly set.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from site_map import build_sitemap  # noqa: E402


TEMPLATE_ROOT = TOOLS_ROOT / "team_communication_templates"
DEFAULT_MANIFEST = ROOT / "team-communication-pages.json"
SITE_ORIGIN = "https://bedsideenglish.github.io"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PLACEHOLDER_RE = re.compile(r"{{([A-Z0-9_]+)}}")
SBAR_STEPS = (("S", "Situation"), ("B", "Background"), ("A", "Assessment"), ("R", "Recommendation"))
US_STYLE_RULES = (
    (re.compile(r"\bpractis(?:e|ed|ing)\b", re.IGNORECASE), "use US `practice/practiced/practicing`"),
    (re.compile(r"\b(?:organisation|recognise|prioritise)\w*\b", re.IGNORECASE), "use US spelling"),
    (re.compile(r"\bwhilst\b", re.IGNORECASE), "use US `while`"),
)
OVERCLAIM_RULES = (
    (re.compile(r"\bguarantees?\b", re.IGNORECASE), "do not guarantee a clinical or safety outcome"),
    (re.compile(r"\bprevents? (?:all )?(?:errors|harm|miscommunication)\b", re.IGNORECASE), "avoid absolute safety claims"),
    (re.compile(r"\balways (?:safe|works)\b", re.IGNORECASE), "avoid universal safety claims"),
)


class GenerationError(RuntimeError):
    """The editorial manifest does not meet the publication contract."""


def escaped(value: Any) -> str:
    return html.escape(str(value), quote=True)


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def require_text(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GenerationError(f"{where}.{key} must be a non-empty string")
    return value.strip()


def require_text_list(data: dict[str, Any], key: str, where: str, minimum: int = 1) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or len(value) < minimum or any(not isinstance(item, str) or not item.strip() for item in value):
        raise GenerationError(f"{where}.{key} must contain at least {minimum} non-empty string(s)")
    return [item.strip() for item in value]


def exact_keys(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(data) - allowed
    missing = allowed - set(data)
    if unknown:
        raise GenerationError(f"{where} contains unsupported keys: {', '.join(sorted(unknown))}")
    if missing:
        raise GenerationError(f"{where} is missing keys: {', '.join(sorted(missing))}")


def render_template(path: Path, values: dict[str, str]) -> str:
    source = path.read_text(encoding="utf-8")
    expected = set(PLACEHOLDER_RE.findall(source))
    missing = expected - values.keys()
    if missing:
        raise GenerationError(f"Template values missing for {path.name}: {', '.join(sorted(missing))}")
    rendered = PLACEHOLDER_RE.sub(lambda match: values[match.group(1)], source)
    leftovers = PLACEHOLDER_RE.findall(rendered)
    if leftovers:
        raise GenerationError(f"Unresolved placeholders in {path.name}: {', '.join(sorted(set(leftovers)))}")
    return rendered.rstrip() + "\n"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GenerationError(f"Manifest not found: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"Invalid UTF-8 JSON in {path}: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"pages"} or not isinstance(value["pages"], list) or not value["pages"]:
        raise GenerationError(f"{path}: expected an object containing a non-empty `pages` list")
    return value


def all_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for child in value for text in all_text(child)]
    if isinstance(value, dict):
        return [text for child in value.values() for text in all_text(child)]
    return []


def validate_page(page: Any, where: str) -> dict[str, Any]:
    if not isinstance(page, dict):
        raise GenerationError(f"{where} must be an object")
    required = {
        "slug", "title", "h1", "meta_description", "lede", "category", "published_on", "reviewed_on",
        "search", "framework", "quick_answer", "scenario", "facts", "steps", "check_back", "checklist",
        "mistakes", "faq", "sources", "review",
    }
    exact_keys(page, required, where)

    for key in ("slug", "title", "h1", "meta_description", "lede", "category", "published_on", "reviewed_on", "quick_answer"):
        require_text(page, key, where)
    if not SLUG_RE.fullmatch(page["slug"]):
        raise GenerationError(f"{where}.slug must use lowercase letters, numbers, and single hyphens")
    for key in ("published_on", "reviewed_on"):
        try:
            date.fromisoformat(page[key])
        except ValueError as exc:
            raise GenerationError(f"{where}.{key} must use YYYY-MM-DD") from exc
    if date.fromisoformat(page["reviewed_on"]) < date.fromisoformat(page["published_on"]):
        raise GenerationError(f"{where}.reviewed_on cannot be earlier than published_on")
    if not 30 <= len(page["title"]) <= 70:
        raise GenerationError(f"{where}.title must be 30-70 characters")
    if not 110 <= len(page["meta_description"]) <= 170:
        raise GenerationError(f"{where}.meta_description must be 110-170 characters")
    if not 35 <= word_count(page["quick_answer"]) <= 90:
        raise GenerationError(f"{where}.quick_answer must be 35-90 words for a useful direct answer")

    search = page["search"]
    if not isinstance(search, dict):
        raise GenerationError(f"{where}.search must be an object")
    exact_keys(search, {"primary_query", "supporting_queries", "reader_task"}, f"{where}.search")
    primary_query = require_text(search, "primary_query", f"{where}.search").lower()
    require_text(search, "reader_task", f"{where}.search")
    require_text_list(search, "supporting_queries", f"{where}.search", 3)
    if primary_query not in f"{page['title']} {page['h1']}".lower():
        raise GenerationError(f"{where}: primary_query must appear naturally in the title or h1")

    framework = page["framework"]
    if not isinstance(framework, dict):
        raise GenerationError(f"{where}.framework must be an object")
    exact_keys(framework, {"name", "expanded", "definition", "use_when"}, f"{where}.framework")
    for key in ("name", "expanded", "definition", "use_when"):
        require_text(framework, key, f"{where}.framework")
    if framework["name"] != "SBAR" or framework["expanded"] != "Situation, Background, Assessment, Recommendation":
        raise GenerationError(f"{where}.framework must use the standard SBAR name and expansion")

    scenario = page["scenario"]
    if not isinstance(scenario, dict):
        raise GenerationError(f"{where}.scenario must be an object")
    exact_keys(scenario, {"setting", "caller", "receiver", "reason", "goal"}, f"{where}.scenario")
    for key in scenario:
        require_text(scenario, key, f"{where}.scenario")

    facts = page["facts"]
    if not isinstance(facts, list) or not 6 <= len(facts) <= 14:
        raise GenerationError(f"{where}.facts must contain 6-14 chart facts")
    fact_ids: set[str] = set()
    must_fact_ids: set[str] = set()
    for index, fact in enumerate(facts):
        fact_where = f"{where}.facts[{index}]"
        if not isinstance(fact, dict):
            raise GenerationError(f"{fact_where} must be an object")
        exact_keys(fact, {"id", "label", "value", "group", "priority"}, fact_where)
        for key in ("id", "label", "value", "group", "priority"):
            require_text(fact, key, fact_where)
        if not ID_RE.fullmatch(fact["id"]):
            raise GenerationError(f"{fact_where}.id must be lowercase snake_case")
        if fact["id"] in fact_ids:
            raise GenerationError(f"{fact_where}.id is duplicated")
        if fact["group"] not in {"Current concern", "Relevant background", "Safety and next steps"}:
            raise GenerationError(f"{fact_where}.group is not a supported chart group")
        if fact["priority"] not in {"must", "supporting"}:
            raise GenerationError(f"{fact_where}.priority must be `must` or `supporting`")
        fact_ids.add(fact["id"])
        if fact["priority"] == "must":
            must_fact_ids.add(fact["id"])

    steps = page["steps"]
    if not isinstance(steps, list) or len(steps) != 4:
        raise GenerationError(f"{where}.steps must contain exactly the four SBAR steps")
    referenced_facts: set[str] = set()
    for index, (step, expected) in enumerate(zip(steps, SBAR_STEPS)):
        step_where = f"{where}.steps[{index}]"
        if not isinstance(step, dict):
            raise GenerationError(f"{step_where} must be an object")
        exact_keys(step, {"letter", "name", "prompt", "statements", "why_it_works", "language_note"}, step_where)
        if (step.get("letter"), step.get("name")) != expected:
            raise GenerationError(f"{step_where} must be {expected[0]} = {expected[1]}")
        for key in ("prompt", "why_it_works"):
            require_text(step, key, step_where)
        statements = step["statements"]
        if not isinstance(statements, list) or not 1 <= len(statements) <= 4:
            raise GenerationError(f"{step_where}.statements must contain 1-4 statements")
        for statement_index, statement in enumerate(statements):
            statement_where = f"{step_where}.statements[{statement_index}]"
            if not isinstance(statement, dict):
                raise GenerationError(f"{statement_where} must be an object")
            exact_keys(statement, {"text", "fact_refs"}, statement_where)
            require_text(statement, "text", statement_where)
            refs = require_text_list(statement, "fact_refs", statement_where)
            unknown_refs = set(refs) - fact_ids
            if unknown_refs:
                raise GenerationError(f"{statement_where} references unknown facts: {', '.join(sorted(unknown_refs))}")
            referenced_facts.update(refs)
        note = step["language_note"]
        if not isinstance(note, dict):
            raise GenerationError(f"{step_where}.language_note must be an object")
        exact_keys(note, {"less_clear", "preferred", "reason"}, f"{step_where}.language_note")
        for key in note:
            require_text(note, key, f"{step_where}.language_note")
    missing_facts = must_fact_ids - referenced_facts
    if missing_facts:
        raise GenerationError(f"{where}: must-priority facts are absent from the spoken SBAR: {', '.join(sorted(missing_facts))}")

    check_back = page["check_back"]
    if not isinstance(check_back, dict):
        raise GenerationError(f"{where}.check_back must be an object")
    exact_keys(check_back, {"receiver", "sender", "why"}, f"{where}.check_back")
    for key in check_back:
        require_text(check_back, key, f"{where}.check_back")

    checklist = require_text_list(page, "checklist", where, 6)
    if len(checklist) > 10:
        raise GenerationError(f"{where}.checklist must contain no more than 10 items")
    mistakes = page["mistakes"]
    if not isinstance(mistakes, list) or len(mistakes) < 3:
        raise GenerationError(f"{where}.mistakes must contain at least 3 repairs")
    for index, mistake in enumerate(mistakes):
        mistake_where = f"{where}.mistakes[{index}]"
        if not isinstance(mistake, dict):
            raise GenerationError(f"{mistake_where} must be an object")
        exact_keys(mistake, {"problem", "repair"}, mistake_where)
        require_text(mistake, "problem", mistake_where)
        require_text(mistake, "repair", mistake_where)

    faq = page["faq"]
    if not isinstance(faq, list) or not 3 <= len(faq) <= 6:
        raise GenerationError(f"{where}.faq must contain 3-6 questions")
    for index, item in enumerate(faq):
        faq_where = f"{where}.faq[{index}]"
        if not isinstance(item, dict):
            raise GenerationError(f"{faq_where} must be an object")
        exact_keys(item, {"question", "answer"}, faq_where)
        require_text(item, "question", faq_where)
        answer = require_text(item, "answer", faq_where)
        if not 20 <= word_count(answer) <= 90:
            raise GenerationError(f"{faq_where}.answer must be 20-90 words")

    sources = page["sources"]
    if not isinstance(sources, list) or len(sources) < 2:
        raise GenerationError(f"{where}.sources must contain at least two primary or authoritative sources")
    for index, source in enumerate(sources):
        source_where = f"{where}.sources[{index}]"
        if not isinstance(source, dict):
            raise GenerationError(f"{source_where} must be an object")
        exact_keys(source, {"title", "organization", "url", "accessed_on"}, source_where)
        for key in source:
            require_text(source, key, source_where)
        parsed = urlsplit(source["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise GenerationError(f"{source_where}.url must be an absolute HTTPS URL")
        try:
            date.fromisoformat(source["accessed_on"])
        except ValueError as exc:
            raise GenerationError(f"{source_where}.accessed_on must use YYYY-MM-DD") from exc

    review = page["review"]
    if not isinstance(review, dict):
        raise GenerationError(f"{where}.review must be an object")
    exact_keys(
        review,
        {"source_claims_checked", "fictional_case_labeled", "local_policy_boundary_checked", "plain_language_checked", "search_intent_checked"},
        f"{where}.review",
    )
    incomplete = [key for key, value in review.items() if value is not True]
    if incomplete:
        raise GenerationError(f"{where}.review requires true attestations: {', '.join(sorted(incomplete))}")

    for label, text in enumerate(all_text(page)):
        for pattern, guidance in (*US_STYLE_RULES, *OVERCLAIM_RULES):
            if pattern.search(text):
                raise GenerationError(f"{where}.text[{label}]: {guidance}; found {pattern.pattern!r}")
    return page


def render_facts(facts: list[dict[str, str]]) -> str:
    groups = []
    for group_name in ("Current concern", "Relevant background", "Safety and next steps"):
        rows = []
        for fact in facts:
            if fact["group"] == group_name:
                priority = '<span class="priority-dot">Must say</span>' if fact["priority"] == "must" else ""
                rows.append(
                    f'<div><dt>{escaped(fact["label"])}</dt><dd>{escaped(fact["value"])} {priority}</dd></div>'
                )
        groups.append(f'<section class="chart-group"><h3>{escaped(group_name)}</h3><dl>{"".join(rows)}</dl></section>')
    return "\n              ".join(groups)


def render_steps(steps: list[dict[str, Any]]) -> str:
    cards = []
    for step in steps:
        statements = "".join(f'<p class="spoken">“{escaped(row["text"])}”</p>' for row in step["statements"])
        note = step["language_note"]
        cards.append(
            f'<article class="sbar-step" id="step-{step["letter"].lower()}">'
            f'<header><span aria-hidden="true">{step["letter"]}</span><div><p>{escaped(step["prompt"])}</p><h3>{escaped(step["name"])}</h3></div></header>'
            f'<div class="step-script">{statements}</div>'
            f'<p class="why"><strong>Why it works:</strong> {escaped(step["why_it_works"])}</p>'
            '<div class="language-contrast">'
            f'<div><small>Less clear</small><p>“{escaped(note["less_clear"])}”</p></div>'
            f'<div><small>Prefer</small><p>“{escaped(note["preferred"])}”</p></div>'
            f'<p>{escaped(note["reason"])}</p></div></article>'
        )
    return "\n            ".join(cards)


def render_full_message(steps: list[dict[str, Any]]) -> str:
    rows = []
    for step in steps:
        speech = " ".join(statement["text"] for statement in step["statements"])
        rows.append(
            f'<div class="transcript-row"><span>{step["letter"]} · {escaped(step["name"])}</span><p>{escaped(speech)}</p></div>'
        )
    return "\n              ".join(rows)


def structured_data(page: dict[str, Any], canonical_url: str) -> str:
    faq_entities = [
        {"@type": "Question", "name": item["question"], "acceptedAnswer": {"@type": "Answer", "text": item["answer"]}}
        for item in page["faq"]
    ]
    graph = [
        {
            "@type": ["Article", "LearningResource"],
            "@id": f"{canonical_url}#guide",
            "headline": page["h1"],
            "name": page["h1"],
            "description": page["meta_description"],
            "url": canonical_url,
            "datePublished": page["published_on"],
            "dateModified": page["reviewed_on"],
            "inLanguage": "en-US",
            "isAccessibleForFree": True,
            "learningResourceType": "Healthcare team communication guide",
            "teaches": page["framework"]["expanded"],
            "about": {"@type": "Thing", "name": page["framework"]["name"]},
            "audience": {"@type": "EducationalAudience", "educationalRole": "Healthcare professional or medical trainee"},
            "author": {"@type": "Organization", "name": "Bedside English", "url": f"{SITE_ORIGIN}/"},
            "publisher": {"@type": "Organization", "name": "Bedside English", "url": f"{SITE_ORIGIN}/"},
            "citation": [source["url"] for source in page["sources"]],
            "mainEntity": faq_entities,
            "isPartOf": {"@id": f"{SITE_ORIGIN}/communication/#library"},
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{canonical_url}#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_ORIGIN}/"},
                {"@type": "ListItem", "position": 2, "name": "Team communication", "item": f"{SITE_ORIGIN}/communication/"},
                {"@type": "ListItem", "position": 3, "name": page["framework"]["name"], "item": canonical_url},
            ],
        },
    ]
    payload = {"@context": "https://schema.org", "@graph": graph}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def build_page(page: dict[str, Any]) -> str:
    canonical_url = f"{SITE_ORIGIN}/communication/{page['slug']}/"
    scenario = page["scenario"]
    source_rows = "".join(
        f'<li><a href="{escaped(source["url"])}" target="_blank" rel="noopener noreferrer">{escaped(source["title"])}</a>'
        f'<span>{escaped(source["organization"])} · Accessed {escaped(source["accessed_on"])}</span></li>'
        for source in page["sources"]
    )
    checklist = "".join(f"<li>{escaped(item)}</li>" for item in page["checklist"])
    mistakes = "".join(
        f'<article><p class="mistake">{escaped(item["problem"])}</p><p class="repair"><strong>Repair:</strong> {escaped(item["repair"])}</p></article>'
        for item in page["mistakes"]
    )
    faq = "".join(
        f'<article><h3>{escaped(item["question"])}</h3><p>{escaped(item["answer"])}</p></article>' for item in page["faq"]
    )
    return render_template(
        TEMPLATE_ROOT / "page.html",
        {
            "PAGE_TITLE": escaped(page["title"]),
            "META_DESCRIPTION": escaped(page["meta_description"]),
            "CANONICAL_URL": escaped(canonical_url),
            "OG_IMAGE_URL": escaped(f"{SITE_ORIGIN}/assets/social/team-communication-og.png"),
            "STRUCTURED_DATA": structured_data(page, canonical_url),
            "SLUG": escaped(page["slug"]),
            "H1": escaped(page["h1"]),
            "LEDE": escaped(page["lede"]),
            "CATEGORY": escaped(page["category"]),
            "QUICK_ANSWER": escaped(page["quick_answer"]),
            "FRAMEWORK_EXPANDED": escaped(page["framework"]["expanded"]),
            "FRAMEWORK_DEFINITION": escaped(page["framework"]["definition"]),
            "FRAMEWORK_USE_WHEN": escaped(page["framework"]["use_when"]),
            "SETTING": escaped(scenario["setting"]),
            "CALLER": escaped(scenario["caller"]),
            "RECEIVER": escaped(scenario["receiver"]),
            "REASON": escaped(scenario["reason"]),
            "GOAL": escaped(scenario["goal"]),
            "FACT_GROUPS": render_facts(page["facts"]),
            "SBAR_STEPS": render_steps(page["steps"]),
            "FULL_MESSAGE": render_full_message(page["steps"]),
            "CHECK_BACK_RECEIVER": escaped(page["check_back"]["receiver"]),
            "CHECK_BACK_SENDER": escaped(page["check_back"]["sender"]),
            "CHECK_BACK_WHY": escaped(page["check_back"]["why"]),
            "CHECKLIST_ITEMS": checklist,
            "MISTAKE_CARDS": mistakes,
            "FAQ_ITEMS": faq,
            "SOURCE_ITEMS": source_rows,
            "PUBLISHED_ON": escaped(page["published_on"]),
            "REVIEWED_ON": escaped(page["reviewed_on"]),
            "REVIEWED_DISPLAY": escaped(date.fromisoformat(page["reviewed_on"]).strftime("%B %-d, %Y") if sys.platform != "win32" else date.fromisoformat(page["reviewed_on"]).strftime("%B %#d, %Y")),
        },
    )


def build_hub(pages: list[dict[str, Any]]) -> str:
    cards = []
    for index, page in enumerate(sorted(pages, key=lambda item: item["h1"].lower()), start=1):
        cards.append(
            f'<a class="guide-card" href="{escaped(page["slug"])}/">'
            f'<span class="card-meta">{escaped(page["category"])} · GUIDE {index:02d}</span>'
            f'<h2>{escaped(page["h1"])}</h2><p>{escaped(page["meta_description"])}</p>'
            '<span class="card-link">Read the worked example <span aria-hidden="true">→</span></span></a>'
        )
    return render_template(
        TEMPLATE_ROOT / "index.html",
        {
            "HUB_URL": escaped(f"{SITE_ORIGIN}/communication/"),
            "OG_IMAGE_URL": escaped(f"{SITE_ORIGIN}/assets/social/team-communication-og.png"),
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


def generate(
    pages: list[dict[str, Any]],
    output_root: Path,
    check: bool,
    selected_slugs: set[str] | None = None,
) -> int:
    validated = [validate_page(page, f"pages[{index}]") for index, page in enumerate(pages)]
    slugs = [page["slug"] for page in validated]
    if len(slugs) != len(set(slugs)):
        raise GenerationError("Manifest contains duplicate slugs")
    communication_root = output_root / "communication"
    actual = {path.parent.name for path in communication_root.glob("*/index.html")}
    unexpected = actual - set(slugs)
    if unexpected:
        raise GenerationError(f"Generated directories are not in the manifest: {', '.join(sorted(unexpected))}")
    selected = [page for page in validated if selected_slugs is None or page["slug"] in selected_slugs]

    mismatches: list[Path] = []
    for page in selected:
        write_or_check(communication_root / page["slug"] / "index.html", build_page(page), check, mismatches)
    write_or_check(communication_root / "index.html", build_hub(validated), check, mismatches)
    write_or_check(output_root / "sitemap.xml", build_sitemap(output_root), check, mismatches)
    if mismatches:
        print("Generated team-communication output is out of date:", file=sys.stderr)
        for path in mismatches:
            print(f"  {path}", file=sys.stderr)
        return 1
    verb = "Verified" if check else "Generated"
    print(f"{verb} {len(selected)} team-communication page(s).")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--page", action="append", default=[], help="generate only a manifest slug; may be repeated")
    parser.add_argument("--output-root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help="verify generated files without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        pages = load_manifest(args.manifest.resolve())["pages"]
        selected_slugs: set[str] | None = None
        if args.page:
            selected_slugs = set(args.page)
            missing = selected_slugs - {page.get("slug") for page in pages if isinstance(page, dict)}
            if missing:
                raise GenerationError(f"Unknown manifest slug(s): {', '.join(sorted(missing))}")
        return generate(pages, args.output_root.resolve(), args.check, selected_slugs)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
