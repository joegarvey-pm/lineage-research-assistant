"""Ancestor walk from the root person.

Assigns, for every direct ancestor:
  * generation      -- 0 = root, 1 = parents, 2 = grandparents, ...
  * Ahnentafel      -- root = 1, father = 2n, mother = 2n+1
  * child_toward_root -- the child on the path back down to the root

That last one is what LINK scoring needs: LINK asks "is the join to *their
child* documented?", and in a tree with collateral branches "their child"
is ambiguous unless you say which child leads home.

Pedigree collapse (the same person reachable by two paths) is handled by
breadth-first traversal: the first visit wins, so a person keeps their
*lowest* Ahnentafel / shallowest generation, and additional paths are kept
in ``extra_paths`` rather than discarded.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .parse import Gedcom, Individual


@dataclass
class AncestorInfo:
    xref: str
    generation: int
    ahnentafel: int
    child_toward_root: Optional[str]      # xref of the child on the home path
    join_family: Optional[str]            # FAM linking this person to that child
    parent_role: str                      # "HUSB" | "WIFE" | "" (root)
    extra_paths: List[int] = field(default_factory=list)  # other ahnentafels


class Pedigree:
    """Ancestor map rooted on one person."""

    def __init__(self, gedcom: Gedcom, root_xref: str):
        if root_xref not in gedcom.individuals:
            raise KeyError(f"root person {root_xref!r} not in this GEDCOM")
        self.gedcom = gedcom
        self.root = root_xref
        self.ancestors: Dict[str, AncestorInfo] = {}
        self._walk()

    # -- construction -----------------------------------------------------
    def _walk(self) -> None:
        g = self.gedcom
        self.ancestors[self.root] = AncestorInfo(
            xref=self.root,
            generation=0,
            ahnentafel=1,
            child_toward_root=None,
            join_family=None,
            parent_role="",
        )
        queue = deque([self.root])

        while queue:
            xref = queue.popleft()
            info = self.ancestors[xref]
            ind = g.individuals.get(xref)
            if not ind:
                continue

            for fam_xref in ind.famc:
                fam = g.families.get(fam_xref)
                if not fam:
                    continue
                for parent_xref, role in (
                    (fam.husband, "HUSB"),
                    (fam.wife, "WIFE"),
                ):
                    if not parent_xref or parent_xref not in g.individuals:
                        continue
                    ahn = info.ahnentafel * 2 + (0 if role == "HUSB" else 1)
                    if parent_xref in self.ancestors:
                        # Pedigree collapse or a duplicated record.
                        existing = self.ancestors[parent_xref]
                        if ahn != existing.ahnentafel:
                            existing.extra_paths.append(ahn)
                        continue
                    self.ancestors[parent_xref] = AncestorInfo(
                        xref=parent_xref,
                        generation=info.generation + 1,
                        ahnentafel=ahn,
                        child_toward_root=xref,
                        join_family=fam_xref,
                        parent_role=role,
                    )
                    queue.append(parent_xref)

    # -- queries ----------------------------------------------------------
    def __contains__(self, xref: str) -> bool:
        return xref in self.ancestors

    def __len__(self) -> int:
        return len(self.ancestors)

    def info(self, xref: str) -> Optional[AncestorInfo]:
        return self.ancestors.get(xref)

    def generation(self, xref: str) -> Optional[int]:
        i = self.ancestors.get(xref)
        return i.generation if i else None

    def path_to_root(self, xref: str) -> List[str]:
        """[xref, child, grandchild, ..., root]. Empty if not an ancestor."""
        if xref not in self.ancestors:
            return []
        path, cur = [xref], xref
        seen = {xref}
        while True:
            info = self.ancestors[cur]
            nxt = info.child_toward_root
            if nxt is None or nxt in seen:
                break
            path.append(nxt)
            seen.add(nxt)
            cur = nxt
        return path

    def by_generation(self) -> Dict[int, List[AncestorInfo]]:
        out: Dict[int, List[AncestorInfo]] = {}
        for info in self.ancestors.values():
            out.setdefault(info.generation, []).append(info)
        for infos in out.values():
            infos.sort(key=lambda i: i.ahnentafel)
        return out

    def non_ancestors(self) -> List[str]:
        """Everyone in the file who is not a direct ancestor of the root."""
        return [x for x in self.gedcom.individuals if x not in self.ancestors]

    def generation_counts(self) -> List[Tuple[int, int, Optional[int]]]:
        """[(generation, known, expected)] -- expected is 2**generation."""
        by_gen = self.by_generation()
        out = []
        for gen in sorted(by_gen):
            expected = 2 ** gen if gen <= 20 else None
            out.append((gen, len(by_gen[gen]), expected))
        return out


# --------------------------------------------------------------------------
# Root discovery
# --------------------------------------------------------------------------


def find_root(gedcom: Gedcom, name_hint: str) -> str:
    """Resolve a root person from a name fragment.

    Raises if the hint is ambiguous or unmatched -- guessing the root would
    silently mis-score the entire tree.
    """
    matches = gedcom.find_by_name(name_hint)
    if not matches:
        raise LookupError(f"no individual matching {name_hint!r}")
    if len(matches) > 1:
        names = ", ".join(f"{m.name} ({m.xref})" for m in matches)
        raise LookupError(f"{name_hint!r} is ambiguous: {names}")
    return matches[0].xref


def describe(gedcom: Gedcom, xref: str) -> str:
    ind: Optional[Individual] = gedcom.individuals.get(xref)
    if not ind:
        return xref
    b = ind.birth_year
    d = ind.death_year
    span = ""
    if b or d:
        span = f" ({b or '?'}–{d or '?'})"
    return f"{ind.name}{span}"
