# Oral case-presentation content system

This system turns one reviewed simulated patient JSON file into one deliberately edited, source-locked clinical English guide under `case-presentations/`. It does not mass-publish case files and it does not treat the source JSON's reference SOAP note as finished public copy.

## Why this is a separate library

Patient-history guides teach questions asked to a patient. Team-communication guides teach a consult, handoff, or closed loop between clinicians. An oral case presentation has a different job: compress a patient story into a prioritized clinical argument for a supervisor. Its basic sequence is:

1. opening one-liner;
2. history of present illness;
3. relevant background;
4. objective data;
5. assessment with ranked reasoning;
6. plan and immediate priorities.

The order is a teaching default, not a universal protocol. Acuity, service, audience, learner level, and supervisor preference can change the length and order.

## Files and ownership

| File | Role |
| --- | --- |
| `case-presentation-pages.json` | Reviewed publication allowlist and editorial source of truth |
| `tools/generate-case-presentation-pages.py` | Source loading, validation, rendering, and stale-output check |
| `tools/case_presentation_templates/` | Hub, detail-page, and starter-manifest templates |
| `case-presentations/styles.css` | Presentation-library visual system |
| `tools/check-case-presentation-pages.py` | Output, metadata, link, provenance, and sitemap QA |
| `tools/test_generate_case_presentation_pages.py` | Regression tests for safety and source-locking rules |

Generated HTML is not edited directly. Change the manifest or templates and regenerate.

## Publication workflow

1. Select one patient case whose main JSON has completed clinical QA. Prefer a common, well-bounded presentation task with enough history or results to demonstrate prioritization.
2. Read the complete source JSON, its clinical QA record, and its current authoritative clinical source. Do not rely only on `reference_soap` or `teaching.one_liner`.
3. Copy `tools/case_presentation_templates/page-manifest-template.json` into a new manifest entry.
4. Create a fact ledger. Each fact has a stable ID and a dotted path into the source JSON. Use the narrowest scalar path that supports the claim.
5. Define the presentation moment. State exactly which history, tests, or results are available at that moment.
6. Draft the six spoken sections. Every section must cite one or more fact IDs. Put reasoning in the assessment; do not disguise it as observed data.
7. Add at least two known gaps. The generator verifies that every claimed-missing JSON path is actually absent.
8. Add clinical-compression decisions, likely supervisor questions, wording contrasts, a checklist, common repairs, and brief FAQs.
9. Check every clinical claim against current primary or authoritative sources. Use direct guideline or medical-school teaching URLs rather than search-result URLs.
10. Read the complete script aloud at a natural pace. Edit for breath length, sequence, transitions, and pronunciation. Do not optimize for memorization.
11. Set every review attestation to `true` only after its review has been performed.
12. Run the publication gate:

```powershell
python tools/test_generate_case_presentation_pages.py
python tools/generate-case-presentation-pages.py
python tools/generate-case-presentation-pages.py --check
python tools/check-case-presentation-pages.py
python tools/check-ga4.py
```

The default source root is the sibling Android repository at `..\Medvoicetrainer-android-app-version\data\cases`. Use `--source-root` when the workspace layout differs. Generate one page during editing with `--page <slug>`.

## AI authoring guide

Another AI may help draft a candidate only if it follows this sequence:

### 1. Establish evidence before prose

- Read the full patient JSON and list source paths for every candidate fact.
- Separate patient-reported history, objective results, source clinical knowledge, and editorial inference.
- Treat missing vital signs, examination, allergies, medication adherence, and tests as unknown—not normal.
- Compare the current JSON hash and content with the existing generated-page provenance before revising a page.

### 2. Define the communication task

- Name the moment: after history only, after initial results, or during a follow-up round.
- Name the listener and what decision they need to make.
- Choose a realistic target duration. A short presentation still includes the information needed for safety.
- Use American English (`en-US`) for public copy; expand dosing abbreviations when spoken.

### 3. Draft as clinical compression

- Opening: age, person, relevant substrate or risks, acute problem, and time course.
- HPI: discriminating positives and meaningful negatives in a coherent chronology.
- Background: only comorbidities, medications, exposure, and social facts that change interpretation or action.
- Data: exact test, value, unit, timing, trend, and relevant location such as ECG leads.
- Assessment: one ranked leading diagnosis, the evidence for it, and a short prioritized differential.
- Plan: immediate priorities and information still needed, with contraindication and local-policy boundaries.

Do not announce headings in the final script. Do not paste a SOAP note into speech. Do not create a polished exam, vital signs, allergy list, or result that the source does not provide. Do not state certainty beyond the evidence. Do not make treatment unconditional when allergies, contraindications, severity, organ function, or local guidance matter.

### 4. Add original teaching value

For each page, add all of the following rather than publishing a generic disease summary:

- an uninterrupted model script;
- six annotated sentence jobs;
- less-clear versus preferred wording with a reason;
- an explicit unknown-data section;
- a chart-compression table explaining what leads, stays, compresses, or is omitted;
- likely supervisor questions with direct, evidence-based answers;
- a read-aloud checklist and repair examples.

### 5. Perform the final audit

Answer each question with evidence before marking the manifest review complete:

- Can every patient-specific claim be traced to a fact ID and JSON path?
- Are observed data, patient report, and clinical inference linguistically distinct?
- Does the leading diagnosis follow from the supplied data?
- Are dangerous alternatives prioritized rather than dumped into a long list?
- Are unknowns explicit and free of invented reassurance?
- Does the plan respect missing contraindications, local protocol, and scope?
- Can a listener reconstruct the patient, time course, main evidence, assessment, and next step after one hearing?
- Is the script natural when read aloud, with manageable sentence length and no unexplained shorthand?
- Does the page answer its named search task immediately and offer value beyond a generic disease summary?
- Are title, H1, description, direct answer, visible page, social metadata, and structured data aligned?

If any answer is no or uncertain, do not publish. Leave the attestation false and record what needs human review.

## Automated blocking rules

Generation blocks invalid or duplicate slugs and ordering, unexpected fields, missing source cases, a mismatched case ID, fact paths that do not resolve to source scalars, unknown fact references, missing source result numbers in the objective-data section, unsupported section order, fake missing-data claims, weak supporting sections, unchecked review attestations, selected non-US wording, absolute diagnostic claims, invalid dates, and non-HTTPS citations.

Output QA blocks stale source hashes, generated directories outside the allowlist, missing or duplicated GA4, mismatched canonical/social/structured metadata, missing headings or fragments, broken internal links, missing visible source links, absent educational boundaries, and sitemap drift.

Automation is not clinical approval. It cannot detect a subtly misleading inference, a clinically unrealistic sequence, an inappropriate plan, an unhelpful omission, or language that sounds awkward when spoken.

## SEO and generative-search standard

The page is designed for a human learning task first. Google's generative-search guidance says that GEO uses the same foundation as SEO: crawlable, helpful, non-commodity, people-first content. Accordingly:

- answer the named query directly after the H1;
- keep the worked script and explanations visible in static HTML;
- use a concise unique title, description, canonical URL, descriptive headings, and stable fragment IDs;
- publish original chart-to-speech decisions and uncertainty handling rather than many shallow disease variants;
- use `Article`, `LearningResource`, and `BreadcrumbList` only for visible, verifiable properties;
- show source titles, publishers, access dates, publication date, review date, and source-case provenance;
- connect the homepage, hub, related learning libraries, and sitemap;
- do not add keyword lists, hidden text, unsupported FAQ rich-result claims, `llms.txt` promises, or “GEO hacks.”

Editorial references: [Google generative AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide), [helpful content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content), [title-link guidance](https://developers.google.com/search/docs/appearance/title-link), and [snippet guidance](https://developers.google.com/search/docs/appearance/snippet).

## Refresh and incident review

Review each published page at least every six months, and sooner when its patient JSON, clinical source, local-boundary language, search intent, or product claim changes. The generated HTML records the source case ID and SHA-256. `--check` makes a source change visible even when the public wording still renders.

If a factual or safety problem is found, preserve the case ID, old source hash, affected section, guideline version, and corrective rationale in the commit or issue record. Regenerate, rerun every gate, and reread the entire script rather than patching the generated HTML.
