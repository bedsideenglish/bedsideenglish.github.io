#!/usr/bin/env python3
"""Focused regression tests for the static learning-page generator."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("generate-learning-pages.py")
SPEC = importlib.util.spec_from_file_location("learning_generator", MODULE_PATH)
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


def valid_case(case_id: str = "case_001", phrase: str = "Does it move anywhere else?") -> dict:
    return {
        "id": case_id,
        "system": "cardiology",
        "difficulty": "beginner",
        "chief_complaint": "chest pain",
        "teaching": {
            "must_ask": [
                {
                    "objective": "Pain location & radiation",
                    "say": phrase,
                    "domains": ["location", "radiation"],
                }
            ]
        },
    }


class GeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "cases"
        self.source.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_case(self, data: dict, name: str = "case_001.json") -> Path:
        path = self.source / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_generation_is_escaped_and_deterministic(self) -> None:
        source = self.write_case(valid_case(phrase='Does <pain> "move" anywhere?'))
        spec = generator.PageSpec(source, "chest-pain-questions", "Chest & pain <English>", "A concise guide & practice page.")
        self.assertEqual(generator.generate([spec], self.root, False), 0)
        first = (self.root / "learning/chest-pain-questions/index.html").read_bytes()
        self.assertIn(b"Does &lt;pain&gt; &quot;move&quot; anywhere?", first)
        self.assertNotIn(b"Does <pain>", first)
        self.assertNotIn(b"{{", first)
        self.assertNotIn(b"Learning level", first)
        self.assertNotIn(b"educationalLevel", first)
        self.assertIn(b"source-sha256:", first)
        self.assertIn(b"G-FK1EXM7ZKH", first)
        self.assertEqual(generator.generate([spec], self.root, False), 0)
        self.assertEqual(first, (self.root / "learning/chest-pain-questions/index.html").read_bytes())
        self.assertEqual(generator.generate([spec], self.root, True), 0)

    def test_missing_optional_domains_is_supported(self) -> None:
        data = valid_case()
        del data["teaching"]["must_ask"][0]["domains"]
        source = self.write_case(data)
        spec = generator.PageSpec(source, "history-questions", "History questions", "A learning guide.")
        self.assertEqual(generator.generate([spec], self.root, False), 0)

    def test_unsupported_case_has_clear_error(self) -> None:
        source = self.write_case({"id": "team_case", "chief_complaint": "call a colleague"})
        with self.assertRaisesRegex(generator.GenerationError, "required field `system`"):
            generator.validate_case(generator.load_json(source), source)

    def test_slug_collision_is_rejected(self) -> None:
        first_source = self.write_case(valid_case("case_001"), "one.json")
        first = generator.PageSpec(first_source, "same-slug", "First", "First page.")
        generator.generate([first], self.root, False)
        second_source = self.write_case(valid_case("case_002"), "two.json")
        second = generator.PageSpec(second_source, "same-slug", "Second", "Second page.")
        with self.assertRaisesRegex(generator.GenerationError, "Slug collision"):
            generator.generate([second], self.root, False)

    def test_editorial_phrase_coaching_is_rendered(self) -> None:
        source = self.write_case(valid_case())
        spec = generator.PageSpec(
            source=source,
            slug="wording-guide",
            h1="A wording guide",
            meta_description="A reviewed wording guide.",
            quick_answer="Ask one clear question at a time.",
            reviewed_on="2026-08-23",
            question_edits={
                "Pain location & radiation": {
                    "phrases": ["Where is the pain?", "Does it spread anywhere else?"],
                    "purpose": "Ask about location and spread",
                    "why_this_wording": "Everyday wording is easier to understand.",
                    "alternatives": [{"label": "More clinical", "phrase": "Does it radiate?"}],
                }
            },
        )
        self.assertEqual(generator.generate([spec], self.root, False), 0)
        output = (self.root / "learning/wording-guide/index.html").read_text(encoding="utf-8")
        self.assertIn("Why this wording", output)
        self.assertIn("Does it spread anywhere else?", output)
        self.assertIn("23 August 2026", output)

    def test_presupposition_lint_rejects_each_time(self) -> None:
        with self.assertRaisesRegex(generator.GenerationError, "episodic"):
            generator.enforce_assumption_safe_questions(
                [("Onset and duration", "How long does it last each time?")],
                "sample",
            )

    def test_us_style_lint_rejects_british_patient_language(self) -> None:
        with self.assertRaisesRegex(generator.GenerationError, "bowel movement"):
            generator.enforce_us_style(
                [("question", "Do you need to open your bowels at night?")],
                "sample",
            )


    def test_semantic_related_slug_linking(self) -> None:
        source_a = self.write_case(valid_case("case_a"), "a.json")
        source_b = self.write_case(valid_case("case_b"), "b.json")
        spec_a = generator.PageSpec(source_a, "page-a", "Page A", "Page A summary", related_slug="page-b")
        spec_b = generator.PageSpec(source_b, "page-b", "Page B", "Page B summary", related_slug="page-a")
        self.assertEqual(generator.generate([spec_a, spec_b], self.root, False), 0)
        output_a = (self.root / "learning/page-a/index.html").read_text(encoding="utf-8")
        self.assertIn('href="../page-b/"', output_a)
        output_b = (self.root / "learning/page-b/index.html").read_text(encoding="utf-8")
        self.assertIn('href="../page-a/"', output_b)


if __name__ == "__main__":
    unittest.main()
