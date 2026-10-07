"""Data-quality audit.

Every check here answers a question a genealogist would ask before trusting
a record. None of them *fix* anything -- a flag is a prompt for a human, and
several of these patterns (a mother at 51, a 12-year sibling gap) are
perfectly possible and just want a second look.

Where a check needs date precision the file does not have, the flag records
what precision it had. "Flagged on year only" and "flagged on a full date"
are different strengths of claim.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .parse import GedDate, Gedcom, Individual

# --------------------------------------------------------------------------
# Thresholds -- all named, none inline
# --------------------------------------------------------------------------

MOTHER_MIN_AGE = 14
MOTHER_MAX_AGE = 50
FATHER_MIN_AGE = 15
MARRIAGE_MIN_AGE = 15
SIBLING_GAP_YEARS = 12
MAX_LIFESPAN = 100
POSTHUMOUS_YEARS = 0.75          # 9 months
PLACE_NARRATIVE_CHARS = 70
PLACE_PART_CHARS = 30            # a real place component is short

SEVERITY_ORDER = {"impossible": 0, "implausible": 1, "hygiene": 2}


@dataclass
class Flag:
    code: str
    severity: str                 # impossible | implausible | hygiene
    message: str
    people: List[str] = field(default_factory=list)     # xrefs
    detail: str = ""
    precision: str = ""           # "full date" | "year only" | "mixed"

    def sort_key(self) -> Tuple[int, str]:
        return (SEVERITY_ORDER.get(self.severity, 9), self.code)


@dataclass
class Coverage:
    """How many records a check could actually evaluate.

    Without this, a check that found nothing is indistinguishable from a
    check that had no data to work on -- the same "nothing found" vs "I
    looked in the wrong place" distinction the research log insists on.
    """

    check: str
    eligible: int
    skipped_no_data: int
    flags: int

    @property
    def ran(self) -> bool:
        return self.eligible > 0


@dataclass
class AuditResult:
    flags: List[Flag]
    coverage: List[Coverage]

    def by_severity(self, severity: str) -> List[Flag]:
        return [f for f in self.flags if f.severity == severity]

    def __len__(self) -> int:
        return len(self.flags)

    def __iter__(self):
        return iter(self.flags)


# --------------------------------------------------------------------------
# Date arithmetic that refuses to over-claim
# --------------------------------------------------------------------------


def _as_fraction(d: Optional[GedDate]) -> Optional[float]:
    """Year as a float, using month/day when present."""
    if d is None or not d.parsed or d.year is None:
        return None
    frac = float(d.year)
    if d.month:
        frac += (d.month - 1) / 12.0
        if d.day:
            frac += (d.day - 1) / 365.0
    return frac


def _precision(*dates: Optional[GedDate]) -> str:
    kinds = set()
    for d in dates:
        if d is None or not d.parsed:
            continue
        kinds.add("full date" if d.month and d.day else "year only")
    if not kinds:
        return "unknown"
    if len(kinds) == 1:
        return kinds.pop()
    return "mixed"


def _age_between(earlier: Optional[GedDate],
                 later: Optional[GedDate]) -> Optional[float]:
    a, b = _as_fraction(earlier), _as_fraction(later)
    if a is None or b is None:
        return None
    return b - a


def _label(gedcom: Gedcom, xref: str) -> str:
    ind = gedcom.individuals.get(xref)
    if not ind:
        return xref
    b, d = ind.birth_year, ind.death_year
    if b or d:
        return f"{ind.name} ({b or '?'}–{d or '?'})"
    return ind.name


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def check_parent_ages(gedcom: Gedcom) -> List[Flag]:
    flags = []
    for fam in gedcom.families.values():
        for child_xref in fam.children:
            child = gedcom.individuals.get(child_xref)
            if not child or not child.birth:
                continue
            cb = child.birth.date
            for parent_xref, role in (
                (fam.wife, "mother"), (fam.husband, "father")
            ):
                if not parent_xref:
                    continue
                parent = gedcom.individuals.get(parent_xref)
                if not parent or not parent.birth:
                    continue
                age = _age_between(parent.birth.date, cb)
                if age is None:
                    continue
                lo = MOTHER_MIN_AGE if role == "mother" else FATHER_MIN_AGE
                hi = MOTHER_MAX_AGE if role == "mother" else None
                code = None
                if age < 0:
                    code, sev = "PARENT_BORN_AFTER_CHILD", "impossible"
                elif age < lo:
                    code, sev = (f"{role.upper()}_TOO_YOUNG", "impossible")
                elif hi is not None and age > hi:
                    code, sev = (f"{role.upper()}_TOO_OLD", "implausible")
                if code:
                    flags.append(Flag(
                        code=code,
                        severity=sev,
                        message=(f"{_label(gedcom, parent_xref)} was "
                                 f"{age:.0f} at the birth of "
                                 f"{_label(gedcom, child_xref)}"),
                        people=[parent_xref, child_xref],
                        detail=f"family {fam.xref}, role {role}",
                        precision=_precision(parent.birth.date, cb),
                    ))
    return flags


def check_posthumous_births(gedcom: Gedcom) -> List[Flag]:
    """Child born more than 9 months after the father's death.

    Ambiguous dates are handled explicitly. Several records in this file
    carry values like ``1614 or 1618 or 1620 or 14 Mar 1628``. Reading only
    the first year silently misses the impossibility that the last year
    creates, so both readings are evaluated and the flag says which one
    fired.
    """
    flags = []
    for fam in gedcom.families.values():
        if not fam.husband:
            continue
        father = gedcom.individuals.get(fam.husband)
        if not father or not father.death:
            continue
        fd = father.death.date
        for child_xref in fam.children:
            child = gedcom.individuals.get(child_xref)
            if not child or not child.birth:
                continue
            cb = child.birth.date
            gap = _age_between(fd, cb)
            if gap is not None and gap > POSTHUMOUS_YEARS:
                flags.append(Flag(
                    code="POSTHUMOUS_BIRTH",
                    severity="impossible",
                    message=(f"{_label(gedcom, child_xref)} was born "
                             f"{gap:.1f} years after the death of their "
                             f"father {_label(gedcom, fam.husband)}"),
                    people=[fam.husband, child_xref],
                    detail=f"family {fam.xref}; threshold is 9 months",
                    precision=_precision(fd, cb),
                ))
                continue
            # Neither reading fired on the headline values -- try the widest
            # reading the ambiguous text allows.
            if not (cb.ambiguous or fd.ambiguous):
                continue
            latest_birth, earliest_death = cb.year_max, fd.year_min
            if latest_birth is None or earliest_death is None:
                continue
            worst = latest_birth - earliest_death
            if worst > POSTHUMOUS_YEARS:
                flags.append(Flag(
                    code="POSTHUMOUS_BIRTH_IF_AMBIGUOUS_DATE_RESOLVED",
                    severity="implausible",
                    message=(f"{_label(gedcom, child_xref)} would be born "
                             f"{worst:.0f} years after the death of their "
                             f"father {_label(gedcom, fam.husband)} on the "
                             f"latest reading of an ambiguous date"),
                    people=[fam.husband, child_xref],
                    detail=(f"family {fam.xref}; child birth recorded as "
                            f"{cb.raw!r}, father death as {fd.raw!r}. "
                            f"Which year is right decides whether this is "
                            f"impossible or unremarkable."),
                    precision="ambiguous",
                ))
    return flags


def check_marriage_ages(gedcom: Gedcom) -> List[Flag]:
    flags = []
    for fam in gedcom.families.values():
        marr = next((e for e in fam.events if e.tag == "MARR"), None)
        if not marr or not marr.date.parsed:
            continue
        for spouse_xref in fam.spouses():
            spouse = gedcom.individuals.get(spouse_xref)
            if not spouse or not spouse.birth:
                continue
            age = _age_between(spouse.birth.date, marr.date)
            if age is None or age >= MARRIAGE_MIN_AGE:
                continue
            flags.append(Flag(
                code="MARRIAGE_TOO_YOUNG",
                severity="implausible" if age >= 0 else "impossible",
                message=(f"{_label(gedcom, spouse_xref)} was {age:.0f} at "
                         f"marriage ({marr.date.raw})"),
                people=[spouse_xref],
                detail=f"family {fam.xref}",
                precision=_precision(spouse.birth.date, marr.date),
            ))
    return flags


def check_sibling_gaps(gedcom: Gedcom) -> List[Flag]:
    flags = []
    for fam in gedcom.families.values():
        births = []
        for child_xref in fam.children:
            child = gedcom.individuals.get(child_xref)
            if child and child.birth and child.birth.date.parsed:
                births.append((_as_fraction(child.birth.date), child_xref,
                               child.birth.date))
        births = [b for b in births if b[0] is not None]
        births.sort()
        for (y1, x1, d1), (y2, x2, d2) in zip(births, births[1:]):
            gap = y2 - y1
            if gap > SIBLING_GAP_YEARS:
                flags.append(Flag(
                    code="SIBLING_GAP",
                    severity="implausible",
                    message=(f"{gap:.0f}-year gap between "
                             f"{_label(gedcom, x1)} and "
                             f"{_label(gedcom, x2)}"),
                    people=[x1, x2],
                    detail=(f"family {fam.xref}; a gap this wide usually "
                            f"means a missing sibling, a second marriage, "
                            f"or two families merged"),
                    precision=_precision(d1, d2),
                ))
    return flags


def check_lifespans(gedcom: Gedcom) -> List[Flag]:
    flags = []
    for xref, ind in gedcom.individuals.items():
        if not ind.birth or not ind.death:
            continue
        span = _age_between(ind.birth.date, ind.death.date)
        if span is None:
            continue
        if span < 0:
            flags.append(Flag(
                code="NEGATIVE_LIFESPAN",
                severity="impossible",
                message=(f"{_label(gedcom, xref)} died {abs(span):.0f} years "
                         f"before they were born"),
                people=[xref],
                detail=(f"born {ind.birth.date.raw!r}, "
                        f"died {ind.death.date.raw!r}"),
                precision=_precision(ind.birth.date, ind.death.date),
            ))
        elif span > MAX_LIFESPAN:
            flags.append(Flag(
                code="LONG_LIFESPAN",
                severity="implausible",
                message=f"{_label(gedcom, xref)} lived {span:.0f} years",
                people=[xref],
                detail=(f"born {ind.birth.date.raw!r}, "
                        f"died {ind.death.date.raw!r}; over "
                        f"{MAX_LIFESPAN} usually means two people merged"),
                precision=_precision(ind.birth.date, ind.death.date),
            ))
    return flags


def _normalise_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def check_duplicate_people(gedcom: Gedcom) -> List[Flag]:
    """Same normalised name + same birth year (or both blank + same death)."""
    flags = []
    buckets: Dict[Tuple[str, Optional[int]], List[str]] = defaultdict(list)
    for xref, ind in gedcom.individuals.items():
        buckets[(_normalise_name(ind.name), ind.birth_year)].append(xref)
    for (name, year), xrefs in sorted(
        buckets.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)
    ):
        if len(xrefs) < 2 or not name:
            continue
        flags.append(Flag(
            code="DUPLICATE_NAME_DATE",
            severity="hygiene",
            message=(f"{len(xrefs)} people named "
                     f"{gedcom.individuals[xrefs[0]].name!r} born "
                     f"{year if year else '(no birth year)'}"),
            people=xrefs,
            detail=", ".join(xrefs),
            precision="year only" if year else "unknown",
        ))

    # Same name, no birth year on either, but the same death year.
    dbuckets: Dict[Tuple[str, int], List[str]] = defaultdict(list)
    for xref, ind in gedcom.individuals.items():
        if ind.birth_year is None and ind.death_year is not None:
            dbuckets[(_normalise_name(ind.name), ind.death_year)].append(xref)
    for (name, year), xrefs in sorted(dbuckets.items()):
        if len(xrefs) < 2 or not name:
            continue
        flags.append(Flag(
            code="DUPLICATE_NAME_DEATH",
            severity="hygiene",
            message=(f"{len(xrefs)} people named "
                     f"{gedcom.individuals[xrefs[0]].name!r} died {year}, "
                     f"no birth year on any of them"),
            people=xrefs,
            detail=", ".join(xrefs),
            precision="year only",
        ))
    return flags


def check_spouse_death_dates(gedcom: Gedcom) -> List[Flag]:
    flags = []
    for fam in gedcom.families.values():
        spouses = fam.spouses()
        if len(spouses) < 2:
            continue
        dates = []
        for x in spouses:
            ind = gedcom.individuals.get(x)
            if ind and ind.death and ind.death.date.raw:
                dates.append((x, ind.death.date.raw.strip()))
        if len(dates) == 2 and dates[0][1].lower() == dates[1][1].lower():
            flags.append(Flag(
                code="SPOUSES_SAME_DEATH_DATE",
                severity="implausible",
                message=(f"{_label(gedcom, dates[0][0])} and "
                         f"{_label(gedcom, dates[1][0])} share the death "
                         f"date {dates[0][1]!r}"),
                people=[dates[0][0], dates[1][0]],
                detail=(f"family {fam.xref}; possible, but far more often "
                        f"one date was copied onto the other"),
                precision="as written",
            ))
    return flags


# --------------------------------------------------------------------------
# Place-field hygiene
# --------------------------------------------------------------------------

_STREET_RE = re.compile(r"^\s*\d{1,6}\s+[A-Za-z]")
_STREET_WORD_RE = re.compile(
    r"\b(street|avenue|boulevard|road|lane|drive|apt\.?|apartment|"
    r"suite|hwy|highway)\b", re.I)
_NARRATIVE_RE = re.compile(
    r"\b(drowned|leaving from|killed|buried|died|lost at sea|"
    r"probably|possibly|unknown|maybe|or near|near the|on the way)\b", re.I)


def _iter_places(gedcom: Gedcom):
    for xref, ind in gedcom.individuals.items():
        for ev in ind.events:
            if ev.place:
                yield xref, ev.tag, ev.place
    for fam in gedcom.families.values():
        for ev in fam.events:
            if ev.place:
                yield fam.xref, ev.tag, ev.place


def check_place_fields(gedcom: Gedcom) -> List[Flag]:
    flags = []
    for xref, tag, place in _iter_places(gedcom):
        reasons = []
        if _STREET_RE.match(place) or _STREET_WORD_RE.search(place):
            reasons.append("looks like a street address")
        if _NARRATIVE_RE.search(place):
            reasons.append("contains narrative text")
        # Length alone is a bad signal: "Jackson Township, Dauphin County,
        # Pennsylvania, United States of America" is 72 clean characters. What
        # actually marks a non-place is one *component* running long.
        longest = max((len(p.strip()) for p in place.split(",")), default=0)
        if len(place) > PLACE_NARRATIVE_CHARS and longest > PLACE_PART_CHARS:
            reasons.append(f"one component runs {longest} chars — "
                           f"narrative, not a place name")
        if reasons:
            flags.append(Flag(
                code="PLACE_NOT_A_PLACE",
                severity="hygiene",
                message=f"{tag} place {place!r} — {'; '.join(reasons)}",
                people=[xref] if xref.startswith("@I") else [],
                detail=f"record {xref}, tag {tag}",
            ))
    return flags


_US_VARIANTS = {
    "usa", "united states", "united states of america", "us", "u.s.",
    "u.s.a.", "america", "united states of amerca",
}


def check_country_conventions(gedcom: Gedcom) -> List[Flag]:
    counts: Counter = Counter()
    for _xref, _tag, place in _iter_places(gedcom):
        last = place.split(",")[-1].strip()
        if last.lower().rstrip(".") in {v.rstrip(".") for v in _US_VARIANTS}:
            counts[last] += 1
    if len(counts) <= 1:
        return []
    listing = ", ".join(f"{k!r} ×{v}" for k, v in counts.most_common())
    return [Flag(
        code="COUNTRY_NAME_SPLIT",
        severity="hygiene",
        message=(f"{len(counts)} different spellings of the United States "
                 f"in one file"),
        detail=(f"{listing}. One person does not type it "
                f"{len(counts)} ways — this is the signature of several "
                f"trees merged into one."),
    )]


def check_repeated_names(gedcom: Gedcom) -> List[Flag]:
    """Same name at *different* birth years.

    Weaker than a name+date duplicate -- a grandson named for a grandfather
    is normal -- but a tree that has absorbed somebody else's research
    tends to carry several of these, and they are worth eyeballing: two
    people with one name and two birth years are often one person
    entered twice from two different sources.
    """
    flags = []
    buckets: Dict[str, List[str]] = defaultdict(list)
    for xref, ind in gedcom.individuals.items():
        if ind.birth_year is not None:
            buckets[_normalise_name(ind.name)].append(xref)
    for name, xrefs in sorted(buckets.items()):
        if len(xrefs) < 2 or not name:
            continue
        years = [gedcom.individuals[x].birth_year for x in xrefs]
        if len(set(years)) < 2:
            continue          # already caught as a name+date duplicate
        flags.append(Flag(
            code="NAME_REPEATED_DIFFERENT_YEARS",
            severity="hygiene",
            message=(f"{gedcom.individuals[xrefs[0]].name!r} appears "
                     f"{len(xrefs)} times, born "
                     f"{', '.join(str(y) for y in sorted(years))}"),
            people=xrefs,
            detail=("could be a legitimate name repeat down a line, or a "
                    "merge error — the birthplaces usually tell you which"),
            precision="year only",
        ))
    return flags


def check_date_quality(gedcom: Gedcom) -> List[Flag]:
    """Dates carrying several years, and dates with no year at all."""
    ambiguous: List[Tuple[str, str, str]] = []
    unparsed: List[Tuple[str, str, str]] = []
    for xref, ind in gedcom.individuals.items():
        for ev in ind.events:
            if not ev.date.raw:
                continue
            if ev.date.ambiguous:
                ambiguous.append((xref, ev.tag, ev.date.raw))
            elif not ev.date.parsed:
                unparsed.append((xref, ev.tag, ev.date.raw))

    flags = []
    for xref, tag, raw in ambiguous:
        flags.append(Flag(
            code="AMBIGUOUS_DATE",
            severity="hygiene",
            message=f"{_label(gedcom, xref)} — {tag} date {raw!r} names "
                    f"more than one year",
            people=[xref],
            detail=("every calculation on this person depends on which "
                    "reading is taken; the tools take the first"),
        ))
    for xref, tag, raw in unparsed:
        flags.append(Flag(
            code="UNPARSEABLE_DATE",
            severity="hygiene",
            message=f"{_label(gedcom, xref)} — {tag} date {raw!r} contains "
                    f"no year",
            people=[xref],
            detail="kept verbatim and excluded from every age calculation",
        ))
    return flags


_NAME_NOISE_RE = re.compile(
    r"(GG[FM]\d|\d{1,2}\s*GG[FM]|\*\s*\d|[A-Z]\d{5,}|"
    r"\bDNA\b|\bconf\b|\bin will\b|\bsaid \b|\?\?)")


def _has_emoji(s: str) -> bool:
    return any(unicodedata.category(c) == "So" for c in s)


def check_name_fields(gedcom: Gedcom) -> List[Flag]:
    """Research annotations imported as though they were names."""
    flags = []
    for xref, ind in gedcom.individuals.items():
        for name in ind.names:
            raw = name.full.replace("/", " ").strip()
            reasons = []
            if _has_emoji(raw):
                reasons.append("contains an emoji tag")
            if _NAME_NOISE_RE.search(raw):
                reasons.append("contains a research annotation or record id")
            if len(raw) > 60:
                reasons.append(f"unusually long ({len(raw)} chars)")
            if reasons:
                flags.append(Flag(
                    code="NAME_FIELD_NOISE",
                    severity="hygiene",
                    message=f"{raw[:80]!r} — {'; '.join(reasons)}",
                    people=[xref],
                    detail=("someone else's filing system, imported as a "
                            "name; symptom of the member-tree import, not a "
                            "question in itself"),
                ))
                break
    return flags


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

ALL_CHECKS = (
    check_parent_ages,
    check_posthumous_births,
    check_marriage_ages,
    check_sibling_gaps,
    check_lifespans,
    check_duplicate_people,
    check_repeated_names,
    check_spouse_death_dates,
    check_place_fields,
    check_country_conventions,
    check_date_quality,
    check_name_fields,
)


def _coverage(gedcom: Gedcom, flags: List[Flag]) -> List[Coverage]:
    """How much of the file each check could actually see."""
    inds = gedcom.individuals
    counts = Counter(f.code for f in flags)

    def dated(ind) -> bool:
        return bool(ind.birth and ind.birth.date.parsed)

    parent_pairs = 0
    father_death_pairs = 0
    for fam in gedcom.families.values():
        for child_xref in fam.children:
            child = inds.get(child_xref)
            if not child or not dated(child):
                continue
            for p in (fam.husband, fam.wife):
                pi = inds.get(p) if p else None
                if pi and dated(pi):
                    parent_pairs += 1
            fi = inds.get(fam.husband) if fam.husband else None
            if fi and fi.death and fi.death.date.parsed:
                father_death_pairs += 1

    sibling_fams = sum(
        1 for f in gedcom.families.values()
        if len([c for c in f.children if inds.get(c) and dated(inds[c])]) >= 2
    )
    marr_pairs = sum(
        1 for f in gedcom.families.values()
        for e in f.events
        if e.tag == "MARR" and e.date.parsed and f.spouses()
    )
    lifespans = sum(
        1 for i in inds.values()
        if dated(i) and i.death and i.death.date.parsed
    )
    spouse_pairs = sum(
        1 for f in gedcom.families.values()
        if len([x for x in f.spouses()
                if inds.get(x) and inds[x].death
                and inds[x].death.date.raw]) == 2
    )
    places = sum(1 for _ in _iter_places(gedcom))

    def code_total(*codes: str) -> int:
        return sum(counts.get(c, 0) for c in codes)

    return [
        Coverage("parent ages at a child's birth", parent_pairs,
                 len(inds) - parent_pairs,
                 code_total("MOTHER_TOO_YOUNG", "MOTHER_TOO_OLD",
                            "FATHER_TOO_YOUNG", "PARENT_BORN_AFTER_CHILD")),
        Coverage("posthumous births", father_death_pairs, 0,
                 code_total("POSTHUMOUS_BIRTH",
                            "POSTHUMOUS_BIRTH_IF_AMBIGUOUS_DATE_RESOLVED")),
        Coverage("marriage ages", marr_pairs,
                 len(gedcom.families) - marr_pairs,
                 code_total("MARRIAGE_TOO_YOUNG")),
        Coverage("sibling gaps (families with 2+ dated children)",
                 sibling_fams, len(gedcom.families) - sibling_fams,
                 code_total("SIBLING_GAP")),
        Coverage("lifespans (birth and death both dated)", lifespans,
                 len(inds) - lifespans,
                 code_total("LONG_LIFESPAN", "NEGATIVE_LIFESPAN")),
        Coverage("spouse death-date collisions", spouse_pairs,
                 len(gedcom.families) - spouse_pairs,
                 code_total("SPOUSES_SAME_DEATH_DATE")),
        Coverage("place fields", places, 0,
                 code_total("PLACE_NOT_A_PLACE")),
        Coverage("name fields", len(inds), 0,
                 code_total("NAME_FIELD_NOISE")),
    ]


def run_audit(gedcom: Gedcom) -> AuditResult:
    flags: List[Flag] = []
    for check in ALL_CHECKS:
        flags.extend(check(gedcom))
    flags.sort(key=lambda f: f.sort_key())
    return AuditResult(flags=flags, coverage=_coverage(gedcom, flags))


def summarise(result) -> Dict[str, int]:
    flags = result.flags if isinstance(result, AuditResult) else result
    return dict(Counter(f.code for f in flags))

