# Instagram card system

The authoring standard for the carousels in `assets/instagram/`. It covers what a
card may say, and — the part that decides whether anyone reads it — how the first
slide is built.

## What a card may say

A card is the most quotable thing this project publishes, so it inherits the
site's editorial gate rather than working around it.

- **The card manifest cannot contain clinical wording.** `instagram-cards.json`
  carries slide selection, hook framing, and caption copy. Every clinical English
  sentence on a slide is pulled by field reference out of a published guide.
- **Selection is editorial; wording is not.** Choosing which four steps or which
  five questions become slides is the manifest's job. Rewording them is nobody's.
- **A card can only cut from a published guide.** If the guide is not in the
  site's allowlist, it cannot become a card.
- **Editing a guide invalidates the cards cut from it.** Each card records the
  source page fingerprint; the checker fails when they diverge.
- **Authored copy makes no clinical claim.** The hook may promise better wording.
  It may not promise a clinical outcome.

## The hook

Roughly half the people who see a carousel decide on slide one whether to swipe.
Everything below is about that slide.

### Lead with the artifact, not the argument

The first draft of the SBAR card opened with *"Your English is fine. Your handoff
isn't."* It is a tidy line and it is the wrong move: it states the thesis of the
carousel. A thesis invites disagreement, and it makes the viewer the audience of
an argument.

An artifact does not. Put a real sentence on the slide — one the viewer has said
out loud, quoted verbatim from the guide — and they convict themselves in their
own words before they have decided to read anything:

> "I just wanted to let you know."

This has a second benefit that matters more than the copywriting: when the hero
of the hook is a source quote, the hook itself is inside the editorial gate
instead of floating outside it as marketing.

### The consequence is a scene, not a judgment

Under the artifact goes one line naming what happens next. Not *this is unclear*
— a judgment the viewer can shrug off — but the moment they have lived:

> Nobody comes.

Three rules for it: present tense, a human actor, and something the viewer has
personally experienced. If the consequence could be printed in a textbook, it is
the wrong line.

### Never lead with the framework

SBAR, I-PASS, OLD CARTS. Naming the framework on slide one filters out exactly
the people who need the card, and signals *lecture* to everyone else. The
framework can appear from slide two onward, where it now reads as the answer.

### Keep authored copy under about eight words

The quote does the work. Long hook copy is a symptom of a hook that does not
trust its artifact.

### The loop closes in one swipe

A hook that opens a vague loop ("here's what most people get wrong") is a
promise the carousel cannot pay off in one slide. A hook built on one specific
sentence implies exactly one missing sentence, and slide two hands it over.

## Four hook moves

The libraries differ in what makes their content hurt, so the artifact differs.
All four are artifact-first.

| Library | The move | Hero | Consequence |
| --- | --- | --- | --- |
| `team-communication` | **The incriminating quote.** Colleague-to-colleague, there is a wrong version and the reader has said it. | The guide's `less_clear` phrasing | What the receiver does not do |
| `learning` | **The jargon trap.** Doctor-to-patient, neither phrasing is wrong — but one uses a word the patient does not have. | The guide's clinical-term alternative | Why the answer cannot be trusted |
| `model-interview` | **The decision point.** A live encounter has no single wrong line, so the hook is a question the reader answers in their head. | The patient card, verbatim | The question, asked of the reader |
| `case-presentation` | **The fact nobody needs.** The skill is compression, so the hook is a true chart fact that still does not belong in the presentation. | A `compression` entry's `source_detail` | That it should not be said |

`case-presentation` differs from the others in what a slide even contains.
Elsewhere a slide holds speech; here it holds a chart fact and the guide's
verdict on it — Lead, Include, Compress, or Omit — so neither half takes quote
marks, and the verdict is set as a stamp because it is the lesson. The
vocabulary is mirrored from the guide generator, so a typo in a verdict fails
rather than being printed onto a card.

The `learning` move needs care. Its alternatives are labelled options, not errors
— the guides say so — and marking one with a cross would be a lie about the
source. Those slides carry the guide's own labels instead of ✗ and ✓, and the
consequence line may describe only what the source supports about the wording,
never a claim about what a patient will do.

## Slide order

Hook, then one contrast per selected item, then the connected script, then the
call to action. At most ten slides, which is Instagram's carousel limit.

The script slide is the one people screenshot, so it holds the preferred lines
in sequence and nothing else. The call to action goes last and asks once.

## Compilations beat single guides

A carousel wants four or five instances of one pattern, and a single guide often
holds one or two. The strongest `learning` card is not one page cut five ways; it
is one pattern — the clinical word the patient does not have — collected across
five pages. Cards may therefore reference items from several guides at once, and
the fingerprint check covers every guide referenced.
