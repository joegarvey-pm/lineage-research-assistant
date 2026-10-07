"""Compare two GEDCOM exports.

The headline check is the last one: **who gained facts without gaining
citations**. That is the signature of a member-tree import, and it is
invisible in either export on its own -- a person with three unsourced dates
looks exactly like a person who always had them. Only the diff shows the
dates arriving with no source behind them.

Ancestry keeps individual xrefs stable across exports of the same tree, so
matching is by xref. Where an export renumbers (a different tree, or a
rebuild), ``match_by_name`` falls back to normalised name + birth year and
says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .audit import _normalise_name
from .parse import Gedcom, Individual

FACT_TAGS = ("BIRT", "DEAT", "BURI", "MARR", "RESI", "OCCU", "CENS", "EVEN",
             "NATU", "IMMI", "EMIG", "PROB", "WILL", "MILI", "EDUC")


@dataclass
class PersonDelta:
    xref: str
    name: str
    facts_before: int
    facts_after: int
    citations_before: int
    citations_after: int
    media_before: int
    media_after: int
    new_fact_summary: List[str] = field(default_factory=list)

    @property
    def gained_facts(self) -> int:
        return self.facts_after - self.facts_before

    @property
    def gained_citations(self) -> int:
        return self.citations_after - self.citations_before

    @property
    def gained_media(self) -> int:
        return self.media_after - self.media_before

    @property
    def unsourced_growth(self) -> bool:
        return self.gained_facts > 0 and self.gained_citations == 0


@dataclass
class DiffReport:
    old_label: str
    new_label: str
    people_before: int
    people_after: int
    families_before: int
    families_after: int
    sources_before: int
    sources_after: int
    media_before: int
    media_after: int

    people_added: List[str] = field(default_factory=list)
    people_removed: List[str] = field(default_factory=list)
    sources_added: List[str] = field(default_factory=list)
    sources_removed: List[str] = field(default_factory=list)
    families_added: List[str] = field(default_factory=list)

    changed: List[PersonDelta] = field(default_factory=list)
    unsourced_growth: List[PersonDelta] = field(default_factory=list)

    added_with_citations: int = 0
    added_without_citations: int = 0
    match_mode: str = "xref"
    shared_people: int = 0        # denominator for the unsourced-growth check
    unchanged_people: int = 0

    @property
    def net_people(self) -> int:
        return self.people_after - self.people_before

    @property
    def net_sources(self) -> int:
        return self.sources_after - self.sources_before


def _fact_signature(ind: Individual) -> List[str]:
    out = []
    for ev in ind.events:
        if ev.tag not in FACT_TAGS:
            continue
        bits = [ev.tag]
        if ev.date.raw:
            bits.append(ev.date.raw)
        if ev.place:
            bits.append(ev.place)
        out.append(" | ".join(bits))
    return sorted(out)


def _count_facts(ind: Individual) -> int:
    return len([e for e in ind.events if e.tag in FACT_TAGS])


def _name_key(ind: Individual) -> Tuple[str, Optional[int]]:
    return (_normalise_name(ind.name), ind.birth_year)


def diff(old: Gedcom, new: Gedcom,
         match_by_name: bool = False) -> DiffReport:
    """Compare two exports of (nominally) the same tree."""
    if match_by_name:
        old_index = {_name_key(i): x for x, i in old.individuals.items()}
        new_index = {_name_key(i): x for x, i in new.individuals.items()}
        old_keys, new_keys = set(old_index), set(new_index)
        shared = [(old_index[k], new_index[k]) for k in old_keys & new_keys]
        added = [new_index[k] for k in new_keys - old_keys]
        removed = [old_index[k] for k in old_keys - new_keys]
        mode = "name+birth-year"
    else:
        old_keys, new_keys = set(old.individuals), set(new.individuals)
        shared = [(x, x) for x in old_keys & new_keys]
        added = sorted(new_keys - old_keys)
        removed = sorted(old_keys - new_keys)
        mode = "xref"

    report = DiffReport(
        old_label=f"{old.export_date or old.path}",
        new_label=f"{new.export_date or new.path}",
        people_before=len(old.individuals),
        people_after=len(new.individuals),
        families_before=len(old.families),
        families_after=len(new.families),
        sources_before=len(old.sources),
        sources_after=len(new.sources),
        media_before=len(old.objects),
        media_after=len(new.objects),
        people_added=sorted(added),
        people_removed=sorted(removed),
        sources_added=sorted(set(new.sources) - set(old.sources)),
        sources_removed=sorted(set(old.sources) - set(new.sources)),
        families_added=sorted(set(new.families) - set(old.families)),
        match_mode=mode,
    )

    for xref in added:
        if new.individuals[xref].citations:
            report.added_with_citations += 1
        else:
            report.added_without_citations += 1

    for old_x, new_x in shared:
        o, n = old.individuals[old_x], new.individuals[new_x]
        delta = PersonDelta(
            xref=new_x,
            name=n.name,
            facts_before=_count_facts(o),
            facts_after=_count_facts(n),
            citations_before=len(o.citations),
            citations_after=len(n.citations),
            media_before=len(o.object_xrefs),
            media_after=len(n.object_xrefs),
        )
        if (delta.gained_facts or delta.gained_citations
                or delta.gained_media):
            before = set(_fact_signature(o))
            delta.new_fact_summary = sorted(set(_fact_signature(n)) - before)
            report.changed.append(delta)
        if delta.unsourced_growth:
            report.unsourced_growth.append(delta)

    report.shared_people = len(shared)
    report.unchanged_people = len(shared) - len(report.changed)
    report.changed.sort(key=lambda d: (-d.gained_facts, d.name))
    report.unsourced_growth.sort(key=lambda d: (-d.gained_facts, d.name))
    return report


def format_report(report: DiffReport, gedcom_new: Optional[Gedcom] = None,
                  max_rows: int = 25) -> str:
    L = []
    L.append(f"GEDCOM diff  ({report.match_mode} matching)")
    L.append("=" * 70)
    L.append(f"  old: {report.old_label}")
    L.append(f"  new: {report.new_label}")
    L.append("")
    L.append(f"{'':<12}{'before':>9}{'after':>9}{'delta':>9}")
    for label, b, a in (
        ("People", report.people_before, report.people_after),
        ("Families", report.families_before, report.families_after),
        ("Sources", report.sources_before, report.sources_after),
        ("Media", report.media_before, report.media_after),
    ):
        L.append(f"{label:<12}{b:>9}{a:>9}{a - b:>+9}")
    L.append("")
    L.append(f"People added   : {len(report.people_added)}  "
             f"({report.added_with_citations} with a citation, "
             f"{report.added_without_citations} without)")
    L.append(f"People removed : {len(report.people_removed)}")
    L.append(f"Sources added  : {len(report.sources_added)}")
    L.append("")
    L.append(f"People present in both exports: {report.shared_people}  "
             f"({report.unchanged_people} completely unchanged)")
    L.append("")
    L.append("FLAG — people who gained facts but no citations "
             f"({len(report.unsourced_growth)} of {report.shared_people} "
             f"checked):")
    if not report.unsourced_growth:
        L.append("  none — the check ran across every shared person and "
                 "found nothing. This import was purely additive.")
    for d in report.unsourced_growth[:max_rows]:
        L.append(f"  {d.name}  +{d.gained_facts} fact(s), "
                 f"+{d.gained_media} media, +0 citations")
        for f in d.new_fact_summary[:4]:
            L.append(f"      {f}")
    if len(report.unsourced_growth) > max_rows:
        L.append(f"  ... and {len(report.unsourced_growth) - max_rows} more")
    return "\n".join(L)
