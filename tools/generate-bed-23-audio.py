#!/usr/bin/env python3
"""Generate the pre-rendered Gemini voice clips used by android-demo.html."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
import wave


SITE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SITE_ROOT.parent
DEFAULT_OUTPUT = SITE_ROOT / "assets" / "audio" / "bed-23"

# Every line is separate so the three roles stay recognizably different.
CLIPS = (
    ("attending-brief-you", "Gacrux", "attending", "You."),
    ("attending-brief-bed-23", "Gacrux", "attending", "Bed twenty-three."),
    ("attending-brief-patient", "Gacrux", "attending", "Thirty-four-year-old woman. Chest pain."),
    ("attending-brief-history", "Gacrux", "attending", "Take the history."),
    ("attending-brief-returning", "Gacrux", "attending", "We'll come back to you."),
    ("attending-twenty-seconds", "Gacrux", "attending", "Twenty seconds. Then you present her."),
    ("attending-return", "Gacrux", "attending", "How's the patient in bed twenty-three?"),
    ("attending-return-time", "Gacrux", "attending", "Time. So, how's the patient in bed twenty-three?"),
    ("patient-opening", "Sulafat", "patient", "Doctor... I've got this pain in my chest. It started this morning."),
    ("patient-radiation", "Sulafat", "patient", "Yeah... into my left shoulder. Should I be worried?"),
    ("patient-provocation", "Sulafat", "patient", "Yes — much sharper. I keep taking these shallow breaths."),
    ("patient-nudge-first", "Sulafat", "patient", "Doctor? Are you going to ask me something?"),
    ("patient-nudge-second", "Sulafat", "patient", "Doctor? Is that a bad sign?"),
    ("learner-radiation", "Achird", "learner", "Does the pain go anywhere else?"),
    ("learner-provocation", "Achird", "learner", "Is it worse when you take a deep breath?"),
)


def read_env_value(env_path: Path, name: str) -> str | None:
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def prompt_for(role: str, transcript: str) -> str:
    direction = {
        "attending": "You are an experienced attending physician leading brisk morning rounds. Use a mature, grounded American English voice: calm authority and a concise pace.",
        "patient": "You are a 34-year-old patient with new chest pain speaking to a doctor. Use a warm, natural American English voice. Sound concerned and slightly breathless, but remain clearly intelligible.",
        "learner": "You are a medical learner rehearsing a question aloud. Use a distinct, friendly young-adult American English voice with a steady, clear pace.",
    }[role]
    return f"{direction}\n\nRead only the exact transcript below. Do not introduce it or add words.\nTranscript: {transcript}"


def request_pcm(api_key: str, model: str, voice_name: str, role: str, transcript: str) -> bytes:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt_for(role, transcript)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}},
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            # Do not include request headers in errors; they contain the API key.
            detail = error.read().decode("utf-8", errors="replace")
            retry_after = re.search(r"retry in (\d+(?:\.\d+)?)s", detail, flags=re.I)
            if error.code != 429 or not retry_after or attempt == 5:
                raise RuntimeError(f"Gemini returned HTTP {error.code}: {detail}") from error
            wait_seconds = max(1, int(float(retry_after.group(1))) + 1)
            print(f"rate limited; retrying this clip in {wait_seconds}s")
            time.sleep(wait_seconds)
    try:
        encoded = body["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"Gemini did not return inline audio data: {body}") from error
    return base64.b64decode(encoded)


def write_wav(path: Path, pcm: bytes) -> None:
    # Gemini TTS emits 24 kHz, mono, 16-bit signed PCM.
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(pcm)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=WORKSPACE_ROOT / ".env")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default="gemini-3.1-flash-tts-preview")
    parser.add_argument("--clip", action="append", choices=[clip[0] for clip in CLIPS], help="Generate only one named clip; repeatable.")
    parser.add_argument("--force", action="store_true", help="Regenerate clips that already exist.")
    args = parser.parse_args()
    api_key = os.environ.get("GEMINI_API_KEY") or read_env_value(args.env_file, "GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set. Put it in the workspace .env or environment.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    clips = tuple(clip for clip in CLIPS if not args.clip or clip[0] in args.clip)
    for clip_id, voice, role, transcript in clips:
        output_path = args.output_dir / f"{clip_id}.wav"
        if output_path.exists() and not args.force:
            print(f"kept {output_path.relative_to(SITE_ROOT)}")
            continue
        print(f"generating {clip_id} ({role}/{voice})")
        write_wav(output_path, request_pcm(api_key, args.model, voice, role, transcript))
        print(f"wrote {output_path.relative_to(SITE_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
