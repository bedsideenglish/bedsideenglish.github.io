#!/usr/bin/env python3
"""Keep the two Android landing-page routes identical where intended."""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android.html"
INDEX = ROOT / "index.html"

# android.html is the structural source. The root route keeps its established
# broader two-track problem statement in addition to route-specific URLs.
ROOT_ROUTE_REPLACEMENTS = {
    'content="https://bedsideenglish.github.io/android.html"': 'content="https://bedsideenglish.github.io/"',
    'href="https://bedsideenglish.github.io/android.html"': 'href="https://bedsideenglish.github.io/"',
    'class="brand" href="android.html"': 'class="brand" href="./"',
    '.quote{max-width:20ch;margin:0;font-size:clamp(2.8rem,5.5vw,5.5rem);line-height:0.96}\n'
    '    .quote em{display:block;color:var(--color-accent-2);font-style:normal}':
        '.quote{max-width:18ch;margin:0;font-size:clamp(2.8rem,6.2vw,6rem);line-height:0.96}\n'
        '    .quote em{color:var(--color-accent-2);font-style:normal}',
    '<!-- The shared problem behind both tracks: learners often know the English,\n'
    '       but cannot retrieve it quickly enough to answer aloud. -->':
        '<!-- The shared problem behind both tracks: real conversations change before\n'
        '       a learner has time to translate a rehearsed sentence. -->',
    '<p class="quote" data-i18n="problem_quote">You know the words.<em>They just don’t come when you need them.</em></p>\n'
    '      <p class="problem-after" data-i18n="problem_after">Practice answering out loud before you translate—in clinical encounters and everyday situations.</p>':
        '<p class="quote" data-i18n="problem_quote">English does not stop at the bedside. It follows you into the hallway, onto the phone, and <em>out into everyday life.</em></p>\n'
        '      <p class="problem-after" data-i18n="problem_after">The skill is the same: understand what changed, answer out loud, and keep the conversation moving before you have time to translate.</p>',
    'problem_quote:"영어를 모르는 게 아닙니다.<em>필요한 순간에 나오지 않는 게 문제입니다.</em>",\n'
    '    problem_after:"머릿속으로 번역하기 전에 소리 내어 답하는 연습. 진료 대화와 일상 상황 모두에서 반복합니다.",':
        'problem_quote:"영어는 진료실에서 끝나지 않습니다. 병원 복도와 전화, 그리고 <em>그 밖의 일상까지</em> 따라옵니다.",\n'
        '    problem_after:"필요한 능력은 하나입니다. 달라진 상황을 알아듣고, 번역할 틈 없이 소리 내어 답하며, 대화를 계속 이어가는 것.",',
}


def expected_index() -> str:
    content = ANDROID.read_text(encoding="utf-8")
    for source, replacement in ROOT_ROUTE_REPLACEMENTS.items():
        if source not in content:
            raise RuntimeError(f"Expected Android-page value not found: {source}")
        content = content.replace(source, replacement)
    return content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite index.html from android.html, preserving root-route values",
    )
    args = parser.parse_args()

    expected = expected_index()
    actual = INDEX.read_text(encoding="utf-8")

    if args.write:
        if actual != expected:
            INDEX.write_text(expected, encoding="utf-8", newline="\n")
            print("Updated index.html from android.html.")
        else:
            print("index.html is already synchronized.")
        return 0

    if actual == expected:
        print("index.html and android.html are synchronized.")
        return 0

    print("index.html is out of sync with android.html. Run:")
    print("  python tools/sync-landing-pages.py --write")
    print("\n".join(difflib.unified_diff(
        actual.splitlines(), expected.splitlines(),
        fromfile="index.html", tofile="expected index.html", lineterm="",
    )))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
