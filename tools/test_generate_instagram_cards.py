#!/usr/bin/env python3
"""Regression tests for the Instagram card generator.

The tests that matter here are the ones that prove a card cannot say something
the site has not published: source fidelity across every library, the drift
fingerprint, and the refusal to let clinical wording into the card manifest.
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


class InstagramCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(CARDS.read_text(encoding="utf-8"))
        cls.pages_by_library = {name: generator.library_pages(name) for name in generator.LIBRARIES}
        cls.cards = {card["slug"]: card for card in cls.manifest["cards"]}

    def card(self, slug: str) -> dict:
        return copy.deepcopy(self.cards[slug])

    def pages(self, card: dict) -> dict:
        return self.pages_by_library[card["library"]]

    def validate(self, card: dict):
        return generator.validate_card(card, 0, self.pages_by_library)

    def html_of(self, card: dict) -> str:
        return "\n".join(d["html"] for d in generator.build_documents(card, self.pages(card)))

    # ---- the shipped cards ----------------------------------------------

    def test_every_shipped_card_validates(self) -> None:
        for index, card in enumerate(self.manifest["cards"]):
            with self.subTest(card=card["slug"]):
                self.assertEqual(generator.validate_card(copy.deepcopy(card), index, self.pages_by_library)["slug"],
                                 card["slug"])

    def test_all_three_libraries_are_exercised(self) -> None:
        self.assertEqual(
            {card["library"] for card in self.manifest["cards"]},
            set(generator.LIBRARIES),
        )

    def test_carousel_shape_and_length(self) -> None:
        for card in self.manifest["cards"]:
            with self.subTest(card=card["slug"]):
                slides = generator.build_slides(copy.deepcopy(card), self.pages(card))
                kinds = [slide["kind"] for slide in slides]
                self.assertEqual(kinds[0], "hook")
                self.assertEqual(kinds[-2:], ["script", "cta"])
                self.assertLessEqual(len(slides), generator.MAX_SLIDES)

    def test_generation_is_deterministic_and_fully_substituted(self) -> None:
        for card in self.manifest["cards"]:
            with self.subTest(card=card["slug"]):
                pages = self.pages(card)
                first = generator.build_documents(copy.deepcopy(card), pages)
                second = generator.build_documents(copy.deepcopy(card), pages)
                self.assertEqual([d["html"] for d in first], [d["html"] for d in second])
                for document in first:
                    self.assertNotIn("{{", document["html"])

    # ---- source fidelity -------------------------------------------------

    def test_every_clinical_sentence_comes_from_a_guide(self) -> None:
        for card in self.manifest["cards"]:
            with self.subTest(card=card["slug"]):
                html = self.html_of(copy.deepcopy(card))
                for item in generator.card_items(copy.deepcopy(card), self.pages(card)):
                    for key in ("top_text", "bottom_text", "reason"):
                        if item[key]:
                            self.assertIn(generator.esc(item[key]), html, f"{key} missing from {card['slug']}")

    def test_hook_hero_is_source_text(self) -> None:
        """The first slide is inside the editorial gate, not marketing outside it."""
        for card in self.manifest["cards"]:
            with self.subTest(card=card["slug"]):
                hook = card["hook"]
                pages = self.pages(card)
                hero = generator.LIBRARIES[card["library"]]["hero"](
                    pages[hook["source"]["page"]], hook["source"]["index"], "hook"
                )
                slides = generator.build_slides(copy.deepcopy(card), pages)
                self.assertIn(generator.esc(hero), slides[0]["html"])

    def test_editing_a_guide_changes_the_fingerprint(self) -> None:
        page = copy.deepcopy(self.pages_by_library["team-communication"]["sbar-nursing-handoff-example"])
        before = generator.page_fingerprint(page)
        page["steps"][0]["language_note"]["preferred"] = "His oxygen saturation has fallen."
        self.assertNotEqual(before, generator.page_fingerprint(page))

    def test_compiled_card_records_every_guide_it_cuts_from(self) -> None:
        card = self.card("words-your-patient-does-not-have")
        referenced = generator.referenced_pages(card)
        self.assertGreater(len(referenced), 1, "the learning card should compile across guides")
        self.assertEqual(referenced, sorted({card["hook"]["source"]["page"], *(i["page"] for i in card["items"])}))

    def test_html_is_escaped(self) -> None:
        card = self.card("sbar-nursing-handoff")
        pages = copy.deepcopy(self.pages(card))
        pages["sbar-nursing-handoff-example"]["steps"][0]["language_note"]["less_clear"] = 'He is <b>"unwell"</b> & pale.'
        html = "\n".join(d["html"] for d in generator.build_documents(card, pages))
        self.assertIn("&lt;b&gt;&quot;unwell&quot;&lt;/b&gt; &amp; pale.", html)
        self.assertNotIn("<b>", html)

    def test_straight_apostrophes_are_set_typographically(self) -> None:
        self.assertEqual(generator.esc("doesn't"), "doesn’t")

    # ---- library adapters ------------------------------------------------

    def test_team_communication_slides_are_marked_contrasts(self) -> None:
        card = self.card("sbar-nursing-handoff")
        items = generator.card_items(card, self.pages(card))
        self.assertTrue(all(item["tone"] == "error" for item in items))
        self.assertTrue(all(item["top_label"] == "&#10007;" for item in items))

    def test_learning_slides_use_the_guides_own_labels(self) -> None:
        """The guides present options, not errors, so no slide may mark one wrong."""
        card = self.card("words-your-patient-does-not-have")
        items = generator.card_items(card, self.pages(card))
        self.assertTrue(all(item["tone"] == "option" for item in items))
        for item in items:
            self.assertNotIn("10007", item["top_label"])
            self.assertNotIn("10003", item["bottom_label"])
        html = self.html_of(card)
        self.assertNotIn("&#10007;", html)

    def test_learning_item_needs_two_alternatives(self) -> None:
        card = self.card("words-your-patient-does-not-have")
        pages = copy.deepcopy(self.pages(card))
        pages["chest-pain-history-questions"]["question_edits"][0]["alternatives"] = [{"label": "One", "phrase": "Only one"}]
        with self.assertRaisesRegex(generator.ManifestError, "fewer than two labelled alternatives"):
            generator.validate_card(card, 0, {**self.pages_by_library, "learning": pages})

    def test_model_interview_slide_pairs_a_question_with_its_answer(self) -> None:
        card = self.card("chest-pain-first-questions")
        pages = self.pages(card)
        items = generator.card_items(card, pages)
        turns = pages["chest-pain-focused-history"]["turns"]
        for item, ref in zip(items, card["items"]):
            self.assertEqual(item["tone"], "ask")
            self.assertEqual(item["bottom_text"], turns[ref["index"]["turn"]]["text"])
            self.assertEqual(item["top_text"], turns[ref["index"]["turn"] + 1]["text"])

    def test_model_interview_rejects_a_patient_turn(self) -> None:
        card = self.card("chest-pain-first-questions")
        card["items"][0]["index"] = {"turn": 3, "flow": 1}
        with self.assertRaisesRegex(generator.ManifestError, "spoken by the patient"):
            self.validate(card)

    def test_model_interview_rejects_a_turn_with_no_reply(self) -> None:
        card = self.card("chest-pain-first-questions")
        pages = copy.deepcopy(self.pages(card))
        pages["chest-pain-focused-history"]["turns"] = pages["chest-pain-focused-history"]["turns"][:3]
        card["items"] = [{"page": "chest-pain-focused-history", "index": {"turn": 2, "flow": 1}}]
        pages["chest-pain-focused-history"]["turns"][2] = {"speaker": "Doctor", "text": "Anything else?"}
        with self.assertRaisesRegex(generator.ManifestError, "no patient reply"):
            generator.validate_card(card, 0, {**self.pages_by_library, "model-interview": pages})

    def test_model_interview_hook_takes_no_index(self) -> None:
        card = self.card("chest-pain-first-questions")
        card["hook"]["source"]["index"] = 0
        with self.assertRaisesRegex(generator.ManifestError, "takes no index"):
            self.validate(card)

    # ---- the card manifest cannot smuggle in clinical wording ------------

    def test_unknown_library_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["library"] = "case-presentation"
        with self.assertRaisesRegex(generator.ManifestError, "library"):
            self.validate(card)

    def test_unknown_source_page_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["items"][0]["page"] = "a-guide-that-was-never-published"
        with self.assertRaisesRegex(generator.ManifestError, "not a published guide"):
            self.validate(card)

    def test_page_from_another_library_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["items"][0]["page"] = "chest-pain-history-questions"
        with self.assertRaisesRegex(generator.ManifestError, "not a published guide"):
            self.validate(card)

    def test_step_without_a_language_note_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        pages = copy.deepcopy(self.pages(card))
        del pages["sbar-nursing-handoff-example"]["steps"][1]["language_note"]
        with self.assertRaisesRegex(generator.ManifestError, "no language_note"):
            generator.validate_card(card, 0, {**self.pages_by_library, "team-communication": pages})

    def test_repeated_item_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["items"][1] = card["items"][0]
        with self.assertRaisesRegex(generator.ManifestError, "repeats an earlier item"):
            self.validate(card)

    def test_unreviewed_card_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["review"]["clinical_text_is_source_verbatim"] = False
        with self.assertRaisesRegex(generator.ManifestError, "clinical_text_is_source_verbatim"):
            self.validate(card)

    def test_unexpected_key_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["overlay_text"] = "Anything at all"
        with self.assertRaisesRegex(generator.ManifestError, "unexpected key"):
            self.validate(card)

    # ---- the text budget -------------------------------------------------

    def test_long_consequence_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["hook"]["consequence"] = "Nobody comes, and the whole shift falls apart around you"
        with self.assertRaisesRegex(generator.ManifestError, "exceeds the .* budget"):
            self.validate(card)

    def test_too_many_items_are_rejected(self) -> None:
        card = self.card("words-your-patient-does-not-have")
        card["items"] = card["items"] * 4
        with self.assertRaisesRegex(generator.ManifestError, "over Instagram's limit"):
            self.validate(card)

    def test_long_source_quote_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        pages = copy.deepcopy(self.pages(card))
        note = pages["sbar-nursing-handoff-example"]["steps"][0]["language_note"]
        note["preferred"] = "His oxygen saturation has fallen to 88% on room air, " + "and so on, " * 10
        with self.assertRaisesRegex(generator.ManifestError, "select another item"):
            generator.validate_card(card, 0, {**self.pages_by_library, "team-communication": pages})

    def test_overlong_caption_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["caption"] = ["word " * 60] * 4
        with self.assertRaisesRegex(generator.ManifestError, "caption"):
            self.validate(card)

    def test_hashtag_must_be_bare_and_lowercase(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["hashtags"][0] = "#ClinicalEnglish"
        with self.assertRaisesRegex(generator.ManifestError, "lowercase alphanumeric"):
            self.validate(card)

    def test_unknown_tone_is_rejected(self) -> None:
        card = self.card("sbar-nursing-handoff")
        card["cta"]["headline"][0]["tone"] = "shout"
        with self.assertRaisesRegex(generator.ManifestError, "tone"):
            self.validate(card)


if __name__ == "__main__":
    unittest.main()
