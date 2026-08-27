#!/usr/bin/env python3
"""Regression tests for the oral case-presentation generator."""

from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "generate-case-presentation-pages.py"
SPEC = importlib.util.spec_from_file_location("case_presentation_generator", GENERATOR_PATH)
assert SPEC and SPEC.loader
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


class CasePresentationGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_root = GEN.DEFAULT_SOURCE_ROOT.resolve()
        cls.pages = GEN.load_pages(GEN.DEFAULT_MANIFEST, cls.source_root)

    def test_reviewed_library_contains_two_source_locked_pages(self) -> None:
        self.assertEqual([page["source"]["case_id"] for page in self.pages], ["cardio_001", "pulm_001"])
        for page in self.pages:
            self.assertEqual(len(page["_source_sha256"]), 64)
            self.assertGreaterEqual(len(page["_fact_values"]), 10)

    def test_unknown_fact_reference_is_blocked(self) -> None:
        page = deepcopy(self.pages[0])
        for key in list(page):
            if key.startswith("_"):
                del page[key]
        page["sections"][0]["fact_refs"].append("invented_vital_sign")
        with self.assertRaisesRegex(GEN.GenerationError, "unknown facts"):
            GEN.validate_page(page, self.source_root, "page")

    def test_claiming_present_source_data_are_missing_is_blocked(self) -> None:
        page = deepcopy(self.pages[0])
        for key in list(page):
            if key.startswith("_"):
                del page[key]
        page["known_gaps"][0]["missing_paths"].append("age")
        with self.assertRaisesRegex(GEN.GenerationError, "claimed-missing path exists"):
            GEN.validate_page(page, self.source_root, "page")

    def test_omitting_an_objective_source_result_number_is_blocked(self) -> None:
        page = deepcopy(self.pages[0])
        for key in list(page):
            if key.startswith("_"):
                del page[key]
        page["sections"][3]["spoken"] = page["sections"][3]["spoken"].replace("176", "a higher value")
        with self.assertRaisesRegex(GEN.GenerationError, "omits source result number"):
            GEN.validate_page(page, self.source_root, "page")

    def test_unfinished_human_review_is_blocked(self) -> None:
        page = deepcopy(self.pages[1])
        for key in list(page):
            if key.startswith("_"):
                del page[key]
        page["review"]["presentation_flow_read_aloud"] = False
        with self.assertRaisesRegex(GEN.GenerationError, "unchecked attestations"):
            GEN.validate_page(page, self.source_root, "page")

    def test_rendered_page_exposes_provenance_and_all_six_sections(self) -> None:
        page = self.pages[0]
        rendered = GEN.render_page(page)
        self.assertIn(f"source-case: {page['source']['case_id']}", rendered)
        self.assertIn(page["_source_sha256"], rendered)
        self.assertEqual(rendered.count('class="presentation-step"'), 6)
        self.assertNotIn("{{", rendered)


if __name__ == "__main__":
    unittest.main()
