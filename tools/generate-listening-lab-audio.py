#!/usr/bin/env python3
"""Generate region-profiled Gemini audio for one Everyday Listening Lab page."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
import wave


SITE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SITE_ROOT.parent
VOICE_BY_PROFILE = {
    "us": "Achird",
    "uk": "Charon",
    "aus": "Algieba",
    "in": "Iapetus",
    "sg": "Kore",
}


def read_env_value(env_path: Path, name: str) -> str | None:
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return None


def load_config(page: Path) -> dict:
    html = page.read_text(encoding="utf-8")
    match = re.search(r'<script id="listening-lab-config" type="application/json">(.*?)</script>', html, flags=re.S)
    if not match:
        raise SystemExit(f"No listening-lab config found in {page}")
    return json.loads(match.group(1))


def prompt_for(profile: dict, transcript: str) -> str:
    return (
        "You are a fellow passenger repeating a short airport announcement to a traveller. "
        f"{profile['tts_prompt']} "
        "Read only the exact transcript below. Do not introduce it, explain it, or add words. "
        f"Transcript: {transcript}"
    )


def request_pcm(api_key: str, model: str, voice: str, prompt: str) -> bytes:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini returned HTTP {error.code}: {detail}") from error
    try:
        return base64.b64decode(body["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"Gemini did not return inline audio data: {body}") from error


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(pcm)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--env-file", type=Path, default=WORKSPACE_ROOT / ".env")
    parser.add_argument("--output-dir", type=Path, default=SITE_ROOT / "assets" / "audio" / "everyday")
    parser.add_argument("--model", default="gemini-3.1-flash-tts-preview")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or read_env_value(args.env_file, "GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set. Put it in the workspace .env or environment.")
    config = load_config(args.page)
    drill = config["drill"]
    for profile in config["profiles"]:
        profile_id = profile["id"]
        voice = VOICE_BY_PROFILE.get(profile_id, "Achird")
        output_dir = args.output_dir / drill["id"]
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{profile_id}.wav"
        if output.exists() and not args.force:
            print(f"kept {output.relative_to(SITE_ROOT)}")
            continue
        print(f"generating {drill['id']} / {profile_id} ({voice})")
        write_wav(output, request_pcm(api_key, args.model, voice, prompt_for(profile, drill["transcript"])))
        print(f"wrote {output.relative_to(SITE_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
