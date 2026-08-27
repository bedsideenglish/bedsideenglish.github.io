#!/usr/bin/env python3
"""Shared validation and fingerprints for generated model-interview pages and WAV audio."""

from __future__ import annotations

import hashlib
import json
import re
import wave
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


SITE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SITE_ROOT.parent
DEFAULT_MANIFEST = SITE_ROOT / "model-interview-pages.json"
DEFAULT_SOURCE_ROOT = WORKSPACE_ROOT / "Medvoicetrainer-android-app-version" / "data" / "cases"
DEFAULT_AUDIO_ROOT = SITE_ROOT / "assets" / "audio" / "model-interviews"
MODEL_ID = "gemini-3.1-flash-tts-preview"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_SPEAKERS = {"Doctor", "Patient", "Parent"}


class ContentError(RuntimeError):
    """The manifest, source case, generated page, or audio is inconsistent."""


@dataclass(frozen=True)
class PageRecord:
    item: dict[str, Any]
    source_path: Path
    source_case: str
    source_sha256: str
    case_id: str
    transcript_sha256: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_transcript_bytes(turns: list[dict[str, str]]) -> bytes:
    return json.dumps(turns, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def transcript_sha256(turns: list[dict[str, str]]) -> str:
    return sha256_bytes(canonical_transcript_bytes(turns))


def segment_transcript(turns: list[dict[str, str]], start: int, end: int) -> str:
    return "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in turns[start : end + 1])


def require_string(item: dict[str, Any], key: str, where: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContentError(f"{where}.{key} must be a non-empty string")
    return value.strip()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContentError(f"Missing file: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContentError(f"Invalid UTF-8 JSON in {path}: {exc}") from exc


def validate_segments(raw: Any, turn_count: int, where: str) -> list[tuple[int, int]]:
    if not isinstance(raw, list) or not raw:
        raise ContentError(f"{where}.audio_segments must be a non-empty list")
    segments: list[tuple[int, int]] = []
    expected_start = 0
    for index, value in enumerate(raw):
        if not isinstance(value, list) or len(value) != 2 or not all(isinstance(number, int) for number in value):
            raise ContentError(f"{where}.audio_segments[{index}] must be [start, end] integer indexes")
        start, end = value
        if start != expected_start or end < start or end >= turn_count:
            raise ContentError(f"{where}.audio_segments[{index}] is not contiguous or is out of range")
        if end - start + 1 > 10:
            raise ContentError(f"{where}.audio_segments[{index}] contains more than 10 turns")
        segments.append((start, end))
        expected_start = end + 1
    if expected_start != turn_count:
        raise ContentError(f"{where}.audio_segments do not cover all {turn_count} turns")
    return segments


def load_records(manifest_path: Path = DEFAULT_MANIFEST, source_root: Path = DEFAULT_SOURCE_ROOT) -> list[PageRecord]:
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("pages"), list):
        raise ContentError(f"{manifest_path}: expected schema_version 1 and a pages list")
    pages = manifest["pages"]
    if len(pages) != 10:
        raise ContentError(f"{manifest_path}: the published library must contain exactly 10 pages")
    records: list[PageRecord] = []
    seen_slugs: set[str] = set()
    seen_cases: set[str] = set()
    for index, item in enumerate(pages):
        where = f"pages[{index}]"
        if not isinstance(item, dict):
            raise ContentError(f"{where} must be an object")
        for key in ("case", "slug", "specialty", "h1", "meta_description", "setting", "patient_card", "estimated_minutes", "reviewed_on"):
            require_string(item, key, where)
        slug = item["slug"].strip()
        if not SLUG_RE.fullmatch(slug) or slug in seen_slugs:
            raise ContentError(f"{where}.slug is invalid or duplicated: {slug!r}")
        seen_slugs.add(slug)
        source_case = item["case"].strip().replace("\\", "/")
        if source_case in seen_cases or Path(source_case).is_absolute() or ".." in Path(source_case).parts:
            raise ContentError(f"{where}.case is unsafe or duplicated: {source_case!r}")
        seen_cases.add(source_case)
        source_path = source_root / Path(source_case)
        case = load_json(source_path)
        if not isinstance(case, dict):
            raise ContentError(f"{source_path}: source case must be an object")
        case_id = require_string(case, "id", str(source_path))
        try:
            date.fromisoformat(item["reviewed_on"])
        except ValueError as exc:
            raise ContentError(f"{where}.reviewed_on must use YYYY-MM-DD") from exc

        voice = item.get("voice")
        if not isinstance(voice, dict):
            raise ContentError(f"{where}.voice must be an object")
        for key in ("doctor", "patient", "patient_speaker", "direction"):
            require_string(voice, key, f"{where}.voice")
        if voice["patient_speaker"] not in {"Patient", "Parent"} or voice["doctor"] == voice["patient"]:
            raise ContentError(f"{where}.voice must use distinct doctor/patient voices and a valid patient_speaker")

        turns = item.get("turns")
        if not isinstance(turns, list) or len(turns) < 16:
            raise ContentError(f"{where}.turns must contain at least 16 turns")
        for turn_index, turn in enumerate(turns):
            if not isinstance(turn, dict) or set(turn) != {"speaker", "text"}:
                raise ContentError(f"{where}.turns[{turn_index}] must contain only speaker and text")
            speaker = require_string(turn, "speaker", f"{where}.turns[{turn_index}]")
            require_string(turn, "text", f"{where}.turns[{turn_index}]")
            expected_speaker = "Doctor" if turn_index % 2 == 0 else voice["patient_speaker"]
            if speaker not in ALLOWED_SPEAKERS or speaker != expected_speaker:
                raise ContentError(f"{where}.turns[{turn_index}] must be spoken by {expected_speaker}")
        validate_segments(item.get("audio_segments"), len(turns), where)

        prediction_pauses = item.get("prediction_pauses")
        if not isinstance(prediction_pauses, list) or not 2 <= len(prediction_pauses) <= 3:
            raise ContentError(f"{where}.prediction_pauses must contain two or three pauses")
        pause_segments: list[int] = []
        segment_count = len(item["audio_segments"])
        for pause_index, pause in enumerate(prediction_pauses):
            pause_where = f"{where}.prediction_pauses[{pause_index}]"
            if not isinstance(pause, dict) or set(pause) != {"after_segment", "prompt"}:
                raise ContentError(f"{pause_where} must contain only after_segment and prompt")
            after_segment = pause.get("after_segment")
            if not isinstance(after_segment, int) or not 1 <= after_segment < segment_count:
                raise ContentError(f"{pause_where}.after_segment must identify a non-final audio segment")
            require_string(pause, "prompt", pause_where)
            pause_segments.append(after_segment)
        if pause_segments != sorted(set(pause_segments)):
            raise ContentError(f"{where}.prediction_pauses must be unique and ordered by segment")

        recall = item.get("recall")
        if not isinstance(recall, dict) or set(recall) != {"patient_turn", "cue"}:
            raise ContentError(f"{where}.recall must contain only patient_turn and cue")
        patient_turn = recall.get("patient_turn")
        if not isinstance(patient_turn, int) or not 0 <= patient_turn < len(turns) - 1:
            raise ContentError(f"{where}.recall.patient_turn must identify a non-final turn")
        if turns[patient_turn]["speaker"] == "Doctor" or turns[patient_turn + 1]["speaker"] != "Doctor":
            raise ContentError(f"{where}.recall.patient_turn must be a patient/parent answer followed by a doctor question")
        require_string(recall, "cue", f"{where}.recall")

        for list_key in ("flow", "do_not_miss", "sources"):
            if not isinstance(item.get(list_key), list) or not item[list_key]:
                raise ContentError(f"{where}.{list_key} must be a non-empty list")
        for source_index, source in enumerate(item["sources"]):
            if not isinstance(source, dict) or set(source) != {"title", "url"}:
                raise ContentError(f"{where}.sources[{source_index}] must contain title and url")
            if not require_string(source, "url", f"{where}.sources[{source_index}]").startswith("https://"):
                raise ContentError(f"{where}.sources[{source_index}].url must use HTTPS")

        records.append(
            PageRecord(
                item=item,
                source_path=source_path,
                source_case=source_case,
                source_sha256=sha256_file(source_path),
                case_id=case_id,
                transcript_sha256=transcript_sha256(turns),
            )
        )
    voice_names = [voice for record in records for voice in (record.item["voice"]["doctor"], record.item["voice"]["patient"])]
    if len(voice_names) != len(set(voice_names)):
        raise ContentError("Every published doctor and patient voice must be distinct across all ten cases")
    return records


def load_audio_metadata(record: PageRecord, audio_root: Path = DEFAULT_AUDIO_ROOT) -> dict[str, Any]:
    path = audio_root / record.item["slug"] / "metadata.json"
    data = load_json(path)
    if not isinstance(data, dict):
        raise ContentError(f"{path}: metadata must be an object")
    expected = {
        "schema_version": 1,
        "model": MODEL_ID,
        "source_case": record.source_case,
        "source_sha256": record.source_sha256,
        "transcript_sha256": record.transcript_sha256,
        "doctor_voice": record.item["voice"]["doctor"],
        "patient_voice": record.item["voice"]["patient"],
        "patient_speaker": record.item["voice"]["patient_speaker"],
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise ContentError(f"{path}: {key} is stale; expected {value!r}, found {data.get(key)!r}")
    segments = data.get("segments")
    expected_ranges = validate_segments(record.item["audio_segments"], len(record.item["turns"]), record.item["slug"])
    if not isinstance(segments, list) or len(segments) != len(expected_ranges):
        raise ContentError(f"{path}: segments do not match the manifest")
    for index, ((start, end), segment) in enumerate(zip(expected_ranges, segments, strict=True)):
        if not isinstance(segment, dict):
            raise ContentError(f"{path}: segment {index} must be an object")
        expected_text_hash = sha256_bytes(segment_transcript(record.item["turns"], start, end).encode("utf-8"))
        expected_file = f"part-{index + 1:02d}.wav"
        if segment.get("turn_start") != start or segment.get("turn_end") != end or segment.get("file") != expected_file:
            raise ContentError(f"{path}: segment {index} range or filename is stale")
        if segment.get("transcript_sha256") != expected_text_hash:
            raise ContentError(f"{path}: segment {index} transcript fingerprint is stale")
        wav_path = path.parent / expected_file
        if not wav_path.is_file() or segment.get("wav_sha256") != sha256_file(wav_path):
            raise ContentError(f"{path}: segment {index} WAV is missing or has the wrong checksum")
        duration = segment.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise ContentError(f"{path}: segment {index} duration must be positive")
        try:
            with wave.open(str(wav_path), "rb") as source:
                actual_duration = source.getnframes() / source.getframerate()
                if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != 24000:
                    raise ContentError(f"{wav_path}: expected 24 kHz mono 16-bit PCM WAV")
        except (wave.Error, EOFError) as exc:
            raise ContentError(f"{wav_path}: invalid WAV file: {exc}") from exc
        if abs(actual_duration - float(duration)) > 0.01:
            raise ContentError(f"{path}: segment {index} WAV duration is stale")
        if not SHA_RE.fullmatch(str(segment.get("wav_sha256", ""))):
            raise ContentError(f"{path}: segment {index} WAV hash is invalid")
    return data
