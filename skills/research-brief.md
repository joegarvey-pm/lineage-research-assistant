# Skill: writing a research brief

**When:** the user asks *"what should I work on next?"* — or you've just
finished something and need to pick the next target.

**Goal:** a short, ranked, costed plan. Not a list of possibilities — a
recommendation with a reason.

---

## The ranking rule

Rank by **which join a hit would move, and by how much** — never by what's
interesting, and never by what's easy to search.

A good target has three properties:

1. **It's shallow.** The weakest *nearest* join beats a weaker distant one,
   because everything above a weak link is capped by it.
2. **One record moves two scores.** A marriage record names two parents. A
   household census places a child with both. Prefer these.
3. **It can actually be reached.** Check coverage *and* access before you
   recommend it (see `web-research.md`).

---

## Before you write anything, check these

```bash
python3 -m treetools.cli frontier --gedcom <file> --overrides <overrides>
python3 -m treetools.cli archives --place "<county>, <state>" --year <year> --record-type <class>
```

Then read the research log for the targets you're considering. **If a prior
session already searched it and found nothing, that is the single most
valuable thing you can know** — and the most commonly ignored.

---

## The shape of a brief

Keep it under a page. Four parts:

### 1. The recommendation, in one sentence

> *"Order [ancestor]'s 1931 death certificate — it names both parents, it's
> $20, and it's the only remaining route past the census ceiling for that
> join."*

### 2. Why this and not something else

Name the alternative you rejected and why. This is the part that stops the
user second-guessing you later.

### 3. What it costs and who does it

Be specific and honest:

- **Free + machine-reachable** → you can do it now
- **Free but needs a human** (login, CAPTCHA, browser-only) → hand them a
  prepared search with the exact terms and URL
- **Costs money** → state the amount and what happens if the record isn't
  found. Many vital-records fees are *retained on a null result* — say so.

### 4. What a null result would mean

**This is the part most research plans skip, and it's the most important.**

Before searching, decide what "not found" would tell you:

- *"If it's not there, that's a real negative — the series is complete for
  that year, so he either died intestate or the surname is spelled
  differently."*
- *"If it's not there, it means nothing — this county's records for that
  decade burned."*

If you can't answer that question, **you're not ready to search yet**. Go
check coverage first.

---

## Ceilings — state them up front

Say what the *best possible outcome* is before the work starts, so nobody
expects more than the record class can deliver:

| If you find… | Best it can be | Why |
|---|---|---|
| One census household | 50% | One secondary record |
| Several census years agreeing | 75% | Still all secondary — a census states where someone lived, not whose child they are |
| A primary record naming the relationship | 90% | Needs a second agreeing record for 99% |

**Watch for permanent ceilings.** If an ancestor died before the next census,
then a single census year isn't "the first of two" — it's the only one there
will ever be, and 50% is that join's permanent census ceiling. Say so rather
than implying more work would help.

---

## Anti-patterns

- **Don't recommend breadth.** "Build out the siblings" is almost never right.
- **Don't recommend depth above a weak join.** Everything up there is capped.
- **Don't produce a menu.** A brief with five equal options is a brief that
  hasn't done its job.
- **Don't bury the cost.** If it needs a $20 cheque and a two-month wait, lead
  with that.
