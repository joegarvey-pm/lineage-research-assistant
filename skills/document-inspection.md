# Skill: reading a record document

**When:** you have an actual record in front of you — a census page, a will, a
probate order, a certificate, a newspaper clipping — and need to extract what
it genuinely says.

**Goal:** a transcription you'd defend, and an explicit statement of what the
document does *not* establish.

---

## Read the whole document, not the matching line

The surrounding context is usually where the real finding is:

- **Neighbours matter.** In 19th-century US censuses, families lived next to
  their in-laws constantly. The household two doors down is often the
  mother's family, and it may be the only thing that names her maiden name.
- **The enumerator's own marks matter.** Certification pages, district
  boundaries, and closing totals tell you whether you've reached the end of a
  jurisdiction — which is how you know your denominator.
- **The column headers matter.** Don't assume the 1880 layout for an 1870
  page. Relationship-to-head only appears from 1880 onward in US censuses;
  before that, a household enumeration places people together but **does not
  state that they are parent and child**. That distinction is the entire
  difference between a 50% and a 90% score.

---

## Transcribe exactly, then interpret separately

Keep these two things visibly apart:

> **What it says:** *"Marsh, Daniel S., 42, M, W, Laborer, b. Illinois;
> [wife], 43, F, W, Keeping House, b. Kansas; Ernest D., 8, M, W, Son, b.
> Kansas"*
>
> **What that means:** one secondary record stating the relationship directly
> → 50% for both parental joins.
>
> **What it does not establish:** nothing about *his* parents; nothing that
> resolves the conflicting birthplace in the tree.

Never merge the quote and the inference into one sentence. A future session
needs to be able to re-interpret your transcription without re-fetching the
image.

---

## When the handwriting is ambiguous

**Say so, in the record.** Do not silently pick the reading that matches what
you were hoping for — that is the most common way a wrong fact enters a tree
and never leaves.

Technique that actually works:

1. Crop tight on the word and enlarge it.
2. **Find the same letter elsewhere on the same page, written by the same
   hand**, in a word you're certain of. Compare letterforms directly.
3. Report what you did: *"reads 'Nora', not 'Lora' — compared against a
   confirmed capital L in 'Lindsay' five rows down on the same sheet, in
   the same hand; genuinely different letterforms."*

That example is the common case, not a contrived one. A flourished 19th-
century capital `L` and capital `N` are frequently indistinguishable in
isolation and obvious side by side — and a single misread initial is enough
to hide a household from every future search.

A documented ambiguity is a finding. A guess presented as a reading is damage.

---

## Watch for these specific traps

**Caption vs. body.** Court records frequently have a clerk's case caption
naming one person and the body of the same order naming another. **Prefer the
body** — it's the operative text and it's the one that states the
relationship. Record the discrepancy rather than reconciling it silently.

**Ditto marks and bracket lines.** A long bracket down a census name column
can group people who aren't a family. Check where it actually starts and
stops.

**Ages that run consistently wrong.** If every person in a household is
exactly one year older than expected, that's internal consistency, not a
mismatch — likely an enumeration date effect. Say so rather than treating it
as six separate discrepancies.

**Truncated images.** A partially-downloaded image can open as a valid file
showing only the top third of a page, with the rest blank grey. It will read
as a sparse page rather than erroring. **Check the file size** against what a
full page should be before trusting a "nothing here."

**Near-miss surnames.** `Hobbs` reads as `Hubs` reads as a possible `Hubbert`
at low resolution. Zoom before you flag, and zoom before you dismiss.

---

## Archive what you found

A citation pointing at a URL that later dies is a promise, not evidence.

```bash
python3 -m treetools.cli evidence add --file <image> --id <short-key> \
  --title "<what the record is>" --tier primary|secondary \
  --repository "<who holds the original, not the website you used>" \
  --free-source "<url>" --retrieved <YYYY-MM-DD> \
  --supports "<which join this moves, and from what to what>"
```

Note the distinction the `--repository` flag is asking for: **who holds the
original**, not which website showed it to you. Those are different facts and
only one of them is stable.

---

## Then say what it doesn't prove

Close every document reading with this explicitly. A record that proves a
couple existed does not prove who their children were. A record naming a widow
does not name a daughter. The gap between "this document is about this family"
and "this document proves this specific join" is where most over-claiming
happens.
