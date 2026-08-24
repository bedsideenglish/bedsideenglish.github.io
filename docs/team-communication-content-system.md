# Team communication content system

This is the editorial and production guide for English communication between healthcare team members. It is intentionally separate from `learning/`, which teaches patient-facing history questions.

## What this library publishes

Each page should solve one observable communication task, such as giving an SBAR escalation, transferring care with I-PASS, using a check-back, raising a safety concern with CUS, or making a concise consult request.

A publishable guide contains:

1. a direct answer to the target query;
2. a fictional but internally consistent clinical situation;
3. a chart or source-information snapshot;
4. the communication framework mapped to that snapshot;
5. a complete spoken example assembled from the same statements;
6. language contrasts that explain what makes wording clearer;
7. a receiver response and check-back where the task needs closed-loop communication;
8. a pre-call or pre-handoff checklist;
9. common failures and repairs;
10. short query-shaped questions and answers;
11. authoritative sources, dates, and a visible clinical boundary.

This structure makes the page useful to a human reader and easy for search or answer systems to extract without hiding the main content in tabs or JavaScript.

## Publishing flow

```text
Topic backlog
  → search task and reader outcome
  → authoritative source pack
  → fictional chart facts
  → spoken framework draft
  → automated generation and blocking QA
  → language + source + local-policy boundary review
  → publish
  → Search Console / Bing citation monitoring
  → refresh or retire
```

Use these statuses outside the public manifest: `idea`, `sourced`, `drafted`, `review`, `published`, and `refresh-due`. Only reviewed entries belong in `team-communication-pages.json`; that file is the publication allowlist, not the idea backlog.

Recommended ownership:

| Responsibility | Minimum review |
| --- | --- |
| Search task and page brief | Content/SEO editor |
| Framework definition and source claims | Clinically informed reviewer against primary or authoritative guidance |
| Spoken English and phrase contrasts | US English language editor |
| Fictional chart coherence and boundary | Clinical/editorial reviewer |
| Build, metadata, structured data, links | Automated checks plus technical owner |

## Files and commands

| File | Purpose |
| --- | --- |
| `team-communication-pages.json` | Reviewed source of truth and publication allowlist |
| `tools/team_communication_templates/page-manifest-template.json` | Copyable editorial record skeleton |
| `tools/team_communication_templates/page.html` | Detail-page HTML template |
| `tools/team_communication_templates/index.html` | Library hub template |
| `communication/styles.css` | Separate presentation system for team communication |
| `tools/generate-team-communication-pages.py` | Deterministic generator and manifest-level blocking checks |
| `tools/check-team-communication-pages.py` | Output, metadata, JSON-LD, link, safety, and sitemap QA |
| `tools/test_generate_team_communication_pages.py` | Regression tests for the generator contract |

Generate all reviewed entries:

```powershell
python tools\generate-team-communication-pages.py
```

Generate one reviewed entry while editing:

```powershell
python tools\generate-team-communication-pages.py --page sbar-nursing-handoff-example
```

Run the full gate before publishing:

```powershell
python tools\test_generate_team_communication_pages.py
python tools\generate-team-communication-pages.py --check
python tools\check-team-communication-pages.py
```

Do not edit files under `communication/<slug>/` or `communication/index.html` directly. The next generator run will replace them.

## Editorial record design

### Search brief

`search.primary_query` names the one task the page solves. It must appear naturally in the title or H1. `supporting_queries` are coverage prompts, not a list to repeat. `reader_task` is the success condition: what the reader can prepare or say after using the page.

Create one strong page for a real task. Do not create near-duplicate pages for every keyword permutation, job title, or acronym expansion.

### Fictional chart facts

Every fact has a stable `id`, visible label/value, chart group, and priority. `must` facts must be referenced by at least one spoken statement or generation fails. This catches the common failure where a chart highlights a critical change that disappears from the verbal handoff.

The chart values and spoken statements should be reviewed together for numerical and temporal consistency. Automation checks reference coverage; a human must still catch contradictions in paraphrases.

### Framework steps

Each SBAR page must have exactly four steps in standard order. Every statement references the fact IDs it communicates. The complete example is assembled from these statements, so the step-by-step script and full transcript cannot drift apart.

Each step also requires a plain prompt, a reason the wording works, a `less_clear`/`preferred` contrast, and an explanation tied to clarity, ownership, urgency, or cognitive load.

### Sources and review attestations

Use at least two primary or authoritative sources. Prefer current official framework owners, public health or safety agencies, professional standards bodies, and original guidance. Secondary articles may help with discovery but should not be the evidence base for a clinical communication claim.

All five `review` values are blocking attestations. Set them to `true` only after checking:

- each framework and safety claim against the listed sources;
- that the case is visibly and consistently labeled fictional;
- that the page defers to local policy, scope, escalation, and supervision;
- that US English is natural when spoken aloud;
- that the page fully satisfies the named search task.

## Blocking automated QA

Generation stops for unknown/missing fields; invalid slugs, dates, URLs, lengths, or SBAR order; duplicate fact IDs; a `must` fact absent from speech; insufficient queries, FAQs, repairs, or sources; unchecked attestations; selected non-US spelling; or an absolute safety claim.

Output QA also blocks unresolved markers, broken links, malformed nesting, duplicate IDs, missing image alt text, incomplete metadata, mismatched structured data, missing safety boundaries, sitemap errors, and generated directories outside the allowlist.

Automation does not approve clinical appropriateness, institution-specific escalation, realistic scope of practice, or subtle contradictions. Those remain review responsibilities.

## Human editorial QA

Read the complete script aloud and answer all of these before publication:

- Can the receiver identify the patient, current change, and requested response in the first listening?
- Is urgency stated with evidence rather than intensifiers or vague claims such as “doesn't look good”?
- Does Background contain only context that changes interpretation or action?
- Are observations separated from the caller's assessment?
- Does Recommendation name an action, timing, owner, and contingency where relevant?
- Does the receiver have an opportunity to ask, clarify, and confirm?
- Are all numbers, times, medications, allergies, pronouns, and patient identifiers consistent?
- Could a reader mistake the example for patient-specific advice or a universal protocol?
- Are abbreviations understandable to the intended audience when first introduced?
- Does each paragraph do one job and remain readable on a narrow screen?

## SEO and generative-answer quality rules

The system uses the same foundation for conventional and generative search:

- Put a self-contained answer immediately after the H1 and lede.
- Use descriptive headings and stable fragment IDs so specific passages can be linked.
- Keep essential content visible in static HTML.
- Make the worked chart, fact-to-script mapping, phrase contrasts, and receiver response the original value of the page.
- Keep title, H1, description, visible answer, social metadata, and structured data aligned to one task.
- Use `Article`, `LearningResource`, and `BreadcrumbList` only for visible or verifiable properties. There is no special GEO schema.
- Link claims to authoritative sources and show access/review dates.
- Avoid filler, keyword repetition, mass-produced variants, invented expertise, and unsupported outcome claims.
- Keep internal links among the homepage, patient library, team hub, and related task pages.
- Add every canonical URL once to the sitemap and allow crawling in `robots.txt`.

Official production references include [Google's AI feature guidance](https://developers.google.com/search/docs/appearance/ai-features), [Google's generative AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide), [structured-data guidelines](https://developers.google.com/search/docs/appearance/structured-data/sd-policies), and [Bing's AI Performance reporting](https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview).

## Measurement and refresh

Review a published guide at least every six months, and sooner when a source, framework, local-policy boundary, product claim, or search intent changes.

Track indexed versus submitted URLs; search impressions, clicks, and query-task fit; page-level citations and grounding queries in Bing Webmaster Tools; anchored-section entrances; source-link health; and next-guide/app engagement that does not weaken the educational answer.

Refresh a page when sources change, queries reveal an unmet task, a cited section lacks context, or the receiver response needs clarification. Retire or redirect duplicate pages.

## Recommended next guides

Build depth across different jobs before creating close variants:

1. I-PASS shift handoff with a to-do list and contingency plan;
2. check-back and repeat-back for verbal orders or critical values;
3. CUS and the two-challenge rule for raising a safety concern;
4. concise specialty consult request with a focused clinical question;
5. team huddle language for workload, priorities, and role assignment;
6. discharge or transfer handoff between units, including ownership confirmation.

Each should have its own source-backed structure. Do not force every communication framework into the SBAR page shape.
