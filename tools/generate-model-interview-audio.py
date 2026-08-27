#!/usr/bin/env python3
"""Pre-generate static two-speaker WAV files for model history-taking pages."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
import wave


TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from model_interview_content import (  # noqa: E402
    DEFAULT_AUDIO_ROOT,
    DEFAULT_MANIFEST,
    DEFAULT_SOURCE_ROOT,
    MODEL_ID,
    ContentError,
    PageRecord,
    load_json,
    load_records,
    segment_transcript,
    sha256_bytes,
    sha256_file,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def read_env_value(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def tts_prompt(record: PageRecord, start: int, end: int) -> str:
    voice = record.item["voice"]
    transcript = segment_transcript(record.item["turns"], start, end)
    return (
        "Render one continuous segment from a two-person clinical education recording.\n"
        f"Audio profile and scene: {voice['direction']}\n"
        "Director's notes: Use American English. Read every spoken line exactly as written and in order. "
        "Do not introduce the scene, speak the speaker labels, add words, omit words, paraphrase, or summarize. "
        "Keep the handoff between speakers natural and leave only a short pause between turns.\n\n"
        "SCRIPT\n"
        f"{transcript}"
    )


def request_pcm(api_key: str, record: PageRecord, start: int, end: int) -> bytes:
    voice = record.item["voice"]
    patient_speaker = voice["patient_speaker"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": tts_prompt(record, start, end)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "languageCode": "en-US",
                "multiSpeakerVoiceConfig": {
                    "speakerVoiceConfigs": [
                        {
                            "speaker": "Doctor",
                            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice["doctor"]}},
                        },
                        {
                            "speaker": patient_speaker,
                            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice["patient"]}},
                        },
                    ]
                },
            },
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    body: dict[str, object] | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            retry_after = re.search(r"retry in (\d+(?:\.\d+)?)s", detail, flags=re.I)
            if error.code not in {429, 500, 503} or attempt == 5:
                raise ContentError(f"Gemini returned HTTP {error.code}: {detail}") from error
            wait_seconds = min(55, max(2, int(float(retry_after.group(1))) + 1 if retry_after else 2 ** (attempt + 1)))
            print(f"  temporary API response {error.code}; retrying in {wait_seconds}s", flush=True)
            time.sleep(wait_seconds)
        except urllib.error.URLError as error:
            if attempt == 5:
                raise ContentError(f"Could not reach Gemini TTS: {error.reason}") from error
            wait_seconds = min(30, 2 ** (attempt + 1))
            print(f"  network retry in {wait_seconds}s", flush=True)
            time.sleep(wait_seconds)
    if body is None:
        raise ContentError("Gemini TTS returned no response")
    try:
        parts = body["candidates"][0]["content"]["parts"]  # type: ignore[index]
        encoded_parts = [part["inlineData"]["data"] for part in parts if "inlineData" in part]
    except (KeyError, IndexError, TypeError) as error:
        raise ContentError(f"Gemini TTS did not return audio data: {json.dumps(body)[:1200]}") from error
    if not encoded_parts:
        raise ContentError(f"Gemini TTS returned no inline audio: {json.dumps(body)[:1200]}")
    return b"".join(base64.b64decode(value) for value in encoded_parts)


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(pcm)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return round(source.getnframes() / source.getframerate(), 3)


def base_metadata(record: PageRecord) -> dict[str, object]:
    voice = record.item["voice"]
    return {
        "schema_version": 1,
        "model": MODEL_ID,
        "source_case": record.source_case,
        "source_sha256": record.source_sha256,
        "transcript_sha256": record.transcript_sha256,
        "doctor_voice": voice["doctor"],
        "patient_voice": voice["patient"],
        "patient_speaker": voice["patient_speaker"],
        "sample_rate_hz": 24000,
        "channels": 1,
        "sample_width_bytes": 2,
        "segments": [],
    }


def usable_cached_segment(
    old: dict[str, object] | None,
    expected_base: dict[str, object],
    index: int,
    path: Path,
    start: int,
    end: int,
    transcript_hash: str,
) -> dict[str, object] | None:
    if old is None:
        return None
    for key in ("schema_version", "model", "source_case", "source_sha256", "transcript_sha256", "doctor_voice", "patient_voice", "patient_speaker"):
        if old.get(key) != expected_base[key]:
            return None
    segments = old.get("segments")
    if not isinstance(segments, list) or index >= len(segments) or not isinstance(segments[index], dict):
        return None
    segment = segments[index]
    if (
        segment.get("file") != path.name
        or segment.get("turn_start") != start
        or segment.get("turn_end") != end
        or segment.get("transcript_sha256") != transcript_hash
        or not path.is_file()
        or segment.get("wav_sha256") != sha256_file(path)
    ):
        return None
    return segment


def generate_record(record: PageRecord, api_key: str, audio_root: Path, force: bool) -> None:
    slug = record.item["slug"]
    output_dir = audio_root / slug
    metadata_path = output_dir / "metadata.json"
    old: dict[str, object] | None = None
    if metadata_path.is_file():
        loaded = load_json(metadata_path)
        if isinstance(loaded, dict):
            old = loaded
    metadata = base_metadata(record)
    ranges = [tuple(segment) for segment in record.item["audio_segments"]]
    print(f"{slug}: {len(ranges)} WAV parts, doctor={record.item['voice']['doctor']}, {record.item['voice']['patient_speaker'].lower()}={record.item['voice']['patient']}", flush=True)
    for index, (start, end) in enumerate(ranges):
        wav_path = output_dir / f"part-{index + 1:02d}.wav"
        text_hash = sha256_bytes(segment_transcript(record.item["turns"], start, end).encode("utf-8"))
        cached = None if force else usable_cached_segment(old, metadata, index, wav_path, start, end, text_hash)
        if cached is not None:
            print(f"  kept {wav_path.name}", flush=True)
            segment_metadata = cached
        else:
            print(f"  generating {wav_path.name} (turns {start + 1}-{end + 1})", flush=True)
            pcm = request_pcm(api_key, record, start, end)
            write_wav(wav_path, pcm)
            segment_metadata = {
                "file": wav_path.name,
                "turn_start": start,
                "turn_end": end,
                "transcript_sha256": text_hash,
                "wav_sha256": sha256_file(wav_path),
                "duration_seconds": wav_duration(wav_path),
            }
            print(f"  wrote {wav_path.name} ({segment_metadata['duration_seconds']}s)", flush=True)
        metadata["segments"].append(segment_metadata)  # type: ignore[union-attr]
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=WORKSPACE_ROOT / ".env")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--page", action="append", help="Generate one slug; repeatable")
    parser.add_argument("--force", action="store_true", help="Regenerate WAV parts even when all fingerprints match")
    args = parser.parse_args()
    api_key = os.environ.get("GEMINI_API_KEY") or read_env_value(args.env_file, "GEMINI_API_KEY")
    if not api_key:
        print("error: GEMINI_API_KEY is not set in the environment or workspace .env", file=sys.stderr)
        return 1
    try:
        records = load_records(args.manifest, args.source_root)
        selected = [record for record in records if not args.page or record.item["slug"] in args.page]
        if args.page and len(selected) != len(set(args.page)):
            known = ", ".join(record.item["slug"] for record in records)
            raise ContentError(f"Unknown --page value. Available slugs: {known}")
        for record in selected:
            generate_record(record, api_key, args.audio_root, args.force)
        return 0
    except ContentError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
