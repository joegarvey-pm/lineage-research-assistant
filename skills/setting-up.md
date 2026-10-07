# Skill: setting up a new user's workspace

**When:** the user's first session. They have cloned the repo and pointed you
at it.

**Goal:** a working private workspace, a root person, and a clear first task —
in about ten minutes, without the user having to understand any of the
machinery.

---

## Step 1 — check the environment (do this silently, report only problems)

```bash
python3 --version          # need 3.9+
python3 -m pytest tests/ -q # should pass; proves the kit works
```

If Python is missing or too old, say so plainly and stop — tell them to
install Python 3.9+ and come back. Don't try to work around it.

If the tests pass, say one line confirming it and move on. Don't paste the
output.

---

## Step 2 — create the workspace

```bash
mkdir -p my-research/People my-research/evidence
cp -r templates/vault/* my-research/
cp templates/overrides.example.yaml my-research/overrides.yaml
```

`my-research/` is git-ignored. **Tell the user this explicitly** — it is the
single most important thing for them to trust:

> *Everything about your family lives in `my-research/`, which is ignored by
> git. It stays on your machine. Nothing here uploads anything.*

---

## Step 3 — ask these questions, in this order

Ask them conversationally, a couple at a time. Don't present a form.

1. **"Whose tree is this — who's the root person?"** Usually the user. Get a
   full name and birth year. This person becomes the centre of every CHAIN
   score.

2. **"Do you have a GEDCOM file exported from a genealogy site?"**
   - *Yes* → ask for the path, then run Step 4.
   - *No* → that's fine. Tell them how to get one (any major genealogy site,
     usually *Tree Settings → Export*), and that they can start without it.
     Skip to Step 5.
   - *"What's a GEDCOM?"* → "It's the standard family-tree export file —
     plain text, works everywhere. Think of it as a `.docx` for family trees."

3. **"What made you want to do this?"** Not small talk. The answer is usually
   a specific question — *"who were my great-grandparents?"*, *"where in
   Ireland did we come from?"*, *"is the family story about X true?"* — and
   that question should shape the whole roadmap. Write it down verbatim at the
   top of their roadmap file.

4. **"Is there anyone alive who remembers the older generations?"**
   If yes, flag it immediately and loudly:

   > ⚠️ **This is the only thing in genealogy with a real deadline.** Records
   > will wait. People won't. An afternoon with a living relative is usually
   > worth more than a month of searching, and it can't be recovered later.

   Put "record an interview" at the top of their action items, ahead of
   anything archival.

---

## Step 4 — if they have a GEDCOM, load and summarise it

```bash
python3 -m treetools.cli summary --gedcom <their-file>
python3 -m treetools.cli audit --gedcom <their-file>
```

Report back **three things, briefly**:

- How many people, how many have any citation at all
- The honest headline: *"X% of your tree has no source behind it"* — this is
  usually a shock, and it's the most useful thing you'll tell them all session
- The top two or three audit flags, in plain language ("there's a mother
  recorded as 11 years old here — that's almost certainly two people merged")

**Do not lecture.** State it, then move to what to do about it.

---

## Step 5 — set the root and find the frontier

Set the root person in `my-research/overrides.yaml`, then:

```bash
python3 -m treetools.cli frontier --gedcom <their-file> --overrides my-research/overrides.yaml
```

The frontier is the shallowest weak join — the one place where work pays off
most. Explain *why* it's the target in one sentence: everything above a weak
link is capped by it, so depth above it is wasted effort.

---

## Step 6 — hand them exactly one next action

Not a list. One thing, with the reason attached.

Good: *"Your grandmother's 1952 marriage record should name both her parents,
and it's free on [archive]. That one document moves two scores at once."*

Bad: *"You could look at censuses, or newspapers, or order a certificate."*

Then write it into `my-research/Action Items.md` and stop. First session done.

---

## What not to do in a first session

- **Don't run a big sweep.** Setup is not the time.
- **Don't add anyone to their tree.** You never add people — that's always a
  human decision against the three-point check.
- **Don't let them start at the deep end.** Everyone wants to chase the
  17th-century immigrant. Redirect to the frontier, and explain why once.
