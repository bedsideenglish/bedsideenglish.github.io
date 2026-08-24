#!/usr/bin/env python3
"""Generate reviewed everyday-English listening guides from app drills.

The public manifest is an editorial allowlist. The listening transcript,
detail labels, accepted answers, receptive tags, and permitted voice profiles
come from the Android app's reviewed Listening Lab data at generation time.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from site_map import build_sitemap  # noqa: E402


TEMPLATE_ROOT = TOOLS_ROOT / "everyday_english_templates"
DEFAULT_MANIFEST = ROOT / "everyday-english-pages.json"
DEFAULT_DRILL_DATA = ROOT / "everyday-listening-drills.json"
DEFAULT_APP_DRILL_DATA = ROOT.parent / "Medvoicetrainer-android-app-version" / "data" / "listening_drills.json"
SITE_ORIGIN = "https://bedsideenglish.github.io"
SOCIAL_IMAGE = f"{SITE_ORIGIN}/assets/social/everyday-listening-og.png"
PLACEHOLDER_RE = re.compile(r"{{([A-Z0-9_]+)}}")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
US_STYLE_RULES = (
    (re.compile(r"\bpractis(?:e|ed|ing)\b", re.IGNORECASE), "use US practice/practiced/practicing"),
    (re.compile(r"\b(?:organisation|recognise|prioritise)\w*\b", re.IGNORECASE), "use US spelling"),
    (re.compile(r"\bwhilst\b", re.IGNORECASE), "use US while"),
)


class GenerationError(RuntimeError):
    """The manifest or source drill does not meet the publication contract."""


def escaped(value: Any) -> str:
    return html.escape(str(value), quote=True)


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def exact_keys(value: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown:
        raise GenerationError(f"{where} contains unsupported keys: {', '.join(sorted(unknown))}")
    if missing:
        raise GenerationError(f"{where} is missing keys: {', '.join(sorted(missing))}")


def require_text(value: dict[str, Any], key: str, where: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise GenerationError(f"{where}.{key} must be a non-empty string")
    return item.strip()


def require_text_list(value: dict[str, Any], key: str, where: str, minimum: int = 1) -> list[str]:
    items = value.get(key)
    if not isinstance(items, list) or len(items) < minimum or any(not isinstance(item, str) or not item.strip() for item in items):
        raise GenerationError(f"{where}.{key} must contain at least {minimum} non-empty strings")
    return [item.strip() for item in items]


def all_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for child in value for text in all_text(child)]
    if isinstance(value, dict):
        return [text for child in value.values() for text in all_text(child)]
    return []


def render_template(path: Path, values: dict[str, str]) -> str:
    source = path.read_text(encoding="utf-8")
    expected = set(PLACEHOLDER_RE.findall(source))
    missing = expected - values.keys()
    if missing:
        raise GenerationError(f"Template values missing for {path.name}: {', '.join(sorted(missing))}")
    rendered = PLACEHOLDER_RE.sub(lambda match: values[match.group(1)], source)
    leftovers = PLACEHOLDER_RE.findall(rendered)
    if leftovers:
        raise GenerationError(f"Unresolved markers in {path.name}: {', '.join(sorted(set(leftovers)))}")
    return rendered.rstrip() + "\n"


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GenerationError(f"{label} not found: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"Invalid UTF-8 JSON in {path}: {exc}") from exc


def validate_profiles(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) < 10:
        raise GenerationError("speaker_profiles must contain at least 10 reviewed profiles")
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, profile in enumerate(raw):
        where = f"speaker_profiles[{index}]"
        if not isinstance(profile, dict):
            raise GenerationError(f"{where} must be an object")
        exact_keys(profile, {"id", "label", "lang_candidates", "tts_prompt"}, where)
        profile_id = require_text(profile, "id", where)
        require_text(profile, "label", where)
        require_text(profile, "tts_prompt", where)
        require_text_list(profile, "lang_candidates", where)
        if not ID_RE.fullmatch(profile_id):
            raise GenerationError(f"{where}.id must be lowercase snake_case")
        if profile_id in seen:
            raise GenerationError(f"{where}.id is duplicated")
        for lang in profile["lang_candidates"]:
            if not re.fullmatch(r"en-[A-Z]{2}", lang):
                raise GenerationError(f"{where}.lang_candidates must use English BCP-47 region tags")
        seen.add(profile_id)
        profiles.append(profile)
    return profiles


def validate_list_of_objects(
    page: dict[str, Any], key: str, fields: set[str], where: str, minimum: int, maximum: int | None = None
) -> list[dict[str, str]]:
    items = page.get(key)
    if not isinstance(items, list) or len(items) < minimum or (maximum is not None and len(items) > maximum):
        cap = f"-{maximum}" if maximum is not None else "+"
        raise GenerationError(f"{where}.{key} must contain {minimum}{cap} items")
    checked: list[dict[str, str]] = []
    for index, item in enumerate(items):
        item_where = f"{where}.{key}[{index}]"
        if not isinstance(item, dict):
            raise GenerationError(f"{item_where} must be an object")
        exact_keys(item, fields, item_where)
        for field in fields:
            require_text(item, field, item_where)
        checked.append(item)
    return checked


def validate_page(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise GenerationError(f"{where} must be an object")
    required = {
        "slug", "source_drill_id", "title", "h1", "meta_description", "lede", "category",
        "published_on", "reviewed_on", "search", "quick_answer", "practice_intro",
        "response_ladder", "decision_map", "dialogue", "mistakes", "transfer_prompts", "faq", "review",
    }
    exact_keys(raw, required, where)
    for key in ("slug", "source_drill_id", "title", "h1", "meta_description", "lede", "category", "published_on", "reviewed_on", "quick_answer", "practice_intro"):
        require_text(raw, key, where)
    if not SLUG_RE.fullmatch(raw["slug"]):
        raise GenerationError(f"{where}.slug must use lowercase letters, numbers, and single hyphens")
    if not ID_RE.fullmatch(raw["source_drill_id"]):
        raise GenerationError(f"{where}.source_drill_id must be lowercase snake_case")
    for key in ("published_on", "reviewed_on"):
        try:
            date.fromisoformat(raw[key])
        except ValueError as exc:
            raise GenerationError(f"{where}.{key} must use YYYY-MM-DD") from exc
    if date.fromisoformat(raw["reviewed_on"]) < date.fromisoformat(raw["published_on"]):
        raise GenerationError(f"{where}.reviewed_on cannot be earlier than published_on")
    if not 30 <= len(raw["title"]) <= 70:
        raise GenerationError(f"{where}.title must be 30-70 characters")
    if not 110 <= len(raw["meta_description"]) <= 170:
        raise GenerationError(f"{where}.meta_description must be 110-170 characters")
    if not 45 <= word_count(raw["quick_answer"]) <= 95:
        raise GenerationError(f"{where}.quick_answer must be 45-95 words")

    search = raw["search"]
    if not isinstance(search, dict):
        raise GenerationError(f"{where}.search must be an object")
    exact_keys(search, {"primary_query", "supporting_queries", "reader_task"}, f"{where}.search")
    primary_query = require_text(search, "primary_query", f"{where}.search").lower()
    require_text(search, "reader_task", f"{where}.search")
    require_text_list(search, "supporting_queries", f"{where}.search", 3)
    if primary_query not in f"{raw['title']} {raw['h1']}".lower():
        raise GenerationError(f"{where}: primary_query must appear naturally in the title or h1")

    validate_list_of_objects(raw, "response_ladder", {"label", "when", "phrase", "why"}, where, 3, 4)
    validate_list_of_objects(raw, "decision_map", {"signal", "move", "example"}, where, 4, 6)
    validate_list_of_objects(raw, "dialogue", {"speaker", "text", "note"}, where, 4, 8)
    validate_list_of_objects(raw, "mistakes", {"problem", "repair"}, where, 3, 6)
    validate_list_of_objects(raw, "transfer_prompts", {"setting", "heard", "say"}, where, 3, 5)
    validate_list_of_objects(raw, "faq", {"question", "answer"}, where, 3, 6)

    review = raw["review"]
    required_reviews = {
        "app_source_checked", "scoring_cases_checked", "transcript_hidden_until_commit",
        "us_english_read_aloud", "browser_tts_limit_disclosed", "search_task_satisfied",
    }
    if not isinstance(review, dict):
        raise GenerationError(f"{where}.review must be an object")
    exact_keys(review, required_reviews, f"{where}.review")
    unchecked = [key for key, value in review.items() if value is not True]
    if unchecked:
        raise GenerationError(f"{where}.review has unchecked attestations: {', '.join(unchecked)}")

    combined = "\n".join(all_text({key: value for key, value in raw.items() if key != "search"}))
    for pattern, message in US_STYLE_RULES:
        if pattern.search(combined):
            raise GenerationError(f"{where}: {message}")
    if re.search(r"\b(?:race|racial|ethnicity|ethnic)\b", combined, re.IGNORECASE):
        raise GenerationError(f"{where}: describe speech by accent/region or first-language influence, not race")
    return raw


def load_manifest(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = load_json(path, "Manifest")
    if not isinstance(data, dict):
        raise GenerationError("Manifest must be an object")
    exact_keys(data, {"speaker_profiles", "pages"}, "manifest")
    profiles = validate_profiles(data["speaker_profiles"])
    if not isinstance(data["pages"], list) or not data["pages"]:
        raise GenerationError("manifest.pages must be a non-empty list")
    pages = [validate_page(page, f"pages[{index}]") for index, page in enumerate(data["pages"])]
    slugs = [page["slug"] for page in pages]
    if len(slugs) != len(set(slugs)):
        raise GenerationError("Page slugs must be unique")
    source_ids = [page["source_drill_id"] for page in pages]
    if len(source_ids) != len(set(source_ids)):
        raise GenerationError("Each published page must use a distinct source drill")
    return profiles, pages


def load_drills(path: Path, profile_ids: set[str]) -> dict[str, dict[str, Any]]:
    data = load_json(path, "Listening Lab source")
    if not isinstance(data, dict) or not isinstance(data.get("drills"), list):
        raise GenerationError(f"{path}: expected an object with a drills list")
    drills: dict[str, dict[str, Any]] = {}
    for index, drill in enumerate(data["drills"]):
        where = f"drills[{index}]"
        if not isinstance(drill, dict):
            raise GenerationError(f"{where} must be an object")
        for key in ("id", "category", "difficulty", "context", "transcript", "details", "receptive_tags", "accent_candidates"):
            if key not in drill:
                raise GenerationError(f"{where} is missing {key}")
        drill_id = require_text(drill, "id", where)
        if drill_id in drills:
            raise GenerationError(f"Duplicate source drill id: {drill_id}")
        if not isinstance(drill["difficulty"], int) or not 1 <= drill["difficulty"] <= 4:
            raise GenerationError(f"{where}.difficulty must be 1-4")
        if not isinstance(drill["details"], list) or len(drill["details"]) < 2:
            raise GenerationError(f"{where}.details must contain at least two exact details")
        detail_keys: set[str] = set()
        for detail_index, detail in enumerate(drill["details"]):
            detail_where = f"{where}.details[{detail_index}]"
            if not isinstance(detail, dict):
                raise GenerationError(f"{detail_where} must be an object")
            for key in ("key", "label", "answers"):
                if key not in detail:
                    raise GenerationError(f"{detail_where} is missing {key}")
            detail_key = require_text(detail, "key", detail_where)
            require_text(detail, "label", detail_where)
            require_text_list(detail, "answers", detail_where)
            if detail_key in detail_keys:
                raise GenerationError(f"{detail_where}.key is duplicated")
            detail_keys.add(detail_key)
        candidates = require_text_list(drill, "accent_candidates", where)
        unknown = set(candidates) - profile_ids
        if unknown:
            raise GenerationError(f"{where} references unknown speaker profiles: {', '.join(sorted(unknown))}")
        drills[drill_id] = drill
    return drills


def source_hash(drill: dict[str, Any]) -> str:
    payload = json.dumps(drill, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def reviewed_audio_sources(drill_id: str, profiles: list[dict[str, Any]]) -> dict[str, str]:
    """Return committed audio assets only; browser TTS remains the fallback."""
    audio_root = ROOT / "assets" / "audio" / "everyday" / drill_id
    sources: dict[str, str] = {}
    for profile in profiles:
        for extension in ("mp3", "m4a", "wav", "ogg"):
            candidate = audio_root / f"{profile['id']}.{extension}"
            if candidate.is_file():
                sources[profile["id"]] = f"../../assets/audio/everyday/{drill_id}/{candidate.name}"
                break
    return sources


def render_page(page: dict[str, Any], drill: dict[str, Any], profiles: list[dict[str, Any]]) -> str:
    profile_by_id = {profile["id"]: profile for profile in profiles}
    selected_profiles = [profile_by_id[profile_id] for profile_id in drill["accent_candidates"]]
    profile_options = "".join(
        f'<option value="{escaped(profile["id"])}">{escaped(profile["label"])}</option>' for profile in selected_profiles
    )
    answer_fields = "".join(
        '<div class="answer-field">'
        f'<label class="field-label" for="answer-{escaped(detail["key"])}">{escaped(detail["label"])}</label>'
        f'<input id="answer-{escaped(detail["key"])}" name="{escaped(detail["key"])}" type="text" '
        'autocomplete="off" autocapitalize="off" spellcheck="false">'
        '<p class="field-feedback" hidden></p></div>'
        for detail in drill["details"]
    )
    response_ladder = "".join(
        '<article class="ladder-card">'
        f'<span class="step-number">{index}</span><h3>{escaped(item["label"])}</h3>'
        f'<p class="when">{escaped(item["when"])}</p><p class="phrase">“{escaped(item["phrase"])}”</p>'
        f'<p class="why">{escaped(item["why"])}</p></article>'
        for index, item in enumerate(page["response_ladder"], start=1)
    )
    decision_map = "".join(
        f'<li><strong>{escaped(item["signal"])}</strong><span>{escaped(item["move"])}</span><em>“{escaped(item["example"])}”</em></li>'
        for item in page["decision_map"]
    )
    dialogue = "".join(
        '<div class="turn">'
        f'<span class="turn-speaker">{escaped(item["speaker"])}</span><div><p>“{escaped(item["text"])}”</p><small>{escaped(item["note"])}</small></div>'
        '</div>'
        for item in page["dialogue"]
    )
    mistakes = "".join(
        f'<article class="mistake"><strong>{escaped(item["problem"])}</strong><p>{escaped(item["repair"])}</p></article>'
        for item in page["mistakes"]
    )
    transfer_prompts = "".join(
        '<article class="transfer-card">'
        f'<span class="setting">{escaped(item["setting"])}</span><h3>{escaped(item["heard"])}</h3>'
        f'<blockquote>“{escaped(item["say"])}”</blockquote></article>'
        for item in page["transfer_prompts"]
    )
    faq = "".join(
        f'<details><summary>{escaped(item["question"])}</summary><p>{escaped(item["answer"])}</p></details>'
        for item in page["faq"]
    )
    canonical = f"{SITE_ORIGIN}/everyday-english/{page['slug']}/"
    lab_config = {
        "version": 1,
        "drill": {
            "id": drill["id"],
            "category": drill["category"],
            "difficulty": drill["difficulty"],
            "transcript": drill["transcript"],
            "details": [
                {"key": detail["key"], "label": detail["label"], "answers": detail["answers"]}
                for detail in drill["details"]
            ],
            "receptive_tags": drill["receptive_tags"],
            "audio_sources": reviewed_audio_sources(drill["id"], selected_profiles),
        },
        "profiles": selected_profiles,
    }
    json_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": ["Article", "LearningResource"],
                "@id": canonical + "#guide",
                "url": canonical,
                "headline": page["h1"],
                "description": page["meta_description"],
                "datePublished": page["published_on"],
                "dateModified": page["reviewed_on"],
                "inLanguage": "en-US",
                "isAccessibleForFree": True,
                "learningResourceType": ["Interactive listening exercise", "Language guide"],
                "interactivityType": "mixed",
                "teaches": page["search"]["reader_task"],
                "author": {"@type": "Organization", "name": "Bedside English"},
                "publisher": {"@type": "Organization", "name": "Bedside English", "url": f"{SITE_ORIGIN}/"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_ORIGIN}/"},
                    {"@type": "ListItem", "position": 2, "name": "Everyday English", "item": f"{SITE_ORIGIN}/everyday-english/"},
                    {"@type": "ListItem", "position": 3, "name": page["h1"], "item": canonical},
                ],
            },
        ],
    }
    values = {
        "TITLE": escaped(page["title"]),
        "META_DESCRIPTION": escaped(page["meta_description"]),
        "CANONICAL": escaped(canonical),
        "SOCIAL_IMAGE": escaped(SOCIAL_IMAGE),
        "H1": escaped(page["h1"]),
        "BREADCRUMB": escaped(page["category"]),
        "CATEGORY": escaped(page["category"]),
        "LEDE": escaped(page["lede"]),
        "QUICK_ANSWER": escaped(page["quick_answer"]),
        "PRACTICE_INTRO": escaped(page["practice_intro"]),
        "DRILL_CONTEXT": escaped(drill["context"]),
        "DRILL_CATEGORY": escaped(drill["category"]),
        "DRILL_DIFFICULTY": str(drill["difficulty"]),
        "PROFILE_OPTIONS": profile_options,
        "ANSWER_FIELDS": answer_fields,
        "RESPONSE_LADDER": response_ladder,
        "DECISION_MAP": decision_map,
        "DIALOGUE": dialogue,
        "MISTAKES": mistakes,
        "TRANSFER_PROMPTS": transfer_prompts,
        "FAQ": faq,
        "LAB_CONFIG": json_script(lab_config),
        "JSON_LD": json_script(json_ld),
        "REVIEWED_ON": escaped(page["reviewed_on"]),
        "SOURCE_DRILL_ID": escaped(drill["id"]),
        "SOURCE_DRILL_SHA256": source_hash(drill),
    }
    return render_template(TEMPLATE_ROOT / "page.html", values)


def render_hub(pages: list[dict[str, Any]], drills: dict[str, dict[str, Any]]) -> str:
    cards = "".join(
        '<a class="guide-card" href="' + escaped(page["slug"]) + '/">'
        '<div class="card-meta"><span>' + escaped(page["category"]) + '</span><span>Level ' + str(drills[page["source_drill_id"]]["difficulty"]) + '</span></div>'
        '<h2>' + escaped(page["h1"]) + '</h2><p>' + escaped(page["lede"]) + '</p>'
        '<span class="card-action">Listen and check your answer →</span></a>'
        for page in pages
    )
    canonical = f"{SITE_ORIGIN}/everyday-english/"
    json_ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": canonical + "#collection",
                "url": canonical,
                "name": "Everyday English Listening Practice",
                "description": "Interactive everyday English listening guides with commit-before-reveal scoring and conversation repair practice.",
                "inLanguage": "en-US",
                "isPartOf": {"@type": "WebSite", "name": "Bedside English", "url": f"{SITE_ORIGIN}/"},
            },
            {
                "@type": "ItemList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": index,
                        "name": page["h1"],
                        "url": f"{canonical}{page['slug']}/",
                    }
                    for index, page in enumerate(pages, start=1)
                ],
            },
        ],
    }
    return render_template(TEMPLATE_ROOT / "index.html", {"GUIDE_CARDS": cards, "JSON_LD": json_script(json_ld)})


def write_or_check(path: Path, content: str, check: bool) -> bool:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            print(f"STALE {path.relative_to(ROOT)}")
            return False
        print(f"OK    {path.relative_to(ROOT)}")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"WROTE {path.relative_to(ROOT)}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-data", type=Path, default=DEFAULT_DRILL_DATA)
    parser.add_argument("--app-source-data", type=Path, default=DEFAULT_APP_DRILL_DATA, help="When present, require every published snapshot to equal the current app drill")
    parser.add_argument("--page", help="Generate/check one reviewed slug plus the hub and sitemap")
    parser.add_argument("--check", action="store_true", help="Fail if generated output is stale")
    args = parser.parse_args(argv)

    try:
        profiles, pages = load_manifest(args.manifest)
        drills = load_drills(args.source_data, {profile["id"] for profile in profiles})
        missing = [page["source_drill_id"] for page in pages if page["source_drill_id"] not in drills]
        if missing:
            raise GenerationError(f"Manifest references missing app drills: {', '.join(missing)}")
        if args.app_source_data.is_file():
            app_drills = load_drills(args.app_source_data, {profile["id"] for profile in profiles})
            for page in pages:
                drill_id = page["source_drill_id"]
                if drill_id not in app_drills:
                    raise GenerationError(f"Published snapshot {drill_id} is absent from the current app source")
                if drills[drill_id] != app_drills[drill_id]:
                    raise GenerationError(f"Published snapshot {drill_id} differs from the current app source; review and refresh it")
        selected = pages
        if args.page:
            selected = [page for page in pages if page["slug"] == args.page]
            if not selected:
                raise GenerationError(f"Unknown reviewed page slug: {args.page}")

        ok = True
        for page in selected:
            output = ROOT / "everyday-english" / page["slug"] / "index.html"
            ok = write_or_check(output, render_page(page, drills[page["source_drill_id"]], profiles), args.check) and ok
        ok = write_or_check(ROOT / "everyday-english" / "index.html", render_hub(pages, drills), args.check) and ok
        sitemap = build_sitemap(ROOT)
        ok = write_or_check(ROOT / "sitemap.xml", sitemap, args.check) and ok
        return 0 if ok else 1
    except GenerationError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
