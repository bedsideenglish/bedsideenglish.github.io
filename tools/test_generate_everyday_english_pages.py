#!/usr/bin/env python3
"""Regression tests for the everyday-English generation and scoring contract."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "generate-everyday-english-pages.py"
SPEC = importlib.util.spec_from_file_location("everyday_generator", GENERATOR_PATH)
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class EverydayEnglishGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profiles, cls.pages = generator.load_manifest(ROOT / "everyday-english-pages.json")
        cls.drills = generator.load_drills(
            ROOT / "everyday-listening-drills.json",
            {profile["id"] for profile in cls.profiles},
        )

    def test_sample_renders_from_real_app_drill(self) -> None:
        page = self.pages[0]
        drill = self.drills[page["source_drill_id"]]
        rendered = generator.render_page(page, drill, self.profiles)
        self.assertIn('id="listening-lab-config"', rendered)
        self.assertIn('id="commit-answer"', rendered)
        self.assertIn('id="revealed-transcript"', rendered)
        self.assertIn("Transcript revealed after commit", rendered)
        self.assertIn(generator.source_hash(drill), rendered)

    def test_unchecked_editorial_attestation_blocks_publication(self) -> None:
        page = copy.deepcopy(self.pages[0])
        page["review"]["scoring_cases_checked"] = False
        with self.assertRaises(generator.GenerationError):
            generator.validate_page(page, "page")

    def test_unknown_speaker_profile_blocks_source_loading(self) -> None:
        with self.assertRaises(generator.GenerationError):
            generator.load_drills(
                ROOT / "everyday-listening-drills.json",
                {"us"},
            )

    def test_javascript_scoring_rejects_negation_and_alternatives(self) -> None:
        js_path = ROOT / "everyday-english" / "listening-lab.js"
        script = r"""
const lab = require(process.argv[1]);
const details = [
  {key: 'gate', label: 'gate', answers: ['b12', 'b 12', 'b twelve', 'gate b12']},
  {key: 'time', label: 'boarding time', answers: ['6:40', 'six forty', '6 40']}
];
const payload = {
  clean: lab.scoreDetails(details, {gate: 'B 12', time: '6:40'}),
  negated: lab.scoreField('not B12', details[0].answers),
  rejectedAfter: lab.scoreField('B12 was wrong', details[0].answers),
  uncertain: lab.scoreField('maybe B12', details[0].answers),
  alternatives: lab.scoreField('B12 or C12', details[0].answers)
};
process.stdout.write(JSON.stringify(payload));
"""
        completed = subprocess.run(
            ["node", "-e", script, str(js_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["clean"]["details_correct"], 2)
        self.assertFalse(result["negated"]["correct"])
        self.assertEqual(result["negated"]["reason"], "negated")
        self.assertFalse(result["rejectedAfter"]["correct"])
        self.assertFalse(result["uncertain"]["correct"])
        self.assertFalse(result["alternatives"]["correct"])

    def test_public_landings_do_not_claim_play_review(self) -> None:
        for filename in ("index.html", "android.html", "android-everyday.html"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertNotIn("Under Google Play review", source)
            self.assertNotIn("Google Play 심사 중", source)
            self.assertIn("https://play.google.com/store/apps/details?id=com.boyskier.bedsideenglish", source)


if __name__ == "__main__":
    unittest.main()
