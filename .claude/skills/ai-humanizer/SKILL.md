---
name: ai-humanizer
description: 'Strip AI-writing tells from developer prose — release notes, PR descriptions, commit messages, announcements, README sections, and technical docs — without changing a single fact. Use when asked to humanize text, make writing sound less AI-generated, tighten a release note or PR body, remove chatbot phrasing, or review a draft for tells like "not X but Y", one-line closers, announcement framing, bold-label bullet lists, emoji status markers, em dashes everywhere, triads, inflated significance, or self-narration ("I first checked X, then Y"). Also use when a draft "sounds like AI" or reads like ChatGPT wrote it.'
license: GPL-3.0
metadata:
  version: "1.0.0"
---

# AI humanizer

Rewrite developer-facing prose so it reads like a person wrote it. Keep every fact.
Change only the presentation.

## The rule that governs everything else

**The facts are fixed. Only the wording moves.**

A rewrite may shorten, merge, split, reorder, or restructure. It may not add a
number, name, date, version, benchmark, error string, or claim, and it may not drop
one. If a sentence needs a detail you do not have, ask for it or write a vaguer
sentence — never invent a plausible one.

This matters more here than in general prose. A marketing sentence that overstates is
annoying; a release note that overstates is wrong, and someone will act on it.

**Check every claim against the source.** If the input is a PR body, the source is the
diff. If it is a bug report, the source is the reproduction. If it is release notes,
the source is the commits. A claim you cannot trace is either cut or asked about.

## Scope

Rewrite these:

- release notes, announcements, changelog entries
- pull request descriptions, issue reports, review comments
- commit messages, README and docs prose, code comments that carry reasoning
- replies in threads, where the reader already has the context

Never touch:

- code blocks, inline code, commands, file paths, URLs, and link targets
- YAML frontmatter, JSON, tables of data, and version strings
- error messages, log output, and anything inside quotes that is being reported
  rather than written
- proper nouns, API names, and identifiers, including ones that look wrong
- a deliberate hedge or scope limit. "This may affect accounts created before 2024"
  is information. Leave it.

## Procedure

### 1. Read once, and mark

Read the whole text before changing anything. Mark each tell as you find it.

Look at **paragraph shape**, not only sentences. A contrast split across two
sentences, three examples that all end in a one-line lesson, or the same kind of
closer after every section is the same tell at a larger scale, and it survives
sentence-level cleanup.

### 2. Draft the rewrite

Write the whole thing again rather than patching flagged phrases. Rephrasing one
clause at a time leaves the shape that caused the problem.

Keep every claim. You may cut anything that only says _this matters_. If a paragraph
resists rewriting, find its main point and rebuild around that.

Vary sentence length. Real technical writing alternates short and long, because it
follows the complexity of what it describes rather than a rhythm.

### 3. Verify

Before writing the final version, check in this order:

1. **Facts.** Walk the original and confirm every number, name, date, version, and
   claim is still present and still accurate. Confirm you added none. This is the
   step that catches the errors that matter.
2. **Cut claims.** Ask whether any sentence asserts something happened, changed, or
   was fixed without the source showing it. Announcement framing is the usual cause.
3. **The tells that survive a rewrite.** In practice these are the ones left behind:
   contrast pairs, one-line closers, triads, em dashes, and bold labels. Search for
   them by name.

### 4. Write the final version

State each point once, directly. Do not explain the change to the reader and do not
narrate how you arrived at it.

## Patterns

Ranked by how reliably they indicate AI drafting. Tier 1 justifies an edit on one
sighting. Tier 3 needs company from other tells in the same passage.

The full catalog, with examples for each, is in
[references/patterns.md](./references/patterns.md).

### Tier 1 — act on sight

| Pattern               | Looks like                                                                      | Do                                                              |
| --------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Chat residue          | "Let me know if you'd like more detail", "Great question!", "I hope this helps" | Delete. Keep the content.                                       |
| Announcement framing  | "**The decisive finding:**", "Bottom line:", "The key insight here is"          | State the finding. The reader decides what is decisive.         |
| Self-narration        | "I first checked X, then found Y", "Let me verify that"                         | Report the result. The process belongs in a log, not a summary. |
| Not X but Y           | "This isn't a bug so much as a design gap", "not just faster, but simpler"      | State which one it is.                                          |
| One-line closers      | "That's the finding." "Worth stating plainly." "This matters."                  | Cut, or make the line carry a fact.                             |
| Deep-sounding sayings | "at its core", "the real question is", "what this really shows"                 | Replace with the specific claim.                                |

### Tier 2 — act on two together

| Pattern                          | Looks like                                                            | Do                                                                       |
| -------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Em dashes as a default connector | clause — clause — clause                                              | Use a period, comma, colon, or parentheses, and rewrite where none fits. |
| Forced triads                    | "faster, cleaner, and more reliable"; three examples plus a lesson    | Use as many items as the meaning has.                                    |
| Bold-label bullets               | Every bullet `**Label:** text`                                        | Drop the bold. Use prose when the labels carry no information.           |
| Emoji as status markers          | `✅` / `❌` / `⚠️` on every line                                      | Say "passed", "failed", "unverified".                                    |
| Inflated significance            | "the most instructive one yet", "a real step forward", "worth noting" | Drop it, or name the consequence.                                        |
| Title Case headings              | `## What Changed And Why`                                             | Sentence case.                                                           |
| Writing about the document       | "This section covers…", "The table below compares…"                   | Describe the subject.                                                    |

### Tier 3 — weak alone

| Pattern                            | Looks like                                                                                                                           | Do                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------- |
| Overused words                     | delve, robust, comprehensive, leverage, seamless, crucial, pivotal, landscape, tapestry, testament, showcase, underscore, meticulous | Use the plain word.                 |
| Avoiding _is_ / _has_              | "serves as", "functions as", "boasts", "features"                                                                                    | "is", "has".                        |
| Stacked hedges                     | "it's likely possible this may perhaps"                                                                                              | Keep the hedge the source supports. |
| Hyphenated pairs after the noun    | "the report is high-quality"                                                                                                         | "the report is high quality".       |
| Passive voice and missing subjects | "no config needed", "results are preserved"                                                                                          | Name the actor when it helps.       |
| Repeated sentence openings         | Three sentences starting "This…"                                                                                                     | Merge, or change the subject.       |
| Curly quotation marks              | `“…”` in a plain-text file                                                                                                           | Straight quotes.                    |

## Voice

Technical writing is the neutral register: plain, specific, and free of reaction. Do
not add opinion, humour, or personality to a release note, a changelog, or an API
reference.

If the user supplies a sample of their own writing, that sample overrides this
section and the pattern list both. Match its sentence length, word choice,
punctuation, and habits — including em dashes, if they use them.

## When not to act

Every pattern describes a choice a person can make deliberately. Leave it alone when:

- it sits inside a quotation, a title, a proper name, or a passage that is discussing
  the phrasing rather than using it
- it is a greeting or sign-off on a real message, which predates chatbots
- it carries something that would otherwise be lost: an unusual specific detail, a
  genuine uncertainty, a first-person judgement the writer can explain
- the text predates late 2022, so it is not model prose
- you cannot tell whether the reader already has the context. Ask, or leave it.

One pattern is not enough. Several together is the signal.

## Source

The taxonomy follows Wikipedia's
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing),
maintained by WikiProject AI Cleanup, reinterpreted here for developer prose.
