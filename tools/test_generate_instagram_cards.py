#!/usr/bin/env python3
"""Regression tests for the Instagram card generator.

The tests that matter here are the ones that prove a card cannot say something
the site has not published: source fidelity, the drift fingerprint, and the
refusal to invent clinical wording in the card manifest.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


def _load(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = _load("instagram_generator", "generate-instagram-cards.py")

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "instagram-cards.json"
GUIDES = ROOT / "team-communication-pages.json"


class InstagramCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(CARDS.read_text(encoding="utf-8"))
        cls.pages = {p["slug"]: p for p in json.loads(GUIDES.read_text(encoding="utf-8"))["pages"]}
        cls.card = cls.manifest["cards"][0]

    def card_copy(self) -> dict:
        return copy.deepcopy(self.card)

    def validate(self, card: dict):
        return generator.validate_card(card, 0, self.pages)

    # ---- the shipped card ------------------------------------------------

    def test_shipped_card_validates(self) -> None:
        self.assertEqual(self.validate(self.card_copy())["slug"], "sbar-nursing-handoff")

    def test_carousel_shape_is_hook_contrasts_script_cta(self) -> None:
        card = self.card_copy()
        slides = generator.build_slides(card, self.pages[card["source_page"]])
        self.assertEqual(
            [slide["kind"] for slide in slides],
            ["hook"] + ["contrast"] * len(card["contrast_steps"]) + ["script", "cta"],
        )
        # Instagram accepts at most 10 items in a carousel.
        self.assertLessEqual(len(slides), 10)

    def test_generation_is_deterministic_and_fully_substituted(self) -> None:
        card = self.card_copy()
        page = self.pages[card["source_page"]]
        first = generator.build_documents(card, page)
        second = generator.build_documents(card, page)
        self.assertEqual([d["html"] for d in first], [d["html"] for d in second])
        for document in first:
            self.assertNotIn("{{", document["html"])

    # ---- source fidelity -------------------------------------------------

    def test_every_clinical_sentence_comes_from_the_guide(self) -> None:
        card = self.card_copy()
        page = self.pages[card["source_page"]]
        html = "\n".join(d["html"] for d in generator.build_documents(card, page))
        for position in card["contrast_steps"]:
            note = page["steps"][position]["language_note"]
            for key in ("less_clear", "preferred", "reason"):
                self.assertIn(generator.esc(note[key]), html, f"{key} of step {position} is missing")

    def test_editing_the_guide_changes_the_fingerprint(self) -> None:
        page = copy.deepcopy(self.pages[self.card["source_page"]])
        before = generator.page_fingerprint(page)
        page["steps"][0]["language_note"]["preferred"] = "His oxygen saturation has fallen."
        self.assertNotEqual(before, generator.page_fingerprint(page))

    def test_html_is_escaped(self) -> None:
        card = self.card_copy()
        page = copy.deepcopy(self.pages[card["source_page"]])
        page["steps"][0]["language_note"]["less_clear"] = 'He is <b>"unwell"</b> & pale.'
        html = "\n".join(d["html"] for d in generator.build_documents(card, page))
        self.assertIn("&lt;b&gt;&quot;unwell&quot;&lt;/b&gt; &amp; pale.", html)
        self.assertNotIn("<b>", html)

    def test_straight_apostrophes_are_set_typographically(self) -> None:
        self.assertEqual(generator.esc("doesn't"), "doesn’t")

    # ---- the card manifest cannot smuggle in clinical wording ------------

    def test_unknown_source_page_is_rejected(self) -> None:
        card = self.card_copy()
        card["source_page"] = "a-guide-that-was-never-published"
        with self.assertRaisesRegex(generator.ManifestError, "not a published guide"):
            self.validate(card)

    def test_step_without_a_language_note_is_rejected(self) -> None:
        card = self.card_copy()
        pages = copy.deepcopy(self.pages)
        del pages[card["source_page"]]["steps"][1]["language_note"]
        with self.assertRaisesRegex(generator.ManifestError, "no language_note"):
            generator.validate_card(card, 0, pages)

    def test_step_outside_the_guide_is_rejected(self) -> None:
        card = self.card_copy()
        card["contrast_steps"] = [0, 99]
        with self.assertRaisesRegex(generator.ManifestError, "not a step index"):
            self.validate(card)

    def test_repeated_step_is_rejected(self) -> None:
        card = self.card_copy()
        card["contrast_steps"] = [0, 0]
        with self.assertRaisesRegex(generator.ManifestError, "repeats a step"):
            self.validate(card)

    def test_unreviewed_card_is_rejected(self) -> None:
        card = self.card_copy()
        card["review"]["clinical_text_is_source_verbatim"] = False
        with self.assertRaisesRegex(generator.ManifestError, "clinical_text_is_source_verbatim"):
            self.validate(card)

    def test_unexpected_key_is_rejected(self) -> None:
        card = self.card_copy()
        card["overlay_text"] = "Anything at all"
        with self.assertRaisesRegex(generator.ManifestError, "unexpected key"):
            self.validate(card)

    # ---- the text budget -------------------------------------------------

    def test_long_headline_line_is_rejected(self) -> None:
        card = self.card_copy()
        card["hook"]["headline"][0]["text"] = "Your clinical English is really quite fine"
        with self.assertRaisesRegex(generator.ManifestError, "exceeds the .* budget"):
            self.validate(card)

    def test_too_many_headline_lines_are_rejected(self) -> None:
        card = self.card_copy()
        card["hook"]["headline"] = [{"text": "Line", "tone": "base"}] * 5
        with self.assertRaisesRegex(generator.ManifestError, "exceeds the .*-line limit"):
            self.validate(card)

    def test_long_source_quote_is_rejected(self) -> None:
        card = self.card_copy()
        pages = copy.deepcopy(self.pages)
        note = pages[card["source_page"]]["steps"][0]["language_note"]
        note["preferred"] = "His oxygen saturation has fallen to 88% on room air, " + "and so on, " * 10
        with self.assertRaisesRegex(generator.ManifestError, "exceeds the .* budget"):
            generator.validate_card(card, 0, pages)

    def test_overlong_caption_is_rejected(self) -> None:
        card = self.card_copy()
        card["caption"] = ["word " * 60] * 4
        with self.assertRaisesRegex(generator.ManifestError, "caption"):
            self.validate(card)

    def test_hashtag_must_be_bare_and_lowercase(self) -> None:
        card = self.card_copy()
        card["hashtags"][0] = "#ClinicalEnglish"
        with self.assertRaisesRegex(generator.ManifestError, "lowercase alphanumeric"):
            self.validate(card)

    def test_unknown_tone_is_rejected(self) -> None:
        card = self.card_copy()
        card["hook"]["headline"][0]["tone"] = "shout"
        with self.assertRaisesRegex(generator.ManifestError, "tone"):
            self.validate(card)


if __name__ == "__main__":
    unittest.main()
