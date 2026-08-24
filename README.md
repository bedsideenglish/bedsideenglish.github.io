# Bedside English: Talk & Train — Landing Page

![Talk to an AI patient. In English. Out loud.](assets/social/og-cover.png)

Source for the public landing page at **https://bedsideenglish.github.io/**.

A single static `index.html` (no build step) presenting both platforms of the product:

- [BedsideEnglish-Desktop](https://github.com/boyskier/BedsideEnglish-Desktop) — Windows/macOS/Linux, available now.
- [BedsideEnglish-Android](https://github.com/boyskier/BedsideEnglish-Android) — pre-launch, build from source.

Served via GitHub Pages from the `main` branch root. Edit `index.html` and push to update the live site.

## Clinical English learning pages

Reviewed patient-case JSON files can be converted into static communication guides under
`learning/`. The publication allowlist and reviewed titles live in `learning-pages.json`; page
markup lives in `tools/learning_templates/` and shared presentation lives in
`learning/styles.css`. No source case JSON is copied into the public site.

Generate the reviewed selection from this workspace on Windows:

```powershell
python tools\generate-learning-pages.py
```

Generate one specific case by ID or path (a neutral ID-based slug is used unless `--slug` is
provided):

```powershell
python tools\generate-learning-pages.py --case gi_011 --slug swallowing-difficulty-history-questions
```

The default case source is the sibling Android repository at
`..\Medvoicetrainer-android-app-version\data\cases`. Override it with `--source-root` when the
workspace layout differs. The generator has intentionally no mass-generation option.

Published manifest entries must include a plain-language quick answer, an editorial update date,
and at least two reviewed wording explanations. `question_edits` can replace or split a source
question and add `Why this wording` comparisons without changing the application's source case.
Each generated page also records the source JSON SHA-256 in an HTML comment, so `--check` catches
stale pages after any source-case change.

Public learning content follows **American English (`en-US`)**, matching the app's USMLE audience.
Every manifest entry must set `language_standard` to `en-US` and confirm
`patient_answer_assumptions_checked`. Generation fails on known British-style patient wording such
as `practise`, `felt sick`, or `open your bowels`, and on presupposition markers such as `each time`
or `you mentioned`. These deterministic checks are a review aid, not a replacement for reading each
question for subtler leading assumptions before publication.

## Healthcare team communication guides

Team-to-team content is managed separately under `communication/`. It uses a chart-to-message model rather than the patient-history question template: every guide includes a fictional source chart, framework steps, a generated complete script, wording contrasts, a receiver check-back, and source-backed editorial notes.

The reviewed publication allowlist is `team-communication-pages.json`. The generator, templates, QA checker, and regression tests live under `tools/`; the complete management and editorial standard is in `docs/team-communication-content-system.md`.

Generate the reviewed team-communication library:

```powershell
python tools\generate-team-communication-pages.py
```

Generate one manifest entry during editing:

```powershell
python tools\generate-team-communication-pages.py --page sbar-nursing-handoff-example
```

Run the publication gate:

```powershell
python tools\test_generate_team_communication_pages.py
python tools\generate-team-communication-pages.py --check
python tools\check-team-communication-pages.py
```

The library includes physician-first examples for an SBAR specialty consult, I-PASS night handoff, and critical-result check-back, plus the original nursing SBAR example. Do not edit generated HTML directly; edit the manifest or templates and regenerate.

## Everyday English interactive listening guides

Everyday-English search pages live under `everyday-english/`. They use a separate hear–commit–verify template rather than the patient-question or team-framework layouts. Each reviewed page maps one search task to one real Android Listening Lab drill, hides the transcript until the learner commits structured detail answers, scores each detail, records replay/slower assistance locally, and then teaches repair and transfer.

The publication allowlist and 15 future-ready speaker profiles live in `everyday-english-pages.json`; published app-drill snapshots live in `everyday-listening-drills.json`. When the sibling Android repository is present, generation requires each snapshot to match the current app drill, so transcript, accepted-answer, difficulty, and profile changes cannot drift silently. Browser speech synthesis is the no-key fallback; reviewed audio added under `assets/audio/everyday/<drill_id>/<profile_id>.*` is picked up automatically.

Run the complete publication gate:

```powershell
python tools\test_generate_everyday_english_pages.py
python tools\generate-everyday-english-pages.py --check
python tools\check-everyday-english-pages.py
```

The full editorial, audio, SEO/GEO, scoring, and QA standard is in `docs/everyday-english-content-system.md`.

### Search discovery on GitHub Pages

This repository is deployed at the GitHub Pages hostname root. Its crawler policy is published at
`https://bedsideenglish.github.io/robots.txt` and points to the sitemap.

Submit `https://bedsideenglish.github.io/sitemap.xml` directly in Google Search Console and Bing
Webmaster Tools.

`android.html` is the structural source for `index.html`. The sync tool preserves the root route's
canonical URLs, brand link, and broader two-track problem statement. After editing `android.html`,
update the root page with:

```sh
python tools/sync-landing-pages.py --write
```

GitHub Actions verifies the two files on every pull request and push to `main`, so an out-of-sync change cannot go unnoticed.

## Assets

| Path | What it is |
| --- | --- |
| `assets/android/*.webp` | Real Android screenshots, 780px wide, Android status bar and gesture strip trimmed off. Used by the practice-loop phone and the screenshot rail. |
| `assets/android/detail/*.webp` | Close-up crops of the same captures. `hero-checklist` and `correction-wide` are cut by `tools/build-crops.py`; the rest are older 760×422 crops. |
| `assets/social/og-cover.png` | 1200×630 Open Graph / Twitter card. Referenced by `og:image` on both pages. |
| `assets/social/feature-graphic.png` | 1024×500 — the exact size Google Play requires for a store listing feature graphic. |
| `assets/social/share-square.png` | 1200×1200 square, for KakaoTalk / Instagram and anywhere a wide card is cropped. |
| `assets/app-*.png` | Older desktop-app screenshots, used only by `desktop/index.html`. |

The three files in `assets/social/` are one composition at three crops. Regenerate them all with:

```sh
python3 tools/build-social.py   # needs Pillow
```

Edit the copy or swap which screenshots appear in the stack at the top of that script — do not
retouch the PNGs by hand, or the three sizes will drift apart.

The hero's magnified checklist and the full-width correction band are straight crops of captures
already in the repo. Re-cut them after replacing either source capture:

```sh
python3 tools/build-crops.py    # needs Pillow
```

### Bed 23 preview audio

`android-demo.html` plays reviewed, pre-generated Gemini TTS clips from
`assets/audio/bed-23/`; the public page does not call Gemini or use a
browser-installed voice. To regenerate a clip locally, set `GEMINI_API_KEY` in
the workspace-level `.env` and run:

```powershell
python tools\generate-bed-23-audio.py
```

Use `--force` when deliberately replacing existing files, and `--clip
patient-opening` to remake one named line. The generator defaults to
`gemini-3.1-flash-tts-preview` and writes 24 kHz mono WAV files.

## Two switches at the top of the page script

Both live at the top of the `<script>` block in `android.html` (and its `index.html` copy):

| Constant | What it does while empty | What to paste in |
| --- | --- | --- |
| `GOOGLE_PLAY_URL` | The public listing URL is already configured. | Keep the published Google Play listing URL here; the status surfaces become download buttons. |
| `VOICE_CLIP_URL` | The hero button replays the silent clip and reads "Watch the 8-second clip". | A path to eight seconds of the encounter's **own** audio. The button becomes "Hear 8 seconds of it" and doubles as a mute toggle. |

`VOICE_CLIP_URL` is deliberately empty rather than wired to speech synthesis. The page's whole claim
is that everything on it is the real app, and a browser text-to-speech voice would be the one thing
on it that is not — it would also sound nothing like the voice the app actually uses. Record it by
screen-capturing an encounter with internal audio capture enabled, then export the audio alone:

```sh
ffmpeg -i encounter.mp4 -ss 0 -t 8 -vn -c:a aac -b:a 96k assets/audio/encounter-8s.m4a
```
