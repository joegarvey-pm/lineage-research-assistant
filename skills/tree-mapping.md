# Skill: mapping the tree

**When:** the user wants to *see* their tree — the shape of it, where the
evidence is strong, where it falls apart.

**Goal:** a markdown or Mermaid view they can read in any editor, paste into
any document, and that renders on GitHub without a toolchain.

---

## The command

```bash
python3 -m treetools.cli treemap --gedcom <file> --overrides <overrides> \
    --format indent|mermaid|table --generations 5
```

Three formats, for three different questions:

| Format | Answers | Best for |
|---|---|---|
| `indent` | *"What's the shape of my direct line?"* | Reading in a plain text editor; pasting into notes |
| `mermaid` | *"Show me a diagram"* | GitHub, Obsidian, Notion — renders natively, no install |
| `table` | *"Where exactly is the evidence weak?"* | Scanning scores; finding the frontier |

---

## Always colour by CHAIN, never by LINK

A person's own LINK can be 90% while their CHAIN is 10%, because something
below them is unproven. **CHAIN is the honest number** and it's the one a
visualisation must show, or the picture lies.

The generated Mermaid uses:

- **Solid border** — CHAIN ≥ 75% (documented)
- **Dashed border** — CHAIN 25-50% (thin)
- **Dotted + grey** — CHAIN ≤ 10% (effectively unproven)

The effect is deliberate: a tree that *looks* impressive renders mostly grey,
and the eye goes straight to where the real work is. That's the point.

---

## Reading the output with the user

Don't just hand over a diagram. Say the three things it shows:

1. **Where the solid part stops.** This is the honest edge of the documented
   tree, and it's usually much closer than the user expects.
2. **The shallowest weak join.** That's the frontier — the next thing worth
   working on.
3. **Anything grey that's deep.** Politely: those generations are inherited
   assertions, not research. They aren't wrong, they're just unverified, and
   nothing can be concluded from them until the join below them is proven.

Say this once, kindly, and don't repeat it every session. Most people's trees
look like this. It isn't a personal failing — it's what accepting hints
produces, and recognising it is the first real step.

---

## A note on the deep end

Almost every tree has a branch that runs back to a medieval king or a
*Mayflower* passenger. These are almost always attached by a single
undocumented join somewhere in the 1700s, below which everything is copied
from other people's trees.

Render it like anything else — grey, dotted, honest. Don't editorialise, don't
delete it, and don't let it be quoted as fact. The CHAIN score already makes
the point without you having to.
