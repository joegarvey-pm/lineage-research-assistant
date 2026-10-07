"""Media provenance from Ancestry's extension tags.

This is the module that turns "the tree feels imported" into "184 of 193
media objects carry a ``_CLON`` block naming the tree they were copied
from". It reads three tags no standard GEDCOM library preserves:

  ``_CLON``  a clone block, written whenever a media object is copied out of
             another member's tree. Its presence is the receipt.
  ``_TID``   inside ``_CLON``: the *source* tree's numeric id. Counting
             distinct values counts how many strangers' trees were merged in.
  ``_CREA``  when the object was created in *this* tree. Histogramming these
             dates dates the import.

``_CLON`` also carries ``_DATE``, the date the media was uploaded to the
originating tree — so an object can be created here in 2026 and have been
sitting in someone else's tree since 2013.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .parse import Gedcom, MediaObject


@dataclass
class TreeGroup:
    tree_id: str
    objects: List[str] = field(default_factory=list)     # OBJE xrefs
    earliest_upload: str = ""
    latest_upload: str = ""

    @property
    def count(self) -> int:
        return len(self.objects)


@dataclass
class ProvenanceReport:
    total_objects: int
    cloned_objects: int
    native_objects: int
    tree_groups: Dict[str, TreeGroup]
    creation_histogram: List[Tuple[str, int]]     # (date 'YYYY-MM-DD', count)
    upload_year_histogram: List[Tuple[str, int]]  # origin-tree upload years
    origin_codes: Dict[str, int]
    examples: List[dict]
    objects_by_person: Dict[str, List[str]]

    @property
    def clone_share(self) -> float:
        if not self.total_objects:
            return 0.0
        return self.cloned_objects / self.total_objects

    @property
    def distinct_source_trees(self) -> int:
        return len(self.tree_groups)


def _day(stamp: str) -> str:
    """'2026-08-25 04:18:42.054' -> '2026-08-25'. Unparseable -> verbatim."""
    if not stamp:
        return "(none)"
    return stamp.split(" ")[0].strip()


def _year(stamp: str) -> str:
    d = _day(stamp)
    return d[:4] if len(d) >= 4 and d[:4].isdigit() else "(unknown)"


def analyze(gedcom: Gedcom, example_limit: int = 5) -> ProvenanceReport:
    objects = gedcom.objects
    cloned = [o for o in objects.values() if o.is_clone]

    groups: Dict[str, TreeGroup] = {}
    for obj in cloned:
        tid = obj.source_tree_id or "(no _TID)"
        grp = groups.setdefault(tid, TreeGroup(tree_id=tid))
        grp.objects.append(obj.xref)
        up = _day(obj.clone_date)
        if up != "(none)":
            if not grp.earliest_upload or up < grp.earliest_upload:
                grp.earliest_upload = up
            if not grp.latest_upload or up > grp.latest_upload:
                grp.latest_upload = up

    creation = Counter(_day(o.created) for o in objects.values())
    uploads = Counter(_year(o.clone_date) for o in cloned)
    origins = Counter(o.origin or "(none)" for o in objects.values())

    # Which person each media object hangs off, for the examples.
    by_person: Dict[str, List[str]] = defaultdict(list)
    for xref, ind in gedcom.individuals.items():
        for obj_xref in ind.object_xrefs:
            by_person[obj_xref].append(xref)

    examples = []
    for obj in sorted(cloned, key=lambda o: o.clone_date or "")[:example_limit]:
        people = by_person.get(obj.xref, [])
        examples.append({
            "object": obj.xref,
            "title": obj.title,
            "source_tree_id": obj.source_tree_id,
            "source_person_id": obj.source_person_id,
            "uploaded_to_source_tree": obj.clone_date,
            "created_in_this_tree": obj.created,
            "attached_to": [
                gedcom.individuals[p].name for p in people
                if p in gedcom.individuals
            ],
        })

    return ProvenanceReport(
        total_objects=len(objects),
        cloned_objects=len(cloned),
        native_objects=len(objects) - len(cloned),
        tree_groups=groups,
        creation_histogram=sorted(creation.items()),
        upload_year_histogram=sorted(uploads.items()),
        origin_codes=dict(origins),
        examples=examples,
        objects_by_person=dict(by_person),
    )


def format_report(report: ProvenanceReport, top_trees: int = 10) -> str:
    lines = []
    lines.append("Media provenance")
    lines.append("=" * 60)
    lines.append(f"Media objects in file      : {report.total_objects}")
    lines.append(f"Carrying a _CLON block     : {report.cloned_objects} "
                 f"({report.clone_share:.0%})")
    lines.append(f"Without one (locally added): {report.native_objects}")
    lines.append(f"Distinct source trees      : "
                 f"{report.distinct_source_trees}")
    lines.append("")
    lines.append("Created in this tree, by day (_CREA):")
    for day, count in report.creation_histogram:
        lines.append(f"  {day:<14} {count:>4}")
    lines.append("")
    lines.append("Uploaded to the ORIGINATING tree, by year (_CLON/_DATE):")
    for year, count in report.upload_year_histogram:
        lines.append(f"  {year:<14} {count:>4}")
    lines.append("")
    lines.append(f"Top {top_trees} source trees by object count (_TID):")
    ranked = sorted(report.tree_groups.values(),
                    key=lambda g: (-g.count, g.tree_id))
    for grp in ranked[:top_trees]:
        lines.append(f"  _TID {grp.tree_id:<14} {grp.count:>3} object(s)  "
                     f"uploaded {grp.earliest_upload or '?'}"
                     f"–{grp.latest_upload or '?'}")
    singletons = sum(1 for g in ranked if g.count == 1)
    lines.append(f"  ... {singletons} tree(s) contributed exactly one object")
    lines.append("")
    lines.append("Examples (oldest origin upload first):")
    for ex in report.examples:
        attached = ", ".join(ex["attached_to"]) or "(not attached to a person)"
        lines.append(f"  {ex['object']} {ex['title'][:40]!r}")
        lines.append(f"      source tree {ex['source_tree_id']}, "
                     f"uploaded there {ex['uploaded_to_source_tree']}")
        lines.append(f"      created here {ex['created_in_this_tree']}")
        lines.append(f"      attached to {attached}")
    return "\n".join(lines)
