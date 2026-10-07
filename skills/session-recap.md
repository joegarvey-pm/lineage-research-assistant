# Skill: writing a session recap

**When:** the end of every working session, without exception.

**Goal:** a record honest enough that a future session — or a future *you*,
with no memory of this one — can trust it without re-verifying.

---

## Why this is non-optional

Research sessions are long and the context disappears. Six weeks later the
only thing that survives is what got written down. A session with a great find
and no recap is worth less than a session with a null result and a good one,
because the null result is reusable and the find has to be re-derived.

The one session in a long project that skips its recap is reliably the one
whose reasoning becomes unrecoverable.

---

## Write these, in this order

### 1. In one paragraph — what actually happened

Lead with the real headline, including when the headline is a negative. *"The
volume is read cover to cover and the record isn't in it"* is a genuine
result. Say so in the first sentence rather than burying it under process.

### 2. What shipped

A short table: what was read or found, where it is now, what score moved.

### 3. What did **not** happen

**Never skip this section.** Three things belong here:

- What you planned and didn't get to
- Where exactly a partial sweep stopped (exact ranges, not "most of")
- Anything you deliberately decided *not* to do, and why

A recap without this section reads as complete work and will be built on as
if it were.

### 4. Score changes, with reasons attached

Every number that moved, with the record that moved it and the ceiling that
record class imposes. If nothing moved, say that plainly — it's common and
it's fine.

### 5. Process notes worth carrying forward

Only genuinely transferable lessons. Not "the search was slow." Things like:
*"a truncated download opens as a valid image showing the top third of the
page — check file size before trusting a blank"* — a trap that will otherwise
be rediscovered the hard way.

---

## The honesty rules

**Mark unverified things as unverified.** If a fee, address, or holding came
from a search-result summary rather than a source you opened, say which.

**Record the denominator.** "Searched the county" means nothing. "Read all 163
pages" or "read 39 of 163, a 24% sample" means something.

**Distinguish the three kinds of null** (settled absence / coverage gap /
method error — see `web-research.md`). Collapsing them is the most expensive
error available in this work.

**If you were wrong earlier, say so at the top.** Loudly, in the recap, where
it will be read. Not quietly patched in a file nobody revisits.

---

## Recaps are append-only

Never edit a previous session's recap. If it was wrong, say so in the *current*
recap and correct the affected files. The historical record of what was
believed when is itself research data — it tells a future reader which
conclusions rested on what.

The single exception: correcting a status line that is factually wrong (a
session marked "not run" that did run). Note in place that you corrected it
and when.

---

## Template

```markdown
---
type: recap
date: YYYY-MM-DD
scope: <one line>
---

# YYYY-MM-DD — <title>

## In one paragraph
<the headline, including if it's a negative>

## What shipped
| Item | Result |
|---|---|

## What did NOT happen
- <planned and not done>
- <partial work, with exact ranges>
- <deliberately skipped, and why>

## Score changes
<each one, with the record and the ceiling — or "none this session">

## Process notes worth carrying forward
- <only genuinely transferable lessons>
```
