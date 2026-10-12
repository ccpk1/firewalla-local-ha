# Pattern catalog

Every pattern below is a default choice a model makes when it writes for the widest
possible reader instead of for one specific reader. The tell is not the words. It is
that the choice was made by rule rather than because the meaning asked for it.

Each entry gives what to look for, why it reads as machine-written, and a rewrite that
keeps every fact.

---

## A. Staging instead of stating

The sentence signals that something matters rather than adding something that does.

### A1. Not X but Y

**Look for:** not X but Y; not just / not only / not merely X, but Y; it's not X, it's
Y; X rather than Y; the same contrast split across two sentences ("This does not mean
X. It means Y."); a negative tail clipped onto the end ("…, no guessing").

**Why:** The negative half names something nobody claimed, which makes the positive
half sound larger than it is. It adds emphasis without adding information.

**Keep it** when the negative half corrects a belief the reader actually holds, or
when both halves carry a fact.

> **Before:** The retry loop isn't a workaround for slow uploads — it's a correctness
> fix. Without it, a partial write can be committed twice.
>
> **After:** The retry loop prevents a partial write from being committed twice.

> **Before:** This does not mean the identifier is unstable. It means the identifier
> is assigned lazily, on first write.
>
> **After:** The identifier is assigned lazily, on first write.

> **Before:** The selector resolves from the entry, no guessing.
>
> **After:** The selector resolves from the config entry without requiring the caller
> to guess.

### A2. One-line closers and dramatic fragments

**Look for:** a one-sentence paragraph that restates the one before it; "That's the
finding.", "That distinction matters.", "Worth stating plainly.", "This matters
because…"; the same kind of closer after several sections; a sentence after an example
that names what it showed ("This shows why the check matters."); a run of fragments
("No retries. No backoff. No mercy.").

**Why:** The line asks the reader to pause on a claim instead of advancing the
argument. It is emphasis pretending to be content.

**Keep it** when the short sentence carries a new fact. A one-line paragraph can be
the right choice.

> **Before:** The cache key excludes the locale.
>
> That's the bug.
>
> **After:** The cache key excludes the locale, so two locales share one entry.

> **Before:** Retries hide brief outages.
>
> That is the real win.
>
> Sessions survive a restart.
>
> That is the real win.
>
> **After:** Retries hide brief outages, and sessions survive a restart.

### A3. Sayings that sound deep

**Look for:** at its core, in reality, what really matters, fundamentally, the deeper
issue, the real question is, the heart of the matter, X is the Y of Z, X becomes a
trap, X is not a tool but a mirror, the language of, the currency of, the architecture
of.

**Why:** An ordinary technical point is dressed as a hidden truth. The dressing adds
nothing you can act on.

> **Before:** At its core, the question is whether the queue can drain faster than it
> fills. What really matters is backpressure.
>
> **After:** The queue drains only if it empties faster than it fills, which depends on
> whether producers back off when it is full.

### A4. Staged run-up before the point

**Look for:** Let's dive in, let's explore, here's what you need to know, now let's look
at, without further ado, quick note, heads up, here's the thing, the thing is, real
talk, and process narration such as "I first checked X, then found Y".

**Why:** The writer announces the point instead of making it. In a summary, the run-up
is pure overhead: the reader wants the answer first.

**Keep it** when the sentence genuinely orients a long document, such as a scope note
at the top of a design doc.

> **Before:** Let's dive into why the migration failed. Here's what you need to know.
> The foreign key was dropped before the backfill ran.
>
> **After:** The migration failed because the foreign key was dropped before the
> backfill ran.

> **Before:** I checked the logs first, then the config, and finally found it. The
> timeout was 30 seconds, but the upstream takes 45.
>
> **After:** The timeout is 30 seconds and the upstream takes 45, so every request
> times out.

### A5. Arguing with no one

**Look for:** I'm not saying, to be clear, don't get me wrong, this is not to say,
some might argue, a tempting approach would be, one might be tempted to, you might
think… but, it would be easy to just.

**Why:** The text answers an objection or rejects an option that appears nowhere else,
usually left from an earlier draft. The defense costs a sentence and defends nothing.

**Keep it** when the objection is one the reader would actually raise, and when you
answer it in full.

> **Before:** This isn't mainly about prompt length, and I'm not arguing that
> documentation doesn't matter. The issue is whether the agent can use the
> instruction when it acts.
>
> **After:** The issue is whether the agent can use the instruction when it acts.

> **Before:** Session tokens rotate every 24 hours. A tempting approach would be to
> restart the auth service on a cron job, but that would drop every active session.
> Rotation happens in place.
>
> **After:** Session tokens rotate in place every 24 hours, so active sessions
> survive.

### A6. Announcement framing

**Look for:** a bolded or headed label that announces the verdict on the content
that follows — "**The decisive finding:**", "Bottom line:", "The key insight here is",
"**TL;DR**" on a short text, "The important part:".

**Why:** It tells the reader how to feel about the finding before they read it, and it
is a judgement the text cannot support. In technical writing it also buries the
finding under a label.

> **Before:** **The decisive problem:** the annotation defaults are the least safe
> case, so every tool must declare all four explicitly.
>
> **After:** The annotation defaults describe the least safe case, so every tool
> declares all four explicitly.

---

## B. Rhythm by rule

Punctuation and structure applied the same way everywhere, regardless of meaning.

### B1. Em dashes as the universal connector

**Rule:** the rewrite must not contain em dashes (—) or en dashes (–) used as dashes
unless the writer's own sample uses them, in which case match that rate.

**Why:** A dash lets the writer skip deciding how two clauses relate. Because many
careful writers also use dashes, a single dash is weak evidence. A document where most
sentences contain one is not.

Leave dashes alone inside code, paths, URLs, and quoted material.

> **Before:** The new policy — announced without warning — affects every account
> created before 2024. The changes -- long overdue -- take effect immediately.
>
> **After:** The new policy affects every account created before 2024. It was announced
> without warning and takes effect immediately.

### B2. Forced triads

**Look for:** three items where the meaning has two or four; three parallel examples
that all land on the same lesson; three adjectives where one is doing the work
("fast, reliable, and scalable").

**Why:** Ideas arrive in threes to sound complete. The third item is usually padding,
and readers can tell.

**Keep three** when there are genuinely three distinct things.

> **Before:** The change makes deployment faster, safer, and more reliable. Teams gain
> simplicity, clarity, and confidence.
>
> **After:** The change makes deployment faster. Rollback is now a single command.

> **Before:** A job can start on time and fail. A retry can succeed and corrupt. A
> migration can finish and lose rows. These failures rarely announce themselves.
>
> **After:** A job can start on time and still fail, or a migration can finish and
> still lose rows. These failures rarely announce themselves.

### B3. Repeated sentence openings

**Look for:** three or more consecutive sentences starting with the same subject,
often "This", "It", or a proper noun.

**Why:** Repetition handled by rule rather than by ear. It reads as a list that was
never converted into prose.

**Keep it** when the repetition is deliberate for rhythm, which is rare and obvious.

> **Before:** The parser reads the header. The parser reads the body. The parser
> discards both if the header is malformed.
>
> **After:** The parser reads the header and body, then discards both if the header is
> malformed.

### B4. Stacked qualifiers

**Look for:** could potentially, might arguably, it's also possible that, in some cases
it may, this is likely an inference, to be fair.

**Why:** Repeated editing adds one hedge after another until every claim sounds
uncertain. Usually it repairs an earlier overstatement rather than reporting real
doubt.

**Keep** the hedge the source supports, and keep scope statements and safety notes.

> **Before:** It could potentially possibly be argued that the patch may have some
> effect on memory use.
>
> **After:** The patch reduces memory use.

### B5. Hyphenated pairs after the noun

**Look for:** high-quality, well-documented, long-term, real-time, read-only used after
the noun they describe.

**Why:** Compound modifiers keep their hyphen wherever they sit. Standard practice
hyphenates before the noun and not after.

**Always hyphenate** words the dictionary spells with one, such as third-party and
read-only.

> **Before:** The report is high-quality and the process is well-documented.
>
> **After:** The report is high quality and the process is well documented.

### B6. Passive voice and missing subjects

**Look for:** "No configuration file needed", "The results are preserved
automatically", "Errors are surfaced to the caller".

**Why:** The text hides who acts. In instructions and API docs this costs the reader
the one thing they need, which is who does what.

**Keep passive** when the actor is unknown, irrelevant, or obvious.

> **Before:** No configuration file is needed. Results are preserved automatically.
>
> **After:** You do not need a configuration file. The system preserves results
> automatically.

---

## C. Inflation and borrowed authority

The fact underneath is usually fine. The dressing is the problem.

### C1. Overused words

**Look for:** delve, robust, comprehensive, leverage, seamless, crucial, pivotal,
landscape (abstract), tapestry, testament, showcase, underscore (verb), meticulous,
vibrant, enhance, utilize, facilitate, myriad.

**Why:** Models reach for these far more often than people do, especially several in
one passage. This is the one list where the word itself is the tell, wherever it
appears.

A formal word that is not on this list is not a tell, and technical terms are never
tells. "Robust" in "robust to partial failure" is fine; "a robust solution" is not.

> **Before:** This comprehensive change leverages a robust caching layer to deliver a
> seamless experience and underscore our commitment to performance.
>
> **After:** The change adds a cache, which removes a repeat database query on every
> request.

### C2. Inflated significance

**Look for:** marks a pivotal moment, plays a key role, sets the stage for, an enduring
legacy, underscores the importance of, reflects a broader trend; a stock section
("Challenges and outlook", "Future direction"); a closing paragraph promising a
future.

**Why:** An ordinary detail is said to mark a turning point or prove a trajectory. The
fact is real; the significance is invented.

**Keep the fact. Drop the significance. End on the last concrete detail.**

> **Before:** The retry cap was added in 2.1.0, marking a pivotal moment in the
> integration's reliability story and reflecting a broader shift toward resilience
> across the project.
>
> **After:** The retry cap was added in 2.1.0.

> **Before:** Despite these challenges, with its active release cadence, the
> integration continues to mature. The future looks bright.
>
> **After:** (cut — end on the previous concrete fact)

### C3. Shallow -ing riders

**Look for:** an -ing clause bolted onto a fact to make it sound considered —
highlighting, underscoring, ensuring, reflecting, showcasing, enabling, providing,
contributing to, helping to.

**Why:** The rider adds a claim that is usually unsupported, and it is often the only
reason the sentence is long. Attaching it to a source does not make it true.

**Keep the rider** only when the source supports what it claims.

> **Before:** The switch now reports the redirect target, improving observability and
> ensuring that users can more easily understand their configuration.
>
> **After:** The switch now reports the redirect target.

### C4. Borrowed authority

**Look for:** experts agree, studies show, it is widely considered, industry best
practice, many teams, several projects; "cited in [list of outlets]"; "used by N
companies".

**Why:** A name or an unnamed authority stands in for what was actually said. Unnamed
experts prop up a claim; a list of prestigious names props up a person or project.

**Keep it** when the source names a real authority and what it said.

> **Before:** Industry best practice suggests that retries should use exponential
> backoff.
>
> **After:** The AWS SDK retries with exponential backoff.

### C5. Avoiding *is*, *are*, and *has*

**Look for:** serves as, stands as, functions as, operates as, represents, constitutes,
boasts, features, offers, maintains.

**Why:** A simple verb is replaced with a longer phrase that says the same thing in
more words.

> **Before:** The module serves as the entry point and boasts a small dependency
> surface.
>
> **After:** The module is the entry point and has one dependency.

### C6. Sales language

**Look for:** in the heart of, nestled in, a must-have, seamlessly integrates, unlocks,
supercharge, powerful, effortless, delightful, empowers you to.

**Why:** The text reads as an advertisement. In a README this is defensible; in a
release note it is not.

> **Before:** This release unlocks a powerful new way to manage your endpoints,
> seamlessly integrating with your existing setup.
>
> **After:** This release adds a service for creating and deleting endpoints.

---

## D. Formatting by rule

A model applies clean formatting everywhere. A person formats where it helps.

### D1. Bold as decoration

**Look for:** bold on every list item label, bold on key terms on first use, bold used
for emphasis inside a sentence that is already clear.

**Why:** Bold loses its meaning when it is everywhere, and a labeled list often hides
that the labels carry no information of their own.

> **Before:**
> - **Performance:** Improved through caching.
> - **Safety:** Preserved via validation.
> - **Scope:** Limited to one profile.
>
> **After:** The change adds caching, is limited to one profile, and validates input
> before writing.

### D2. Emoji as status markers

**Look for:** ✅ / ❌ / ⚠️ / 🚀 / 💡 opening most lines or table rows.

**Why:** Status is already carried by the words. The emoji adds a second channel for
the same information, and in a technical document it reads as decoration.

> **Before:**
> - ✅ Tests pass
> - ⚠️ Lint has one warning
> - ❌ Deploy is unverified
>
> **After:**
> - Tests pass.
> - Lint reports one warning.
> - Deploy is unverified.

### D3. Decorative headings

**Look for:** Title Case In Every Heading; emoji or arrows in headings; a horizontal
rule between every section; a document that opens with a heading repeating its own
title; a heading written for effect ("The decision, on one screen") rather than for
findability ("How the six options compare").

**Why:** Sentence case is the convention in most technical styles, and a heading's job
is to help someone find the section again.

### D4. Curly quotation marks

**Look for:** “ ” and ’ where the file or the writer uses straight quotes.

**Why:** Editors autocorrect, so this is weak alone. It matters in plain-text files
where straight quotes are the convention.

### D5. Writing about the document instead of its subject

**Look for:** "This section covers…", "The table below compares…", "This document is
organised by…", "Note that this guide…", "what changed since the previous version".

**Why:** The reader can see the structure. Describing it spends their attention on the
container rather than the content.

**Keep** a note about a previous version in a changelog, release note, or migration
guide, where that is the subject. State a convention only when the reader cannot infer
it, and state it once.

> **Before:** This section describes the retry behaviour. The table below compares the
> two modes.
>
> **After:** (cut both sentences; let the heading and table speak)

---

## E. Leftovers from the chat

Remove these outright.

### E1. Chat residue

**Look for:** I hope this helps, of course, certainly, great question, you're
absolutely right, would you like me to, want me to, shall I continue, let me know,
here is a, as requested.

**Why:** A chatbot's greeting, praise, offer, or closing left in text that should stand
on its own. It is the most certain tell here and the easiest to miss when it wraps real
content.

> **Before:** Great question. Here's the summary you asked for. The deploy failed
> because the token had expired. Let me know if you'd like the full log.
>
> **After:** The deploy failed because the token had expired.

### E2. Knowledge-limit disclaimers and guesses

**Look for:** as of [date], up to my last update, while specific details are limited,
based on available information, not publicly documented, in the provided sources,
likely [did X], it is believed that, appears to have been.

**Why:** The text reports where the model's knowledge ends, or admits it found nothing
and then fills the gap with a plausible guess. The guess is the real problem, because
it is indistinguishable from the surrounding facts.

**State what the source does not show, or cut the sentence. Never guess.**

> **Before:** While the exact version is not documented in the available sources, it
> appears to have been introduced in 2023.
>
> **After:** The available sources do not give the version. (Or cut.)

### E3. A heading repeated in the first sentence

**Look for:** a heading followed by a one-line paragraph that restates it before the
real content starts.

**Why:** Pure duplication. The heading already told the reader what the section holds.

> **Before:**
> ## Performance
> > Performance matters here. The query runs once per request.
>
> **After:**
> ## Performance
> > The query runs once per request.

### E4. Narrating your own process

**Look for:** "I first checked X, then Y", "Let me verify that", "To confirm, I ran…",
"After some investigation", "I then discovered".

**Why:** The reader wants the result. The method belongs in a ticket, a log, or a
reproduction step, and stating it in a summary pushes the answer down.

**Keep it** in a bug report under a heading that asks for it, such as reproduction
steps.

> **Before:** Let me verify the claim first. I ran the query against staging, then
> against production, and found that production has the stale row. So the answer is
> that production was not migrated.
>
> **After:** Production was not migrated, so it still holds the stale row.

---

## F. Writing for the wrong reader

A model writes for a reader with no context, because that fits the most cases. A reply
in a thread has a reader who already knows the background.

**Act on this only when you can see the surrounding conversation, or when the text is
plainly a reply. If you cannot tell, ask or leave it.**

### F1. Re-explaining what the reader knows

**Look for:** a reply that restates the problem, walks the diagnosis, and lays out the
evidence before reaching the decision; numbers or command output included to prove a
plan will work; background the other person wrote themselves; the answer sitting in
the last line.

**Why:** Every sentence can read fine on its own, so this survives sentence-level
cleanup. The fix is structural: lead with the decision and keep only the reasoning
that would change whether the reader agrees.

The diagnosis and the proof belong in the ticket that follows, not in the reply. A
reviewer raising a topic is not asking for the full write-up.

> **Before:** You're right, this works around the issue rather than fixing it. The real
> fix is in `MergeService`: when a child moves under a new parent, it should update
> `pipeline_id` along with `parent_id`. We can backfill the bad rows from the audit
> log. I checked QA: 123 past merges, only 6 rows are wrong, so the cleanup is small.
>
> Since `MergeService` is shared, I'd rather open a separate ticket than widen this
> PR.
>
> **After:** Agreed, this is a workaround. Fixing it properly means changing shared
> code, so I'd rather keep this PR scoped and open a separate ticket for the
> `MergeService` fix and the backfill.

---

## Checking your own work

Two checks catch most of what survives a rewrite.

**Read it aloud.** Anything that sounds like a summary of a summary is still staged.

**Ask "what does this sentence add?"** If the answer is "emphasis", cut it or give it
a fact to carry.
