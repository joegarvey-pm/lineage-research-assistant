# Skill: writing the next session's prompt

**When:** planning a substantial piece of work — a long sweep, a new line of
enquiry, anything that will take a whole session.

**Goal:** a brief the user can review and approve *before* any work starts,
and that a fresh agent with no memory can execute correctly.

---

## Why write a prompt instead of just starting

Three reasons, all of them learned the hard way:

1. **The user gets a veto before the expensive part.** Scope errors are cheap
   to fix in a paragraph and expensive to fix after 400 pages.
2. **The next session starts clean.** Agents lose context. A prompt written to
   be read cold, by someone who knows nothing, is the only reliable handoff.
3. **Fact-checking the plan catches errors the work would inherit.** Checking
   a volume's actual page count before writing "sweep all 324 pages" has
   repeatedly turned out to matter — estimates are wrong constantly.

---

## Fact-check the prompt before you write it

This is the step that distinguishes a useful brief from a plausible one.
Before writing, verify by actually looking:

- Does the archive item exist, and what is its **real** size?
- Is it currently reachable? (`OPEN` in the registry is a past observation,
  not a promise about today)
- What did prior sessions already cover? **Re-reading 200 pages somebody
  already read is the most common waste in this work.**
- Is there a known index or finding aid that would skip the brute-force?

Then put what you verified in the prompt, with the date you verified it.

---

## Structure

### Why this prompt exists
One paragraph. What question it answers and why it's next.

### What is already true — read before planning
Everything the executing agent should not re-derive: current scores, what's
been searched, exact item IDs, verified page ranges. **This section is what
makes a cold start possible.**

### Non-negotiables
Restate them even though they're in `CLAUDE.md`. The executing session may
have cleared its context, and these are the rules whose violation is
expensive:

- Never assert a detail that didn't come from a real tool call
- Never work around `robots.txt` or an auth wall
- Rate-limit ≥ 1 second
- Work sequentially, one bounded chunk at a time
- A census caps at 75%; state the ceiling for whatever record class applies
- Never add anyone to the tree — that's a human decision
- Stopping cleanly partway is allowed; misreporting it is not

### The task
Numbered, bounded, each step with an explicit stop condition.

### Success / failure criteria
What counts as done — **including that an honest partial result counts as
success.** And a short hard-fail list: working around a block, asserting an
unverified detail, claiming coverage you don't have.

### Output contract
Which files get updated: research log, open questions, scores, person notes,
recap.

---

## Be honest about size and odds

If a sweep is 1,200 images, say so, and say it probably won't finish in one
sitting. If the index already came back clean and you're only checking for an
unindexed mention, say the odds are low and why it's still worth doing.

**A prompt that oversells its target produces a session that feels like a
failure when it returns an honest negative.** That's a framing error, not a
research one, and it's avoidable by writing the real expectation down first.

---

## Record what happened to it

Keep an index of prompts with their status — not started, ran, ran partially.
Update it the moment a session ends. A prompt whose status is stale is how
work gets silently re-run, or a real finding gets doubted later.
