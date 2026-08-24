# Everyday English interactive content system

Updated: 2026-08-24

This library turns reviewed app Listening Lab drills into public, search-discoverable guides. It is intentionally separate from `learning/` patient-history guides and `communication/` team frameworks.

## Product and search position

Do not publish a generic phrase farm. Every guide must connect a real search task to the product's distinctive learning loop:

`hear → commit → verify → repair → transfer`

The page must fully answer the reader's question before asking for a download. Its original value comes from a scored exact-detail task, an honest assistance record, a situation-specific repair ladder, and transfer into new settings. The app remains the next step because it turns the fixed task into a live conversation that answers back.

The 2,637 Survival situations are source material, not 2,637 page ideas. Publish one guide for one reusable interaction task. Do not create near-duplicate pages for every setting, accent, occupation, or keyword permutation.

## Published files

| File | Purpose |
| --- | --- |
| `everyday-english-pages.json` | Reviewed publication allowlist, editorial content, and 15 future-ready speaker profiles |
| `everyday-listening-drills.json` | Minimal reviewed snapshots of the exact app drills published on the web |
| `tools/everyday_english_templates/page.html` | Interactive detail-page template |
| `tools/everyday_english_templates/index.html` | Library hub template |
| `tools/generate-everyday-english-pages.py` | Source-linked deterministic generator and manifest validation |
| `tools/check-everyday-english-pages.py` | Output, metadata, interaction, source-parity, link, image, and sitemap QA |
| `tools/test_generate_everyday_english_pages.py` | Generator and scoring regression tests |
| `everyday-english/styles.css` | Presentation system independent from patient and team guides |
| `everyday-english/listening-lab.js` | Browser audio, commit-before-reveal, scoring, assistance, and local progress logic |
| `assets/social/everyday-listening-og.png` | 1200×630 social preview for the hub and current sample |

Generated output lives under `everyday-english/<slug>/` and `everyday-english/index.html`. Do not edit generated HTML directly.

## Source-of-truth relationship with the app

Each page names one `source_drill_id`. The website repository keeps only published, reviewed drill snapshots in `everyday-listening-drills.json`, so its CI remains reproducible without cloning the private/current app repository. When the sibling Android repository is available, generation also requires each public snapshot to equal the current app record exactly.

The snapshot contains only the fields required by the public exercise:

- context and transcript;
- difficulty and category;
- detail keys, labels, and accepted answers;
- receptive tags;
- permitted accent/profile IDs.

The generated page records a SHA-256 of that exact drill. `--check` rerenders against the reviewed snapshot, while the optional local app parity gate catches a transcript, accepted-answer, label, or profile change before publication.

Editorial explanations, search intent, examples, mistakes, FAQs, and transfer prompts remain in the public manifest. Teaching examples must not reveal the source drill's scored answers before the learner commits.

## Audio architecture

### Current public fallback

The first sample uses the browser's Speech Synthesis API. It needs no API key and sends no answer or microphone recording to Bedside English. The selected profile is matched to the closest English BCP-47 voice installed on the device.

Browser voices vary by operating system and browser. Therefore the UI must say which voice was selected and must never claim that a regional profile was reproduced when only a generic English fallback was found.

### Reviewed audio added later

Speaker profiles in `everyday-english-pages.json` include:

- a stable profile ID shared with the app;
- a human-facing label;
- browser language candidates;
- a future TTS prompt.

To replace browser TTS with pre-generated audio, add one reviewed file using this convention:

```text
assets/audio/everyday/<drill_id>/<profile_id>.mp3
```

The generator also recognizes `.m4a`, `.wav`, and `.ogg`. It automatically adds existing files to `audio_sources`; the web interaction prefers them and otherwise falls back to a browser voice. Slow playback reuses the same audio with pitch preservation where the browser supports it.

Generate these files offline with a maintainer-controlled Gemini TTS key, review the actual clip, then commit it. Never put a provider API key in public HTML or client JavaScript. The desired operation is **TTS** (creating the prompt audio), not STT. STT would be relevant only if a later exercise records and transcribes the learner's spoken response.

OpenAI transcription also requires authenticated API usage and is not available anonymously from this static page. If it is added later, use a server-side credential or short-lived client token flow; never expose a standard API key in browser code.

Accent and race are not interchangeable. Content and code must describe regional or first-language-influenced speech profiles, avoid ethnic stereotypes, and avoid promising that prompted synthetic speech is an authentic representation of a community.

## Interaction contract

A page is publishable only when all of these hold:

1. The context is visible before playback, but the scored transcript and answers are not.
2. Play and repeat default to 1.5× speed; the normal-speed option is keyboard-accessible and announced to assistive technology.
3. The learner commits at least one structured detail before reveal.
4. Scoring happens once against the committed answer; later edits cannot change it.
5. Every detail receives its own correct/incorrect result and accepted examples.
6. Negated values, uncertain answers, and alternative lists do not receive credit merely because they contain the correct token.
7. Replay and normal-speed playback are recorded as assisted repair, not described as failure.
8. The transcript appears only after scoring.
9. A fresh retry resets the exercise without deleting previous device-local attempts.
10. Progress storage is device-local and bounded to the 20 most recent attempts.

The web version intentionally uses structured fields. This prevents relation reversals such as entering one person's amount under another person's label, which a single free-text answer makes harder to score safely.

## Page structure

The template is designed around the reader's task, not the patient-question template:

1. query-shaped H1 and concise lede;
2. self-contained quick answer;
3. interactive hear–commit–verify lab;
4. audio-source disclosure;
5. repeat → confirm → read-back response ladder;
6. decision map based on how much was heard;
7. annotated complete repair dialogue using values different from the scored clip;
8. common failures and repairs;
9. transfer prompts in three different settings;
10. short FAQs;
11. contextual app CTA and visible editorial boundary.

Keep the practice close to the top, but do not weaken the direct answer. The page must remain useful when audio or JavaScript is unavailable.

## Editorial workflow

Use non-public backlog statuses: `idea`, `query-checked`, `drill-mapped`, `drafted`, `interaction-review`, `published`, `refresh-due`, and `retired`. Only reviewed entries belong in `everyday-english-pages.json`.

```text
Search task
  → reusable interaction skill
  → reviewed app drill
  → answer + repair draft
  → generator and blocking QA
  → listen/read-aloud/mobile review
  → publish
  → Search Console + Bing AI citation review
  → expand, refresh, or retire
```

Minimum human review:

- listen to every approved audio profile actually published;
- read all response phrases and dialogues aloud in US English;
- confirm the teaching examples do not disclose scored answers;
- try blank, correct, wrong, negated, uncertain, and alternative-list answers;
- complete the exercise with keyboard only and on a narrow screen;
- confirm that the page answers its named search task without requiring the app.

## Blocking QA

Generation blocks invalid dates, slugs, metadata lengths, missing search fields, duplicate source drills, unknown voice profiles, non-US spelling, race-based profile descriptions, underspecified sections, or unchecked attestations.

Output QA blocks stale Google Play review copy, missing metadata, broken links, malformed JSON-LD, missing interaction IDs, source transcript/detail/profile drift, a visible pre-commit transcript, missing social art, wrong social-art dimensions, unknown audio profiles, missing reviewed audio files, and sitemap omissions.

Automation cannot certify whether a synthetic accent sounds authentic or whether a phrase is socially natural in every setting. Those remain human review responsibilities.

## Commands

From `bedside-english/`:

```powershell
python tools\generate-everyday-english-pages.py
python tools\generate-everyday-english-pages.py --page ask-again-and-confirm-details
python tools\test_generate_everyday_english_pages.py
python tools\generate-everyday-english-pages.py --check
python tools\check-everyday-english-pages.py
```

## SEO and generative-search rules

- The quick answer must stand on its own and align with title, H1, description, social metadata, and structured data.
- Important teaching content stays in static HTML; JavaScript owns only the exercise state.
- Use stable section IDs and descriptive headings.
- Use `Article`, `LearningResource`, `CollectionPage`, `ItemList`, and `BreadcrumbList` only for visible or verifiable properties.
- There is no special GEO schema or required `llms.txt` file.
- Do not create pages for every query variation, drill, speaker profile, or scenario.
- Original value must come from the scored task, repair logic, annotated example, and transfer—not keyword repetition.
- Keep internal links among the everyday hub, patient guides, team guides, landing pages, and Google Play listing.
- Refresh a page when its app drill, scoring contract, audio, search intent, product claim, or language review changes.

## Pilot decision rule

Keep the first release to the hub and one gold-standard guide. After the template is stable, expand to no more than six guides before reviewing performance.

Track:

- indexed versus submitted URLs;
- non-brand queries and whether they match the named reader task;
- page-level search clicks;
- Bing citation counts and grounding queries;
- guide-to-app and Play Store acquisition signals when attribution is available;
- failure and assistance patterns only when collected with an explicit privacy-preserving design.

Expand the interaction cluster only when its pages attract relevant queries or citations and produce a qualified product signal. Do not use raw impression volume as the sole success criterion.
