#!/usr/bin/env python3
"""Small regression tests for model-interview manifest and sync fingerprints."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from model_interview_content import (  # noqa: E402
    DEFAULT_MANIFEST,
    DEFAULT_SOURCE_ROOT,
    ContentError,
    load_records,
    transcript_sha256,
)


class ModelInterviewGenerationTests(unittest.TestCase):
    def test_release_has_ten_unique_cases_and_twenty_unique_voices(self) -> None:
        records = load_records()
        self.assertEqual(10, len(records))
        self.assertEqual(10, len({record.case_id for record in records}))
        voices = [name for record in records for name in (record.item["voice"]["doctor"], record.item["voice"]["patient"])]
        self.assertEqual(20, len(set(voices)))

    def test_transcript_hash_changes_with_spoken_text(self) -> None:
        turns = [{"speaker": "Doctor", "text": "What brought you in today?"}, {"speaker": "Patient", "text": "Chest pain."}]
        changed = [{"speaker": "Doctor", "text": "What brought you in today?"}, {"speaker": "Patient", "text": "Chest pressure."}]
        self.assertNotEqual(transcript_sha256(turns), transcript_sha256(changed))

    def test_manifest_rejects_a_gap_between_audio_segments(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        manifest["pages"][0]["audio_segments"][1][0] += 1
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ContentError):
                load_records(path, DEFAULT_SOURCE_ROOT)

    def test_manifest_rejects_a_prediction_pause_after_the_final_segment(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        page = manifest["pages"][0]
        page["prediction_pauses"][-1]["after_segment"] = len(page["audio_segments"])
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ContentError):
                load_records(path, DEFAULT_SOURCE_ROOT)

    def test_manifest_rejects_recall_on_a_doctor_turn(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        manifest["pages"][0]["recall"]["patient_turn"] = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ContentError):
                load_records(path, DEFAULT_SOURCE_ROOT)


if __name__ == "__main__":
    unittest.main()
