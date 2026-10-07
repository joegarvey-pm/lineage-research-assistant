# Lineage Research Assistant

**A research kit for building a family tree where every link is backed by a
document — run by an AI agent, on your own machine, with your data staying
yours.**

Most family trees grow by accepting suggestions until they're enormous and
almost entirely unsourced. This kit does the opposite. It scores every
parent-child link by how well it's actually proven, tells you which record to
chase next, and refuses to let a guess quietly become a fact.

It is designed to be driven by an AI coding agent — Claude Code, Gemini CLI,
Codex, Cursor, or similar — so you don't have to write code to use it.

---

## Start here (about 5 minutes)

**1. Get the kit onto your machine.**

```bash
git clone https://github.com/joegarvey-pm/lineage-research-assistant.git
cd lineage-research-assistant
```

**2. Open your AI agent in that folder** (e.g. run `claude` in that directory,
or open the folder in Cursor).

**3. Paste this to your agent, exactly as written:**

> Read `CLAUDE.md` in this repo in full, then read `skills/README.md`. You are
> going to help me research my family tree using the method described there.
> When you've read both, set up my workspace by following
> `skills/setting-up.md`, then ask me the questions it tells you to ask.
> Don't skip the reading.

That's it. Your agent will set up your private workspace, ask you a handful of
questions about your family, and tell you what to do first.

**You do not need to know Python.** You never have to run a command yourself
unless you want to — your agent runs them for you.

---

## What you need

| | |
|---|---|
| **An AI coding agent** | Claude Code, Gemini CLI, Codex, Cursor, or similar — something that can read files and run commands in a folder |
| **Python 3.9 or newer** | Almost certainly already on your machine. Your agent can check. |
| **A GEDCOM file** *(optional to start)* | The standard family-tree export file. Every major genealogy site can produce one — usually under *Tree Settings → Export*. You can start without one. |

---

## What this kit actually does

**Scores your tree honestly.** Every parent-child link gets a number from 0 to
99 based on what evidence actually exists for it — not on how confident the
tree looks. Then every person gets a second number: the weakest link anywhere
between them and you. That second number is the honest one, and it's usually
much lower than people expect.

**Tells you where to dig next.** The weakest *shallow* link is almost always
worth more than another generation of depth, because everything above a weak
link is capped by it. The kit surfaces that frontier instead of letting you
wander.

**Keeps a real research log — including the misses.** A recorded "I searched
this and found nothing, across all 163 pages" stops you re-searching the same
collection in three months. Most research notes only record the wins, which is
why most research gets repeated.

**Knows which archives will actually let a bot in.** A registry of major
genealogy and government archives, with each one marked `OPEN`,
`KEY_REQUIRED`, `BLOCKED`, `AUTH_WALLED`, or `NO_MACHINE_INTERFACE` — plus
working endpoints and known traps. Months of trial and error you skip.

**Catches the errors that make a tree wrong.** Mothers who'd be 11 or 63,
children born after their father died, the same person entered twice from two
different sources, facts that arrived without a citation.

**Archives the records you find.** Content-addressed, hash-verified, so a
citation points at a file you still have rather than a URL that died.

---

## What it deliberately does not do

- **It will not build you a website.** Out of scope on purpose.
- **It will not break into anything.** It respects `robots.txt` and
  authentication walls absolutely. Where a site requires a human, it hands you
  a prepared search and gets out of the way.
- **It will not invent a record.** If a date or a document doesn't exist in
  something it actually retrieved, it says so.
- **It will not upload your family's data anywhere.** Everything runs locally.
  The `.gitignore` is written to stop you accidentally publishing your own
  GEDCOM, which contains living people's birth dates.

---

## Your data stays yours

Running this kit creates a `my-research/` folder — your notes, your scored
judgements, your archived records. **That folder is git-ignored by default and
never leaves your machine.**

This matters more than it sounds. A family tree export typically contains full
birth dates for living adults and children. Once that's pushed to a public
repo it is public permanently, even if you delete it in a later commit. The
kit is set up so you'd have to work quite hard to make that mistake.

---

## Repo layout

```
CLAUDE.md          The method. Your agent reads this first. Start here if
                   you want to understand the approach yourself.
skills/            Task recipes your agent follows — setting up, writing a
                   research brief, reading a document, running a sweep,
                   writing a session recap.
templates/         Starter files copied into your workspace on setup.
examples/          A worked research session, start to finish.
treetools/         The Python engine. Your agent calls this; you don't have to.
tests/             117 tests, all on synthetic data. `pytest` passes on a
                   fresh clone with no family data present.
```

---

## For the curious: the scoring rubric in one table

| Score | What it takes |
|---|---|
| **99%** | Two+ independent records, at least one primary, each naming the relationship |
| **90%** | One primary record naming the link, plus a secondary agreeing |
| **75%** | Several secondary records consistently placing the child in the household |
| **50%** | One secondary record names or implies the link |
| **25%** | In another researcher's work, no record behind it |
| **10%** | Only from a hint or someone else's online tree |
| **0%** | Asserted. Someone looked and found nothing. |

Full method, including the evidence hierarchy and the red-flag checks, is in
[`CLAUDE.md`](CLAUDE.md).

---

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, adapt it.

If you improve the archive registry or the method, a pull request is welcome.
**Please don't include your own family's data in one.**
