#!/usr/bin/env python3
"""Regression tests for the team-communication generator."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("generate-team-communication-pages.py")
SPEC = importlib.util.spec_from_file_location("team_generator", MODULE_PATH)
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


MANIFEST = Path(__file__).resolve().parents[1] / "team-communication-pages.json"


class TeamGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = json.loads(MANIFEST.read_text(encoding="utf-8"))["pages"]
        cls.page = cls.pages[0]

    def test_sample_passes_strict_schema(self) -> None:
        validated = generator.validate_page(copy.deepcopy(self.page), "sample")
        self.assertEqual(validated["framework"]["name"], "SBAR")

    def test_all_supported_framework_samples_pass(self) -> None:
        names = {
            generator.validate_page(copy.deepcopy(page), f"sample[{index}]")["framework"]["name"]
            for index, page in enumerate(self.pages)
        }
        self.assertEqual(names, {"SBAR", "I-PASS", "Check-Back"})

    def test_generation_is_escaped_and_deterministic(self) -> None:
        page = copy.deepcopy(self.page)
        page["steps"][0]["statements"][0]["text"] = (
            'This is Mina & the <nurse> "calling" about Mr. Han, age 68, in room 412.'
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(generator.generate([page], root, False), 0)
            output = root / "communication" / page["slug"] / "index.html"
            first = output.read_bytes()
            self.assertIn(b'Mina &amp; the &lt;nurse&gt; &quot;calling&quot;', first)
            self.assertNotIn(b"<nurse>", first)
            self.assertNotIn(b"{{", first)
            self.assertEqual(generator.generate([page], root, False), 0)
            self.assertEqual(first, output.read_bytes())

    def test_missing_must_say_fact_is_rejected(self) -> None:
        page = copy.deepcopy(self.page)
        for step in page["steps"]:
            for statement in step["statements"]:
                statement["fact_refs"] = [ref for ref in statement["fact_refs"] if ref != "oxygen"]
        with self.assertRaisesRegex(generator.GenerationError, "oxygen"):
            generator.validate_page(page, "sample")

    def test_numeric_drift_in_must_say_fact_is_rejected(self) -> None:
        page = copy.deepcopy(self.page)
        page["facts"][0]["value"] = "Mr. Han · 68 years old · Room 999"
        with self.assertRaisesRegex(generator.GenerationError, "999"):
            generator.validate_page(page, "sample")

    def test_nonstandard_sbar_order_is_rejected(self) -> None:
        page = copy.deepcopy(self.page)
        page["steps"][0], page["steps"][1] = page["steps"][1], page["steps"][0]
        with self.assertRaisesRegex(generator.GenerationError, "S = Situation"):
            generator.validate_page(page, "sample")

    def test_unchecked_editorial_attestation_is_rejected(self) -> None:
        page = copy.deepcopy(self.page)
        page["review"]["source_claims_checked"] = False
        with self.assertRaisesRegex(generator.GenerationError, "source_claims_checked"):
            generator.validate_page(page, "sample")

    def test_absolute_safety_claim_is_rejected(self) -> None:
        page = copy.deepcopy(self.page)
        page["lede"] = "This framework prevents all errors during every handoff in every setting."
        with self.assertRaisesRegex(generator.GenerationError, "absolute safety claims"):
            generator.validate_page(page, "sample")

    def test_structured_data_matches_visible_source_record(self) -> None:
        canonical = "https://bedsideenglish.github.io/communication/sample/"
        payload = json.loads(generator.structured_data(self.page, canonical))
        article = next(node for node in payload["@graph"] if "Article" in node["@type"])
        self.assertEqual(article["headline"], self.page["h1"])
        self.assertEqual(set(article["citation"]), {source["url"] for source in self.page["sources"]})

    def test_single_page_generation_preserves_full_hub(self) -> None:
        first = copy.deepcopy(self.page)
        second = copy.deepcopy(self.page)
        second["slug"] = "sbar-team-update-example"
        second["title"] = "SBAR Team Update Example: Script and Chart | Bedside English"
        second["h1"] = "SBAR team update example in English"
        second["search"]["primary_query"] = "SBAR team update example"
        second["library_order"] = 99
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(generator.generate([first, second], root, False), 0)
            second_output = root / "communication" / second["slug"] / "index.html"
            before = second_output.read_bytes()
            self.assertEqual(generator.generate([first, second], root, False, {first["slug"]}), 0)
            self.assertEqual(before, second_output.read_bytes())
            hub = (root / "communication" / "index.html").read_text(encoding="utf-8")
            self.assertIn(first["h1"], hub)
            self.assertIn(second["h1"], hub)


if __name__ == "__main__":
    unittest.main()
