"""LINK / CHAIN scoring.

The rubric is CLAUDE.md's, implemented literally:

    LINK  -- is the join to their child documented?
      99%  2+ independent records, at least one primary, each naming the
           parent-child relationship. No unresolved conflicts.
      90%  1 primary record naming the link, plus a secondary agreeing.
      75%  Several secondary records consistently placing the child in the
           parent's household, but no primary states the relationship.
      50%  1 secondary record names or implies the link.
      25%  Named in an independent researcher's work with no record behind it.
      10%  Present only via a suggested-person feature or a member tree.
       0%  Asserted. Nothing behind it.

    CHAIN -- the lowest LINK anywhere between that person and the root.

Two things a program cannot decide, and therefore does not:

  1. **Whether a cited record actually names the relationship.** GEDCOM
     records that a source is attached; it does not record what the source
     says. So the mechanical pass can only distinguish "the join carries a
     citation" from "it does not".
  2. **Why an unsourced person is in the tree at all** -- an independent
     researcher's chart (25%) and a member-tree import (10%) look identical
     in the file.

Both are human judgements, so they live in ``overrides.yaml`` where they are
version-controlled and reviewable, not buried in code. The mechanical pass
supplies a floor; overrides supply the truth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a declared dependency
    yaml = None

from .parse import Gedcom
from .pedigree import Pedigree

# The rubric's tiers. A score outside this set is a bug or a typo in the
# overrides file, and is rejected rather than rounded.
RUBRIC_TIERS = (99, 90, 75, 50, 25, 10, 0)

RUBRIC_TEXT = {
    99: "2+ independent records, one primary, each naming the relationship",
    90: "1 primary naming the link + a secondary agreeing",
    75: "Several secondary records placing the child in the household",
    50: "1 secondary record names or implies the link",
    25: "Independent researcher's work, no record behind it",
    10: "Member tree / suggested-person only",
    0: "Asserted. Nothing behind it",
}

DEFAULT_UNSOURCED_JOIN = 10
DEFAULT_CITED_JOIN = 50


class OverrideError(ValueError):
    pass


def _squash(s: str) -> str:
    """Lowercase, single-spaced. Names in this file carry stray double
    spaces from the import, and a name check should not trip on those."""
    return " ".join(s.split()).lower()


@dataclass
class Overrides:
    root: str = ""
    root_name: str = ""
    unsourced_join: int = DEFAULT_UNSOURCED_JOIN
    cited_join: int = DEFAULT_CITED_JOIN
    link: Dict[str, dict] = field(default_factory=dict)
    id_scores: Dict[str, dict] = field(default_factory=dict)
    notes: Dict[str, str] = field(default_factory=dict)
    # Where a person actually LIVED, keyed by xref — human judgement about
    # geography, kept next to the human judgement about scores. Added
    # 2026-08-31 because `census.place_for_year` derives a search county from
    # whichever dated event sits nearest the target year, and that heuristic
    # sent three separate sessions to the wrong county. See census.py's module
    # docstring and [[12 Tech Reduction Roadmap]] item 5.
    residences: Dict[str, dict] = field(default_factory=dict)
    # Editorial prose for the archive page's frontier cards, keyed by xref.
    # The people and scores on those cards are computed; only this is typed.
    frontier_prose: Dict[str, dict] = field(default_factory=dict)
    # Durable human prose that belongs in the ledger. Kept here so the
    # generated file stays a pure function of (GEDCOM, overrides) instead of
    # the generator quietly destroying hand-written narrative on each run.
    narrative: List[dict] = field(default_factory=list)

    def validate(self, gedcom: Optional[Gedcom] = None) -> List[str]:
        """Return a list of problems. Empty list = clean."""
        problems = []
        for tier_name, value in (
            ("unsourced_join", self.unsourced_join),
            ("cited_join", self.cited_join),
        ):
            if value not in RUBRIC_TIERS:
                problems.append(
                    f"defaults.{tier_name}={value} is not a rubric tier "
                    f"{RUBRIC_TIERS}"
                )
        for xref, entry in self.frontier_prose.items():
            if gedcom is not None and xref not in gedcom.individuals:
                problems.append(
                    f"frontier_prose[{xref}] is not in this GEDCOM "
                    f"(name in overrides: {entry.get('name')!r})")
            elif gedcom is not None:
                declared = _squash(entry.get("name") or "")
                actual = _squash(gedcom.individuals[xref].name)
                if declared and declared not in actual:
                    problems.append(
                        f"frontier_prose[{xref}] name mismatch: overrides say "
                        f"{declared!r}, GEDCOM says {actual!r}")
            if not entry.get("record"):
                problems.append(
                    f"frontier_prose[{xref}] has no 'record' -- a card with no "
                    f"stated next record is decoration")
        for xref, entry in self.link.items():
            score = entry.get("score")
            if score not in RUBRIC_TIERS:
                problems.append(
                    f"link[{xref}].score={score!r} is not a rubric tier "
                    f"{RUBRIC_TIERS}"
                )
            if not entry.get("basis"):
                problems.append(f"link[{xref}] has no 'basis' -- every manual "
                                f"score must say why")
            if gedcom is not None and xref not in gedcom.individuals:
                problems.append(f"link[{xref}] is not in this GEDCOM "
                                f"(name in overrides: {entry.get('name')!r})")
            elif gedcom is not None:
                declared = _squash(entry.get("name") or "")
                actual = _squash(gedcom.individuals[xref].name)
                if declared and declared not in actual:
                    problems.append(
                        f"link[{xref}] name mismatch: overrides say "
                        f"{declared!r}, GEDCOM says {actual!r}"
                    )
        # `residences` is asserted geography. It is held to the same standard
        # as an asserted score: it must name a real person in this GEDCOM, and
        # every place must say what proves it. An unsourced residence is the
        # same failure the whole heuristic was fixed to stop -- a guess wearing
        # the clothes of a fact.
        for xref, entry in self.residences.items():
            if gedcom is not None and xref not in gedcom.individuals:
                problems.append(
                    f"residences[{xref}] is not in this GEDCOM "
                    f"(name in overrides: {(entry or {}).get('name')!r})")
            elif gedcom is not None:
                declared = _squash((entry or {}).get("name") or "")
                actual = _squash(gedcom.individuals[xref].name)
                if declared and declared not in actual:
                    problems.append(
                        f"residences[{xref}] name mismatch: overrides say "
                        f"{declared!r}, GEDCOM says {actual!r}")
            places = (entry or {}).get("places") or []
            if not places:
                problems.append(
                    f"residences[{xref}] lists no places")
            for i, item in enumerate(places):
                item = item or {}
                if not str(item.get("place") or "").strip():
                    problems.append(
                        f"residences[{xref}].places[{i}] has no 'place'")
                if not str(item.get("basis") or "").strip():
                    problems.append(
                        f"residences[{xref}].places[{i}] has no 'basis' -- "
                        f"an asserted residence must say what proves it")
                if (item.get("year") is None
                        and item.get("from") is None
                        and item.get("to") is None):
                    problems.append(
                        f"residences[{xref}].places[{i}] has no 'year' and no "
                        f"'from'/'to' -- a residence with no dates cannot be "
                        f"matched to a census year")
        return problems


def load_overrides(path: str) -> Overrides:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read overrides.yaml")
    if not os.path.exists(path):
        return Overrides()
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    defaults = raw.get("defaults") or {}
    return Overrides(
        root=raw.get("root", ""),
        root_name=raw.get("root_name", ""),
        unsourced_join=int(defaults.get("unsourced_join",
                                        DEFAULT_UNSOURCED_JOIN)),
        cited_join=int(defaults.get("cited_join", DEFAULT_CITED_JOIN)),
        link=raw.get("link") or {},
        id_scores=raw.get("id") or {},
        notes=raw.get("notes") or {},
        residences=raw.get("residences") or {},
        narrative=raw.get("narrative") or [],
        frontier_prose=raw.get("frontier_prose") or {},
    )


@dataclass
class PersonScore:
    xref: str
    name: str
    generation: Optional[int]
    ahnentafel: Optional[int]
    link: int
    link_basis: str
    link_origin: str              # "override" | "mechanical"
    chain: Optional[int]
    chain_weakest: Optional[str]  # xref of the weakest join on the path
    id_score: int
    id_origin: str
    citation_count: int
    distinct_sources: int
    join_citation_count: int
    child_toward_root: Optional[str]
    is_ancestor: bool


def _mechanical_id(distinct_sources: int) -> int:
    """A deliberately blunt ID heuristic, clearly labelled as such.

    CLAUDE.md defines ID as "distinct record types naming them with
    consistent detail" but publishes no tier table, so this counts distinct
    source collections and stops short of 99%, which requires a human to
    confirm the detail is consistent.
    """
    if distinct_sources == 0:
        return 0
    if distinct_sources == 1:
        return 50
    if distinct_sources == 2:
        return 75
    return 90


def score_tree(
    gedcom: Gedcom,
    pedigree: Pedigree,
    overrides: Overrides,
    strict: bool = True,
) -> Dict[str, PersonScore]:
    """Score every person in the file. Ancestors get a CHAIN; others do not."""
    problems = overrides.validate(gedcom)
    if problems and strict:
        raise OverrideError(
            "overrides.yaml has problems:\n  - " + "\n  - ".join(problems)
        )

    scores: Dict[str, PersonScore] = {}

    # ---- pass 1: LINK -------------------------------------------------
    for xref, ind in gedcom.individuals.items():
        info = pedigree.info(xref)
        distinct = len({c.source_xref for c in ind.citations if c.source_xref})

        join_cites = 0
        if info is not None and info.join_family:
            fam = gedcom.families.get(info.join_family)
            # The join that matters is the one to the child on the home
            # path: that is the family where this person is a *spouse* and
            # the child appears. info.join_family is the child's FAMC.
            if fam:
                join_cites = fam.join_citation_count

        entry = overrides.link.get(xref)
        if entry:
            link = int(entry["score"])
            basis = str(entry.get("basis", ""))
            origin = "override"
        else:
            link = (overrides.cited_join if join_cites
                    else overrides.unsourced_join)
            basis = (
                f"Mechanical: {join_cites} citation(s) on the joining family "
                f"record" if join_cites else
                "Mechanical: no citation on the joining family record. In "
                "this tree unsourced and member-tree-copied are "
                "indistinguishable"
            )
            origin = "mechanical"

        id_entry = overrides.id_scores.get(xref)
        if id_entry:
            id_score = int(id_entry["score"])
            id_origin = "override"
        else:
            id_score = _mechanical_id(distinct)
            id_origin = "mechanical"

        scores[xref] = PersonScore(
            xref=xref,
            name=ind.name,
            generation=info.generation if info else None,
            ahnentafel=info.ahnentafel if info else None,
            link=link,
            link_basis=basis,
            link_origin=origin,
            chain=None,
            chain_weakest=None,
            id_score=id_score,
            id_origin=id_origin,
            citation_count=len(ind.citations),
            distinct_sources=distinct,
            join_citation_count=join_cites,
            child_toward_root=info.child_toward_root if info else None,
            is_ancestor=info is not None and info.generation > 0,
        )

    # ---- pass 2: CHAIN ------------------------------------------------
    # CHAIN(X) = min LINK over every join between X and the root. The root
    # itself contributes no join, so it is excluded from the minimum.
    for xref in gedcom.individuals:
        if xref not in pedigree:
            continue
        path = pedigree.path_to_root(xref)
        joins = path[:-1] if len(path) > 1 else []
        if not joins:
            continue  # the root person
        weakest_xref = min(joins, key=lambda x: scores[x].link)
        scores[xref].chain = scores[weakest_xref].link
        scores[xref].chain_weakest = weakest_xref

    return scores


def link_distribution(scores: Dict[str, PersonScore],
                      ancestors_only: bool = True) -> Dict[int, List[str]]:
    out: Dict[int, List[str]] = {t: [] for t in RUBRIC_TIERS}
    for s in scores.values():
        if ancestors_only and not s.is_ancestor:
            continue
        out.setdefault(s.link, []).append(s.xref)
    return out


def frontier(scores: Dict[str, PersonScore],
             threshold: int = 90) -> List[PersonScore]:
    """The lowest-generation ancestors whose LINK is under ``threshold``.

    This is the "work the frontier bottom-up" rule expressed as code: the
    shallowest weak join is always the one worth breaking, because every
    join above it is capped by it.
    """
    weak = [s for s in scores.values() if s.is_ancestor and s.link < threshold]
    if not weak:
        return []
    lowest_gen = min(s.generation for s in weak if s.generation is not None)
    return sorted(
        [s for s in weak if s.generation == lowest_gen],
        key=lambda s: (s.ahnentafel or 0),
    )
