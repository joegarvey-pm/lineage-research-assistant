# Skill: web research against archives

**When:** searching any online archive, catalogue, or record collection.

**Goal:** a result you can actually trust — which means knowing, before you
search, what a null result would mean.

---

## The access rule, restated because it has no exceptions

**Respect `robots.txt` and authentication walls absolutely.**

No user-agent spoofing. No headless browser aimed at a blocked host. No
"just this once." If a site disallows automated access, the search is a
**human** task and you hand it over.

This isn't pedantry. Most genealogy platforms' terms prohibit automation and
they enforce it, and a banned account can cost a user years of their own
uploaded material and attached record images. The downside is catastrophic and
the upside is saving someone ten minutes of clicking.

**What *is* allowed:** the user driving their own logged-in browser, at human
speed, while you tell them exactly what to type and where.

Always rate-limit to **at least one second** between requests to any public
archive.

---

## Check two things before you search, always

### 1. Does the archive HOLD it? (coverage)

### 2. May you REQUEST it? (access)

These are different questions with different answers, and conflating them is
how research goes wrong. An archive that blocks your agent still tells you
whether a null would be meaningful — and that sentence is worth *more* once
the search becomes a human job, not less.

```bash
python3 -m treetools.cli archives --place "<county>, <state>" --year <year> --record-type <class>
```

The registry marks each archive with one of:

| Verdict | Meaning |
|---|---|
| `OPEN` | Keyless machine access works |
| `KEY_REQUIRED` | Works, but needs an API key |
| `BLOCKED` | `robots.txt` or a firewall says no |
| `AUTH_WALLED` | Exists, needs a human login |
| `NO_MACHINE_INTERFACE` | Exists, browser only |
| `ABSENT` | Doesn't exist at all |

Only `OPEN` and `KEY_REQUIRED` are ones you may issue a request against.

---

## Name the record class before you ask about a place

*"Can I search this county for 1885?"* has no single answer. For probate it
may be fully searchable; for newspapers the same county in the same year may
be a complete coverage gap.

**An answer that doesn't say which record class it's about is worse than no
answer**, because it will be remembered as settled.

---

## Run a positive control

When a search returns zero hits, you need to know whether the search *worked*.

Run a query you know should succeed — a common surname in the same
collection, the same county in a year you know is covered — alongside the real
one. If the control also returns zero, your query is broken, not your
ancestor's absence.

**A null result without a positive control is not evidence.**

---

## Test the text layer before planning a text search

Digitised does not mean searchable. In one real case, two volumes from the
same county in the same archive differed completely: one returned thousands
of characters of OCR per page, the next returned literally zero across 487
pages.

Extract text from **one** page before building a plan on grep. If there's no
text layer, it's an image-reading job — see `record-sweep.md`.

---

## How to record the result

Every search gets a log row, hit or miss. A miss needs three things:

1. **What you searched** — collection, place, year range, exact terms
2. **The denominator** — "all 163 pages, every one read" or "a 1-in-5 sample,
   32 of 163"
3. **Which kind of null it is:**

| Kind | Means | Next time |
|---|---|---|
| **Settled absence** | The records are complete for that time and place, and the person isn't in them | Don't search again. Draw a conclusion from it. |
| **Coverage gap** | The records don't exist or weren't digitised | Don't search again. Find a different record class. |
| **Method error** | You searched the wrong place, wrong spelling, wrong jurisdiction | **Do** search again, correctly. Say what was wrong. |

**Conflating these is the single most expensive mistake in this work.** A
coverage gap logged as a settled absence will cause a future session to
"conclude" something from silence that the silence never supported.

---

## Before you assert anything

Never state a fee, form number, address, collection name, date range, or
holding that didn't come out of a tool call you actually made or a page you
actually read. If you're passing along something from a search result summary
rather than the source, **say which** — or go open the source.

Fabricated specifics are the characteristic failure of AI research. They look
exactly like real ones.
