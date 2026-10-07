"""GEDCOM 5.5.1 parser.

Design notes
------------
This parser deliberately keeps a *lossless* generic tree (``Node``) as the
substrate and layers typed views (``Individual``, ``Family``, ...) on top.
That matters for this project: Ancestry's ``_``-prefixed extension tags
(``_CLON``, ``_TID``, ``_CREA``, ``_APID``, ``_PID``) are load-bearing for
provenance, and every off-the-shelf GEDCOM library we could have used
silently discards them.

Continuation handling follows GEDCOM 5.5.1:
  * ``CONT`` starts a new line   -> value joined with ``"\\n"``
  * ``CONC`` continues the line  -> value joined with ``""`` (no space)

Nothing here interprets or corrects data. A date that cannot be parsed is
retained verbatim with ``parsed=False`` rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

# --------------------------------------------------------------------------
# Low-level line / node model
# --------------------------------------------------------------------------

_LINE_RE = re.compile(r"^(\d+)\s+(?:(@[^@]*@)\s+)?([A-Za-z0-9_]+)(?:\s(.*))?$")
_POINTER_RE = re.compile(r"^@[^@]+@$")

CONTINUATION_TAGS = ("CONT", "CONC")


@dataclass
class Node:
    """One GEDCOM node plus its subordinate nodes."""

    level: int
    tag: str
    value: str = ""
    xref: Optional[str] = None          # only set on level-0 records
    line_no: int = 0
    children: List["Node"] = field(default_factory=list)

    # -- navigation -------------------------------------------------------
    @property
    def pointer(self) -> Optional[str]:
        """The value read as an xref pointer, if it is one."""
        return self.value if _POINTER_RE.match(self.value or "") else None

    def kids(self, *tags: str) -> List["Node"]:
        return [c for c in self.children if c.tag in tags]

    def first(self, *tags: str) -> Optional["Node"]:
        for c in self.children:
            if c.tag in tags:
                return c
        return None

    def value_of(self, *tags: str, default: str = "") -> str:
        n = self.first(*tags)
        return n.value if n is not None else default

    def walk(self) -> Iterator["Node"]:
        """Depth-first over this node and everything under it."""
        yield self
        for c in self.children:
            yield from c.walk()

    def path_value(self, *tags: str, default: str = "") -> str:
        """``node.path_value("FILE", "FORM")`` -> value of FILE/FORM."""
        cur: Optional[Node] = self
        for t in tags:
            if cur is None:
                return default
            cur = cur.first(t)
        return cur.value if cur is not None else default


def _parse_lines(text: str) -> List[Tuple[int, Optional[str], str, str, int]]:
    out = []
    for i, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        m = _LINE_RE.match(line)
        if not m:
            # Malformed line: keep it as a pseudo-node so nothing is lost.
            out.append((99, None, "_UNPARSED", line, i))
            continue
        level, xref, tag, value = m.groups()
        out.append((int(level), xref, tag, value or "", i))
    return out


def parse_text(text: str) -> List[Node]:
    """Parse GEDCOM text into a list of level-0 records."""
    records: List[Node] = []
    stack: List[Node] = []

    for level, xref, tag, value, line_no in _parse_lines(text):
        if tag == "_UNPARSED":
            if stack:
                stack[-1].children.append(Node(99, tag, value, line_no=line_no))
            continue

        if tag in CONTINUATION_TAGS:
            # Attach to the node one level up (the node being continued).
            target = None
            for n in reversed(stack):
                if n.level == level - 1:
                    target = n
                    break
            if target is None and stack:
                target = stack[-1]
            if target is not None:
                sep = "\n" if tag == "CONT" else ""
                target.value = (target.value or "") + sep + value
            continue

        node = Node(level=level, tag=tag, value=value, xref=xref, line_no=line_no)

        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            records.append(node)
        stack.append(node)

    return records


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}

_QUALIFIERS = (
    "abt", "about", "circa", "c", "ca", "cal", "est", "bef", "before",
    "aft", "after", "from", "to", "bet", "between", "and", "or",
)

_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")


@dataclass(frozen=True)
class GedDate:
    """A tolerant GEDCOM date.

    ``parsed`` is False whenever we could not extract a year. Such values are
    kept verbatim and are never guessed at -- a blank field is information.
    """

    raw: str = ""
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    qualifier: str = ""          # "abt", "bef", "aft", "range", ...
    ambiguous: bool = False      # more than one year present in the raw text
    parsed: bool = False
    years: Tuple[int, ...] = ()  # every year in the raw text, in order

    def __bool__(self) -> bool:
        return bool(self.raw)

    @property
    def year_min(self) -> Optional[int]:
        return min(self.years) if self.years else None

    @property
    def year_max(self) -> Optional[int]:
        return max(self.years) if self.years else None

    @property
    def approximate(self) -> bool:
        return bool(self.qualifier) or self.ambiguous

    def __str__(self) -> str:
        return self.raw


def parse_date(raw: str) -> GedDate:
    if not raw or not raw.strip():
        return GedDate()
    text = raw.strip()
    low = text.lower()

    qualifier = ""
    for q in ("bef", "aft", "abt", "about", "circa", "est", "bet", "from", "c."):
        if low.startswith(q):
            qualifier = {"about": "abt", "circa": "abt", "c.": "abt"}.get(q, q)
            break
    if not qualifier and re.search(r"\bor\b|\band\b|/", low):
        qualifier = "range"

    years = [int(y) for y in _YEAR_RE.findall(text)]
    ambiguous = len(set(years)) > 1
    year = years[0] if years else None

    month = None
    for token in re.findall(r"[A-Za-z]+", text):
        t = token.lower().strip(".")
        if t in _MONTHS and t not in _QUALIFIERS:
            month = _MONTHS[t]
            break

    day = None
    # A day is a 1-2 digit number that is not part of the year.
    if month is not None:
        dm = re.search(r"\b(\d{1,2})\b", text)
        if dm:
            candidate = int(dm.group(1))
            if 1 <= candidate <= 31:
                day = candidate
    else:
        # Slash dates: 12/24/1879 (US convention, as written by the importer)
        sm = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if sm:
            month, day, year = int(sm.group(1)), int(sm.group(2)), int(sm.group(3))
            if month > 12:  # defensive; do not silently swap
                month, day = None, None

    return GedDate(
        raw=text,
        year=year,
        month=month,
        day=day,
        qualifier=qualifier,
        ambiguous=ambiguous,
        parsed=year is not None,
        years=tuple(dict.fromkeys(years)),
    )


# --------------------------------------------------------------------------
# Typed views
# --------------------------------------------------------------------------


@dataclass
class Citation:
    source_xref: Optional[str]
    page: str
    apid: str
    www: str
    context_tag: str            # the event/attribute tag it hangs under
    node: Node

    @classmethod
    def from_node(cls, node: Node, context_tag: str) -> "Citation":
        data = node.first("DATA")
        www = data.value_of("WWW") if data else ""
        if not www:
            www = node.value_of("WWW")
        return cls(
            source_xref=node.pointer,
            page=node.value_of("PAGE"),
            apid=node.value_of("_APID"),
            www=www,
            context_tag=context_tag,
            node=node,
        )


@dataclass
class PersonName:
    full: str
    given: str
    surname: str
    suffix: str
    citations: List[Citation]

    @property
    def display(self) -> str:
        return self.full.replace("/", "").strip() or (
            f"{self.given} {self.surname}".strip()
        )


@dataclass
class Event:
    tag: str
    type: str
    date: GedDate
    place: str
    citations: List[Citation]
    node: Node


def _collect_citations(node: Node, context_tag: str) -> List[Citation]:
    """Every SOUR citation anywhere under ``node``, tagged with the event it
    hangs under.

    Citations nest under *any* tag in an Ancestry export -- NAME, BIRT, DEAT,
    RESI, a custom EVEN, or the record root. Flattening them all to "INDI"
    would throw away the one thing that makes a citation interpretable: what
    it is a citation *for*. So the walk carries the nearest enclosing
    event/attribute tag down with it.
    """
    out: List[Citation] = []

    def walk(n: Node, context: str) -> None:
        for child in n.children:
            if child.tag == "SOUR" and child.level > 0:
                out.append(Citation.from_node(child, context))
                # A citation's own subtree (PAGE, DATA, _APID) holds no
                # further citations; do not descend and double-count.
                continue
            next_context = (child.tag
                            if child.tag in _EVENT_TAGS or child.tag == "NAME"
                            else context)
            walk(child, next_context)

    walk(node, context_tag)
    return out


_EVENT_TAGS = {
    "BIRT", "CHR", "DEAT", "BURI", "CREM", "ADOP", "BAPM", "BARM", "BASM",
    "BLES", "CHRA", "CONF", "FCOM", "ORDN", "NATU", "EMIG", "IMMI", "CENS",
    "PROB", "WILL", "GRAD", "RETI", "EVEN", "MARR", "DIV", "DIVF", "ENGA",
    "MARB", "MARC", "MARL", "MARS", "ANUL", "RESI", "OCCU", "EDUC", "MILI",
}


def _build_events(record: Node) -> List[Event]:
    events = []
    for child in record.children:
        if child.tag not in _EVENT_TAGS:
            continue
        events.append(
            Event(
                tag=child.tag,
                type=child.value_of("TYPE"),
                date=parse_date(child.value_of("DATE")),
                place=child.value_of("PLAC"),
                citations=_collect_citations(child, child.tag),
                node=child,
            )
        )
    return events


@dataclass
class Individual:
    xref: str
    node: Node
    names: List[PersonName]
    sex: str
    famc: List[str]             # families this person is a child in
    fams: List[str]             # families this person is a spouse in
    events: List[Event]
    citations: List[Citation]   # every citation anywhere on the record
    object_xrefs: List[str]

    # -- convenience ------------------------------------------------------
    @property
    def name(self) -> str:
        return self.names[0].display if self.names else "(unnamed)"

    @property
    def surname(self) -> str:
        return self.names[0].surname if self.names else ""

    @property
    def given(self) -> str:
        return self.names[0].given if self.names else ""

    def event(self, tag: str) -> Optional[Event]:
        for e in self.events:
            if e.tag == tag:
                return e
        return None

    @property
    def birth(self) -> Optional[Event]:
        return self.event("BIRT")

    @property
    def death(self) -> Optional[Event]:
        return self.event("DEAT")

    @property
    def birth_year(self) -> Optional[int]:
        b = self.birth
        return b.date.year if b else None

    @property
    def death_year(self) -> Optional[int]:
        d = self.death
        return d.date.year if d else None

    @property
    def citation_count(self) -> int:
        return len(self.citations)

    def alt_names(self) -> List[str]:
        seen, out = set(), []
        for n in self.names:
            d = n.display
            if d and d not in seen:
                seen.add(d)
                out.append(d)
        return out


@dataclass
class Family:
    xref: str
    node: Node
    husband: Optional[str]
    wife: Optional[str]
    children: List[str]
    events: List[Event]
    citations: List[Citation]

    @property
    def join_citation_count(self) -> int:
        """Citations on the family record itself -- i.e. on the *join*."""
        return len(self.citations)

    def spouses(self) -> List[str]:
        return [x for x in (self.husband, self.wife) if x]


@dataclass
class Source:
    xref: str
    node: Node
    title: str
    author: str
    publisher: str
    apid: str


@dataclass
class MediaObject:
    xref: str
    node: Node
    title: str
    created: str                # _CREA in *this* tree
    clone: Optional[Node]       # _CLON block, if the media was copied in
    origin: str                 # _ORIG

    @property
    def is_clone(self) -> bool:
        return self.clone is not None

    @property
    def source_tree_id(self) -> str:
        return self.clone.value_of("_TID") if self.clone else ""

    @property
    def source_person_id(self) -> str:
        return self.clone.value_of("_PID") if self.clone else ""

    @property
    def clone_date(self) -> str:
        """Date the media was uploaded to the *originating* tree."""
        return self.clone.value_of("_DATE") if self.clone else ""


@dataclass
class Gedcom:
    path: str
    records: List[Node]
    header: Optional[Node]
    individuals: Dict[str, Individual]
    families: Dict[str, Family]
    sources: Dict[str, Source]
    objects: Dict[str, MediaObject]

    # -- header facts -----------------------------------------------------
    @property
    def export_date(self) -> str:
        if not self.header:
            return ""
        d = self.header.first("DATE")
        if not d:
            return ""
        t = d.value_of("TIME")
        return f"{d.value} {t}".strip()

    @property
    def tree_name(self) -> str:
        if not self.header:
            return ""
        sour = self.header.first("SOUR")
        return sour.value_of("_TREE") if sour else ""

    def parents_of(self, xref: str) -> List[Tuple[str, str]]:
        """[(parent_xref, 'HUSB'|'WIFE'), ...] via the FAMC link."""
        out = []
        ind = self.individuals.get(xref)
        if not ind:
            return out
        for fam_xref in ind.famc:
            fam = self.families.get(fam_xref)
            if not fam:
                continue
            if fam.husband:
                out.append((fam.husband, "HUSB"))
            if fam.wife:
                out.append((fam.wife, "WIFE"))
        return out

    def child_family(self, xref: str) -> Optional[Family]:
        ind = self.individuals.get(xref)
        if not ind or not ind.famc:
            return None
        return self.families.get(ind.famc[0])

    def find_by_name(self, needle: str) -> List[Individual]:
        n = needle.lower().strip()
        return [
            i for i in self.individuals.values()
            if any(n in alt.lower() for alt in i.alt_names())
        ]


def _build_individual(rec: Node) -> Individual:
    names = []
    for nn in rec.kids("NAME"):
        names.append(
            PersonName(
                full=nn.value,
                given=nn.value_of("GIVN"),
                surname=nn.value_of("SURN"),
                suffix=nn.value_of("NSFX"),
                citations=[
                    Citation.from_node(c, "NAME") for c in nn.kids("SOUR")
                ],
            )
        )
    return Individual(
        xref=rec.xref or "",
        node=rec,
        names=names,
        sex=rec.value_of("SEX"),
        famc=[n.value for n in rec.kids("FAMC") if n.pointer],
        fams=[n.value for n in rec.kids("FAMS") if n.pointer],
        events=_build_events(rec),
        citations=_collect_citations(rec, "INDI"),
        object_xrefs=[n.value for n in rec.kids("OBJE") if n.pointer],
    )


def _build_family(rec: Node) -> Family:
    return Family(
        xref=rec.xref or "",
        node=rec,
        husband=rec.value_of("HUSB") or None,
        wife=rec.value_of("WIFE") or None,
        children=[n.value for n in rec.kids("CHIL") if n.pointer],
        events=_build_events(rec),
        citations=_collect_citations(rec, "FAM"),
    )


def _build_object(rec: Node) -> MediaObject:
    return MediaObject(
        xref=rec.xref or "",
        node=rec,
        title=rec.path_value("FILE", "TITL"),
        created=rec.value_of("_CREA"),
        clone=rec.first("_CLON"),
        origin=rec.value_of("_ORIG"),
    )


def parse_file(path: str) -> Gedcom:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        text = fh.read()
    return parse_string(text, path=path)


def parse_string(text: str, path: str = "<string>") -> Gedcom:
    records = parse_text(text)
    header = next((r for r in records if r.tag == "HEAD"), None)

    individuals: Dict[str, Individual] = {}
    families: Dict[str, Family] = {}
    sources: Dict[str, Source] = {}
    objects: Dict[str, MediaObject] = {}

    for rec in records:
        if rec.tag == "INDI" and rec.xref:
            individuals[rec.xref] = _build_individual(rec)
        elif rec.tag == "FAM" and rec.xref:
            families[rec.xref] = _build_family(rec)
        elif rec.tag == "SOUR" and rec.xref:
            sources[rec.xref] = Source(
                xref=rec.xref,
                node=rec,
                title=rec.value_of("TITL"),
                author=rec.value_of("AUTH"),
                publisher=rec.value_of("PUBL"),
                apid=rec.value_of("_APID"),
            )
        elif rec.tag == "OBJE" and rec.xref:
            objects[rec.xref] = _build_object(rec)

    return Gedcom(
        path=path,
        records=records,
        header=header,
        individuals=individuals,
        families=families,
        sources=sources,
        objects=objects,
    )
