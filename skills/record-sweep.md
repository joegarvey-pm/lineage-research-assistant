# Skill: sweeping many unindexed records

**When:** reading hundreds of record images in sequence, looking for one
household. Unindexed census reels, probate volumes, bound registers.

**Goal:** a result with a real denominator — and if you stop early, an honest
account of exactly where.

This is the grinding one. It is also where most of the real finds come from,
because unindexed records are exactly the ones nobody else has searched.

---

## Before you start: bound the range

Find the **true** first and last image of the thing you're searching, by
reading the page headers — not by estimating.

Every naive estimate is wrong. In practice: estimated ranges have been wrong
at both ends, by over 30 images, on the majority of volumes where anyone
checked. A range that's wrong at the start means you sweep the wrong county
and report a confident negative about a place you never looked at.

Bisect by header: read image 100, 200, 400; find where the jurisdiction
changes; narrow. Record the bounded range and **how** you bounded it ("both
edges hard-read" vs "start inferred").

---

## Chunk it, sequentially

**Work one bounded chunk at a time** — 50-100 images is a good size — with an
explicit stop condition.

**Do not run several heavy sweeps in parallel.** They share a usage limit;
when it trips, they all die mid-task and the partial work is lost. Sequential
chunks that each complete are strictly better than parallel chunks that each
die at 60%.

After each chunk, **write the result down before starting the next one.**

---

## Verify each image before you read it

A truncated download opens as a valid image file showing the top fraction of
the page and blank grey below. It reads as a sparse or empty page. It does not
error.

**Check the file size** against a known-good full page. If it's well under,
re-fetch before reading. This single check prevents false negatives that are
otherwise undetectable.

---

## Don't trust a page-numbering formula

If you work out that printed page = 2 × (image − 20), **re-confirm it
periodically**, not once.

Bound volumes genuinely contain:
- duplicate scans of the same spread
- skipped frames
- **two separately-numbered original books bound and filmed as one**, so the
  numbering jumps by hundreds mid-volume

Read the printed number off each page where it matters. Use the formula for
navigation, never for citation.

---

## Record the chunk result

Each chunk gets a log row with:

- The **exact** image range read ("231-300", not "about 70 images")
- What jurisdictions/sections it covered — this is often genuinely new
  reference data nobody has mapped before, worth recording even on a miss
- Any near-miss names found **and ruled out**, with the reason
- Any images that were blank, illegible, or failed to fetch — **listed
  separately** from genuine negatives
- Whether the chunk completed or stopped early

---

## Stopping early is allowed. Lying about it is not.

If a sweep stops partway — usage limit, a service outage, running out of
session — **say exactly where it stopped and what remains.**

> ✅ *"Read images 231-242 of 736. Negative through 242. Images 243-736 remain
> unread. Next session resumes at 243."*
>
> ❌ *"Searched the reel, nothing found."*

The second sentence will cause a future session to treat 500 unread images as
settled. That's not a reporting nicety — it's the difference between a
conclusion and a fabrication.

---

## When the service fails rather than the search

Distinguish these clearly, because they need opposite responses:

| Symptom | Likely cause | Response |
|---|---|---|
| Every request to one item fails, other items on the same host work | Item-specific backend problem | Note it, switch to a different item, come back later |
| Every request to the host fails, including its homepage | Site-wide outage | Stop. Don't retry in a loop. Report and wait. |
| Downloads succeed but are undersized | Truncation | Re-fetch with size verification |
| Works, but one specific image 404s or errors | Corrupt source file | Note the single image as unreadable; it's not a coverage gap if the surrounding content is complete |

**Diagnose before retrying.** Five identical failed retries tell you nothing
that the first one didn't. Test a *different* item on the same host — that one
experiment distinguishes "this item is broken" from "this site is down," and
they call for completely different responses.
