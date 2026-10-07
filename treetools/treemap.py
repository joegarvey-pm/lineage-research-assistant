"""Render the direct line as markdown, Mermaid, or a table.

Three views of the same thing, because three different questions get asked:

    indent    "what's the shape of my direct line?"
    mermaid   "show me a diagram"            (renders on GitHub, no toolchain)
    table     "where exactly is the evidence weak?"

**Everything here colours by CHAIN, never by LINK**, and that choice is the
whole point of the module. A person's own LINK can be 90% while their CHAIN
is 10%, because something *below* them on the path to the root is unproven.
CHAIN is the honest number. A visualisation that shows LINK would make an
undocumented tree look documented, which is the exact failure this project
exists to prevent.

The deliberate consequence: a tree that *looks* impressive renders mostly
grey, and the eye goes straight to the weakest shallow join. That is the
frontier, and it is where the next piece of work belongs.
"""

from typing import Dict, List, Optional, Tuple

from .parse import Gedcom
from .pedigree import Pedigree
from .score import PersonScore

#: CHAIN thresholds. These mirror the rubric's own tiers rather than being
#: chosen for visual balance -- 75 is "several consistent secondary records",
#: 25 is "somebody's chart, no record", so those are the real boundaries.
STRONG = 75
THIN = 25


def _tier(chain: Optional[int], is_root: bool = False) -> str:
    """root | documented | thin | unproven — the visual states.

    The root person has no join of their own, so their CHAIN is None by
    design, not by failure. Rendering them as "unproven" would be a lie
    about the one person in the tree we are certain about.
    """
    if is_root:
        return "root"
    if chain is None:
        return "unproven"
    if chain >= STRONG:
        return "documented"
    if chain >= THIN:
        return "thin"
    return "unproven"


_MARK = {"root": "@", "documented": "#", "thin": "~", "unproven": "?"}


def _life(gedcom: Gedcom, xref: str) -> str:
    """`b.1824-d.1899` style, with whatever is actually known."""
    ind = gedcom.individuals.get(xref)
    if ind is None:
        return ""
    born = getattr(ind, "birth_year", None)
    died = getattr(ind, "death_year", None)
    if born and died:
        return f"{born}-{died}"
    if born:
        return f"b.{born}"
    if died:
        return f"d.{died}"
    return ""


def _label(gedcom: Gedcom, s: PersonScore) -> str:
    life = _life(gedcom, s.xref)
    return f"{s.name} ({life})" if life else s.name


def _ordered(pedigree: Pedigree, scores: Dict[str, PersonScore],
             generations: int) -> List[PersonScore]:
    """Ancestors within the generation limit, in Ahnentafel order.

    Ahnentafel order is used rather than a recursive walk because it is
    stable, it puts each generation together, and it survives pedigree
    collapse (the same person appearing at two positions) without looping.
    """
    out = []
    for xref, info in pedigree.ancestors.items():
        if info.generation > generations:
            continue
        s = scores.get(xref)
        if s is not None:
            out.append(s)
    out.sort(key=lambda s: (s.ahnentafel or 0))
    return out


# --------------------------------------------------------------------------
# indent — plain markdown, readable anywhere
# --------------------------------------------------------------------------

def render_indent(gedcom: Gedcom, pedigree: Pedigree,
                  scores: Dict[str, PersonScore],
                  generations: int = 5) -> str:
    people = _ordered(pedigree, scores, generations)
    by_gen: Dict[int, List[PersonScore]] = {}
    for s in people:
        by_gen.setdefault(s.generation or 0, []).append(s)

    lines = ["# Direct line", ""]
    lines.append("`@` root person  ·  `#` documented (CHAIN >= 75)  ·  "
                 "`~` thin (25-50)  ·  `?` unproven (<= 10)")
    lines.append("")

    for gen in sorted(by_gen):
        label = {0: "Root", 1: "Parents", 2: "Grandparents"}.get(
            gen, f"{gen - 2}x-great-grandparents" if gen > 3
            else "Great-grandparents")
        filled = len(by_gen[gen])
        total = 2 ** gen
        lines.append(f"## Generation {gen} — {label} ({filled}/{total})")
        lines.append("")
        for s in by_gen[gen]:
            mark = _MARK[_tier(s.chain, s.ahnentafel == 1)]
            chain = "--" if s.chain is None else f"{s.chain}%"
            indent = "  " * min(gen, 6)
            lines.append(f"{indent}{mark} {_label(gedcom, s)} — CHAIN {chain}")
        lines.append("")

    lines.extend(_frontier_note(scores))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# mermaid — renders natively on GitHub, Obsidian, Notion
# --------------------------------------------------------------------------

_MERMAID_CLASSES = """
    classDef root fill:#e3f2fd,stroke:#1565c0,stroke-width:3px,color:#0d47a1;
    classDef documented fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20;
    classDef thin fill:#fff8e1,stroke:#f9a825,stroke-width:2px,stroke-dasharray:5 3,color:#795548;
    classDef unproven fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1px,stroke-dasharray:2 3,color:#9e9e9e;
"""


def _node_id(s: PersonScore) -> str:
    return f"A{s.ahnentafel}"


def _escape(text: str) -> str:
    """Mermaid labels break on quotes and brackets."""
    return (text.replace('"', "'")
                .replace("[", "(").replace("]", ")")
                .replace("{", "(").replace("}", ")"))


def render_mermaid(gedcom: Gedcom, pedigree: Pedigree,
                   scores: Dict[str, PersonScore],
                   generations: int = 5) -> str:
    people = _ordered(pedigree, scores, generations)
    by_ahn = {s.ahnentafel: s for s in people if s.ahnentafel}

    lines = ["```mermaid", "graph RL"]  # right-to-left: root on the right
    tiers: Dict[str, List[str]] = {"root": [], "documented": [],
                                   "thin": [], "unproven": []}

    for ahn, s in sorted(by_ahn.items()):
        chain = "--" if s.chain is None else f"{s.chain}%"
        label = _escape(f"{_label(gedcom, s)}\\nCHAIN {chain}")
        lines.append(f'    {_node_id(s)}["{label}"]')
        tiers[_tier(s.chain, s.ahnentafel == 1)].append(_node_id(s))

    # Ahnentafel makes the edges trivial: parents of N are 2N and 2N+1.
    for ahn, s in sorted(by_ahn.items()):
        for parent_ahn in (ahn * 2, ahn * 2 + 1):
            parent = by_ahn.get(parent_ahn)
            if parent is not None:
                lines.append(f"    {_node_id(parent)} --> {_node_id(s)}")

    lines.append(_MERMAID_CLASSES.rstrip())
    for tier, ids in tiers.items():
        if ids:
            lines.append(f"    class {','.join(ids)} {tier};")
    lines.append("```")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# table — scanning for the weak spots
# --------------------------------------------------------------------------

def render_table(gedcom: Gedcom, pedigree: Pedigree,
                 scores: Dict[str, PersonScore],
                 generations: int = 5) -> str:
    people = _ordered(pedigree, scores, generations)
    lines = ["| Ahn | Gen | Person | LINK | CHAIN | Evidence |",
             "|---|---|---|---|---|---|"]
    for s in people:
        chain = "--" if s.chain is None else f"**{s.chain}%**"
        tier = _tier(s.chain, s.ahnentafel == 1)
        note = {"root": "root person",
                "documented": "documented",
                "thin": "thin",
                "unproven": "unproven"}[tier]
        lines.append(
            f"| {s.ahnentafel or ''} | {s.generation} | {_label(gedcom, s)} "
            f"| {s.link}% | {chain} | {note} |")
    lines.append("")
    lines.extend(_frontier_note(scores))
    return "\n".join(lines)


# --------------------------------------------------------------------------

def _frontier_note(scores: Dict[str, PersonScore]) -> List[str]:
    """The shallowest weak join — the one place work actually pays off."""
    weak = [s for s in scores.values()
            if s.is_ancestor and s.chain is not None and s.chain < STRONG
            and s.ahnentafel != 1
            and s.generation is not None]
    if not weak:
        return ["> Every join on the direct line is documented to 75% or "
                "better. The frontier is wherever the tree currently ends."]
    weak.sort(key=lambda s: (s.generation, s.chain))
    shallowest = weak[0]
    return [
        "> **Frontier — the shallowest weak join, and where work pays off "
        "most:**",
        f"> {shallowest.name} at generation {shallowest.generation}, "
        f"CHAIN {shallowest.chain}%.",
        "> Everything above this person is capped by it, so depth up there "
        "cannot exceed this number.",
    ]


RENDERERS = {
    "indent": render_indent,
    "mermaid": render_mermaid,
    "table": render_table,
}


def render(gedcom: Gedcom, pedigree: Pedigree,
           scores: Dict[str, PersonScore],
           fmt: str = "indent", generations: int = 5) -> str:
    try:
        fn = RENDERERS[fmt]
    except KeyError:
        raise ValueError(
            f"unknown format {fmt!r} — expected one of "
            f"{', '.join(sorted(RENDERERS))}")
    return fn(gedcom, pedigree, scores, generations)
