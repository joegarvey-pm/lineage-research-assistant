"""The archive registry — what can be searched, where, and what is walled off.

Every research session so far has re-derived the same question from scratch:
*can we search place X for year Y, and how?* Texas was cheap because
`texashistory.unt.edu` turned out to be keyless. Oklahoma was nearly free
because it runs the same software. Kansas was expensive precisely because
that discovery had to happen from nothing, and it ended at a `robots.txt`.

That knowledge lived in agent reports and prose, so it evaporated between
sessions. This module is the durable form of it: a declarative catalogue,
indexed by place and date, that answers the question as a lookup.

**The negatives are the point.** A registry that only lists what works would
let a future session re-attempt the KSHS block, the Illinois 403 and the
missing Kansas gateway — each of which cost real time to establish. Blocked
and absent entries are first-class rows here, carrying the exact evidence.

Design decisions worth stating:

1. **A query never returns a bare empty list.** "No archive covers Ellis
   County in 1860" and "an archive covers it and the name is not there" are
   opposite findings, and the research log's defining failure mode is
   conflating them. `for_place()` returns a structured answer with
   `no_coverage` and `unknown` as distinct, named outcomes.

2. **`verified_on` is mandatory.** Collection availability shifts; a verdict
   with no date is a rumour.

3. **A `BLOCKED` entry must quote the line that blocks it.** "Blocked" with
   no evidence invites somebody to try again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Vocabulary — small and closed, for the same reason evidence.py's is.
# --------------------------------------------------------------------------

OPEN = "OPEN"                                  # keyless machine access works
KEY_REQUIRED = "KEY_REQUIRED"                  # works, but needs a key
BLOCKED = "BLOCKED"                            # robots or WAF says no
NO_MACHINE_INTERFACE = "NO_MACHINE_INTERFACE"  # exists; browser only
ABSENT = "ABSENT"                              # does not exist at all
AUTH_WALLED = "AUTH_WALLED"                    # exists; needs a human login

VERDICTS = (OPEN, KEY_REQUIRED, BLOCKED, NO_MACHINE_INTERFACE, ABSENT,
            AUTH_WALLED)

#: Verdicts a program may actually issue a request against.
AUTOMATABLE = (OPEN, KEY_REQUIRED)

#: ⚠️ READ THIS BEFORE TREATING ANY "BLOCKED" ROW AS FINAL, and it is a
#: correction to how 2026-08-28 first recorded five of them.
#:
#: Anthropic publishes THREE crawlers, and its own support page distinguishes
#: them by purpose:
#:
#:   ClaudeBot         "collecting web content that could potentially
#:                      contribute to their training"
#:   Claude-User       "supports Claude AI users. When individuals ask
#:                      questions to Claude, it may access websites using a
#:                      Claude-User agent" — i.e. USER-INITIATED requests
#:   Claude-SearchBot  search indexing
#:
#: EVERY ONE of the five sources that closed on 2026-08-28 names **ClaudeBot**
#: and **none of them names Claude-User**. Four of them go further and declare,
#: in their wildcard group:
#:
#:     User-agent: *
#:     Content-Signal: search=yes,ai-train=no,use=reference
#:     Allow: /
#:
#: So the operators separated TRAINING from REFERENCE USE, blocked the
#: training crawler, and permitted reference use explicitly. UNT's two sites
#: have no content signal but their wildcard group allows everything except
#: /stats/, /feedback/ and */zoom/, at Crawl-delay: 3.
#:
#: WHAT THAT DOES AND DOES NOT LICENCE. It does not license this package to
#: fetch them: BLOCKED stays BLOCKED here, and the portal adapter still
#: refuses. What it does is describe accurately WHO is blocked, so that the
#: humane routes are visible instead of buried:
#:   * a person in their own browser is not a crawler and never was;
#:   * a research fetcher you operate under your own identity is
#:     addressed by the wildcard group, not by the ClaudeBot group;
#:   * and an operator who writes "use=reference" is an operator worth
#:     emailing.
#: Recording a block without recording WHICH AGENT it names is the same
#: failure as recording a null without its denominator.
CLAUDE_AGENTS = {
    "claudebot": "training crawler",
    "claude-user": "user-initiated requests",
    "claude-searchbot": "search indexing",
}

#: Verdicts that mean "a human can get this, you cannot".
MANUAL_ONLY = (BLOCKED, NO_MACHINE_INTERFACE, AUTH_WALLED)


class RegistryError(ValueError):
    pass


# --------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------

_COUNTY_RE = re.compile(r"\b(county|co\.?|parish)\b", re.I)

#: This tree carries three spellings of the same country, because it is a
#: merge of many trees -- a structural finding worth knowing. A trailing
#: country token is dropped so "Fairview, Logan County, Kansas, USA"
#: resolves to Kansas rather than to a country called "usa".
US_COUNTRY = frozenset({
    "usa", "us", "u.s.", "u.s.a.", "united states",
    "united states of america",
})

#: The registry stores full state names; records and prompts use both.
# ⭐ COMPLETED 2026-08-31. This table held fifteen abbreviations, chosen by
# whichever states the project had happened to touch, so any record naming one
# of the other thirty-six parsed its state as an unrecognised string. That is
# invisible until something downstream asks "is this a real state?" — which
# `census.place_for_year` began asking the same day.
STATE_NAMES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut",
    "de": "delaware", "dc": "district of columbia", "fl": "florida",
    "ga": "georgia", "hi": "hawaii", "id": "idaho", "il": "illinois",
    "in": "indiana", "ia": "iowa", "ks": "kansas", "ky": "kentucky",
    "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota",
    "ms": "mississippi", "mo": "missouri", "mt": "montana",
    "ne": "nebraska", "nv": "nevada", "nh": "new hampshire",
    "nj": "new jersey", "nm": "new mexico", "ny": "new york",
    "nc": "north carolina", "nd": "north dakota", "oh": "ohio",
    "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota",
    "tn": "tennessee", "tx": "texas", "ut": "utah", "vt": "vermont",
    "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming",
}

#: A trailing country stuck to the state with no comma between them:
#: "Washington,Ky USA" is a real value seen in the wild, and it tends to
#: appear on BOTH parents of a couple at once, so it can silently break a
#: whole generation rather than one person. Splitting on the comma
#: leaves "Ky USA" as the region, which matches no state.
_TRAILING_COUNTRY = re.compile(
    r"[\s,]+(u\.?\s?s\.?\s?a\.?|u\.?\s?s\.?"
    r"|united\s+states(\s+of\s+america)?)\.?$", re.I)


@dataclass(frozen=True)
class Place:
    """A parsed place. `county` and `city` may be empty; `region` may not."""

    region: str = ""     # state, or country for non-US
    county: str = ""
    city: str = ""

    def __str__(self) -> str:
        bits = [b for b in (self.city.title(),
                            self.county and f"{self.county.title()} County",
                            self.region.title()) if b]
        return ", ".join(bits)


def parse_place(text: str) -> Place:
    """"Ellis County, Texas" -> Place(region='texas', county='ellis').

    Tolerant on purpose: place strings in this project come from GEDCOM
    fields typed by four different people across three data-entry
    conventions, and from prompts written by hand.
    """
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    while len(parts) > 1 and parts[-1].lower() in US_COUNTRY:
        parts.pop()
    if not parts:
        return Place()
    region = _TRAILING_COUNTRY.sub("", parts[-1]).strip().lower()
    region = STATE_NAMES.get(region.replace(".", "").replace(" ", ""), region)
    county = city = ""
    for p in parts[:-1]:
        if _COUNTY_RE.search(p):
            # "Carroll Co., VA." leaves a stray period behind the regex, and
            # a county named "carroll ." matches nothing in VERIFIED_WINDOWS.
            county = _COUNTY_RE.sub("", p).strip(" .,").lower()
        elif not city:
            city = p.lower()
    # "Fairview, Logan, Kansas" — Ancestry's own three-part form, where the
    # middle element is a county with the word "County" left off.
    if not county and len(parts) >= 3:
        county, city = parts[-2].strip().lower(), parts[0].strip().lower()
    return Place(region=region, county=county, city=city)


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Holding:
    """What one archive holds for one place.

    `titles == 0` is a deliberate, load-bearing value: it records that the
    place was *checked* and holds nothing, which is what makes a later null
    a coverage gap rather than an absence.
    """

    region: str                       # state or country, lowercase
    county: str = ""                  # "" means the whole region
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    titles: Optional[int] = None      # None = unknown/not a title-based archive
    note: str = ""
    #: What CLASS of record this row is about. Empty means unspecified, which
    #: is what all 96 seeded rows are: the registry grew up answering one
    #: question — "is there a digitised newspaper for this county and year?" —
    #: and its holdings model is newspaper-shaped down to the `titles` count.
    #:
    #: Probate is the first record class that does not fit that shape. A
    #: county clerk's estate files have no "titles", are not digitised at all,
    #: and are held by an office rather than an archive. Rather than pretend a
    #: probate row is a newspaper row, holdings now declare their class, and a
    #: query for one class NEVER answers from a row of another.
    #:
    #: The default stays empty on purpose. Retro-labelling 96 rows
    #: "newspapers" from memory would be exactly the kind of asserted fact
    #: this module exists to stop; they say nothing, which is true.
    record_type: str = ""
    #: Years INSIDE the span that hold nothing. Added 2026-08-28 to fix a
    #: silent contradiction: this row's own note has said since 2026-08-25
    #: that a county held "zero issues for ... 1922, 1924-1925 ..", and
    #: `holds(1924)` answered "a null for 1924 is a REAL negative result",
    #: because it only compared against the ends of the span.
    #:
    #: That is precisely the error this module exists to prevent, and it
    #: landed on exactly the year that mattered — the ancestor in question
    #: died in that county in 1924. The note was right and the code wrong,
    #: and a note the code contradicts is worse than no note at all.
    gap_years: Tuple[int, ...] = ()

    def matches(self, place: Place) -> bool:
        if place.region and self.region and place.region != self.region:
            return False
        if self.county and place.county and self.county != place.county:
            return False
        if self.county and not place.county:
            return False          # we hold a county; the query is statewide
        return True

    @property
    def informative(self) -> bool:
        """Does this row actually say something a searcher can use?

        A statewide row with no county, no year span and no title count says
        only "this archive covers Kansas somehow", which is not evidence that
        a search there for a particular county and year would mean anything.
        Promoting one of those into an answer manufactures reassurance —
        which is the same failure as logging a coverage gap as an absence,
        wearing a different hat.
        """
        return bool(self.county or self.start_year or self.end_year
                    or self.titles is not None or self.gap_years)

    def holds(self, year: Optional[int]) -> Tuple[bool, str]:
        """Can a search of this holding for `year` mean anything?"""
        where = (f"{self.county.title()} County, {self.region.title()}"
                 if self.county else self.region.title())
        if self.titles == 0:
            return False, (
                f"{where}: nothing digitised. A null here is a COVERAGE GAP, "
                f"not an absence — do not log it as 'nothing found'.")
        if year is None:
            return True, f"{where}: held."
        if self.start_year and year < self.start_year:
            return False, (
                f"{where}: coverage starts {self.start_year}. {year} is "
                f"before it — a null is a COVERAGE GAP, not an absence.")
        if self.end_year and year > self.end_year:
            return False, (
                f"{where}: coverage ends {self.end_year}. {year} is past it "
                f"— a null is a COVERAGE GAP, not an absence.")
        if year in self.gap_years:
            return False, (
                f"{where}: {year} is INSIDE the span but ZERO issues are "
                f"digitised for it. A null is a COVERAGE GAP, not an "
                f"absence — the run is not continuous.")
        span = (f"{self.start_year or '?'}–{self.end_year or '?'}"
                if (self.start_year or self.end_year) else "full run")
        titles = f"{self.titles} title(s), " if self.titles else ""
        return True, (f"{where}: {titles}{span}. A null for {year} is a REAL "
                      f"negative result.")


# --------------------------------------------------------------------------
# Archives
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Archive:
    key: str
    name: str
    base_url: str
    operator: str
    verdict: str
    verified_on: str                 # YYYY-MM-DD
    robots: str = ""                 # what robots.txt says, in words
    disallow_line: str = ""          # the exact line, when BLOCKED by robots
    recipe: str = ""                 # endpoints, working params, known traps
    adapter: str = ""                # treetools module that drives it, if any
    holdings: Tuple[Holding, ...] = ()
    notes: str = ""
    #: What class of record this archive holds, when a holding does not say.
    #:
    #: The registry was seeded with 96 holdings that all answer one question —
    #: "is there a digitised newspaper for this county and year?" — and none
    #: declares a record type. Labelling all 96 by hand would be asserting 96
    #: facts. Labelling the ARCHIVE asserts one, and it is a fact the
    #: archive's own name and recipe already state: Chronicling America holds
    #: newspapers; the Missouri State Archives database holds death
    #: certificates. A holding may still override it.
    #:
    #: 2026-08-28 made the ambiguity real. Once one county had a PROBATE
    #: holding as well as a NEWSPAPER one, "what can I search for that
    #: County in 1924?" stopped having a single answer: **searchable for
    #: probate, a coverage gap for newspapers**. An answer that does not say
    #: which is worse than no answer at all.
    #: "mixed" is a real value, not a cop-out: FamilySearch holds census,
    #: vital AND probate film, and saying so is honest where picking one
    #: would be a lie. The strict filter then answers a probate query about a
    #: "mixed" archive with UNKNOWN — "nobody has looked" — which is exactly
    #: right, because nobody has.
    default_record_type: str = ""

    def validate(self) -> List[str]:
        problems = []
        if self.verdict not in VERDICTS:
            problems.append(
                f"{self.key}: verdict {self.verdict!r} not in {VERDICTS}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.verified_on or ""):
            problems.append(
                f"{self.key}: verified_on must be YYYY-MM-DD, got "
                f"{self.verified_on!r}")
        if self.verdict == BLOCKED and not (self.disallow_line or self.robots):
            problems.append(
                f"{self.key}: BLOCKED with no evidence. Quote the robots line "
                f"or the HTTP status, or somebody will try again.")
        if self.verdict in AUTOMATABLE and not self.recipe:
            problems.append(
                f"{self.key}: {self.verdict} but no access recipe — an open "
                f"archive nobody knows how to call is not open in practice.")
        return problems

    @property
    def automatable(self) -> bool:
        return self.verdict in AUTOMATABLE

    def type_of(self, holding: Holding) -> str:
        """The record class of one holding: its own, else the archive's."""
        return holding.record_type or self.default_record_type

    def holding_for(self, place: Place,
                    record_type: Optional[str] = None) -> Optional[Holding]:
        """Most specific matching holding.

        A county row beats a state row, and a state row beats a nationwide
        one. Without the second term FamilySearch answered a Lima query
        from its US-census row, which is the wrong record set entirely.

        `record_type` narrows to one class of record and does so STRICTLY: a
        probate query is never answered from a newspaper row, and if this
        archive declares no probate holding for the place the answer is None
        — which the caller reports as UNKNOWN, meaning "nobody has looked",
        not "nothing exists". Asked without one, the historical rows win the
        tie, so every existing query answers exactly as it did before.
        """
        candidates = [h for h in self.holdings if h.matches(place)]
        if record_type is not None:
            candidates = [h for h in candidates
                          if self.type_of(h) == record_type]
        if not candidates:
            return None
        return sorted(candidates,
                      key=lambda h: (0 if h.county else 1,
                                     0 if h.region else 1,
                                     0 if not h.record_type else 1))[0]


# --------------------------------------------------------------------------
# The registry itself
#
# Seeded 2026-08-26 with every verdict established on 2026-08-25 and
# 2026-08-26. Nothing here was re-verified for the seeding — the evidence is
# in 01 Research Log.md, and re-running settled checks is waste, not
# diligence. New verdicts carry their own `verified_on`.
# --------------------------------------------------------------------------

REGISTRY: Dict[str, Archive] = {}


def register(a: Archive) -> Archive:
    problems = a.validate()
    if problems:
        raise RegistryError("; ".join(problems))
    if a.key in REGISTRY:
        raise RegistryError(f"duplicate archive key: {a.key}")
    REGISTRY[a.key] = a
    return a


# --- OPEN, keyless, driven by treetools.portal ----------------------------

# ==========================================================================
# THE REGISTRY
# ==========================================================================
#
# What ships here is the ACCESS map, not anybody's research: for each
# archive, where it lives, whether a program may issue requests against it,
# what its robots.txt actually says, and the working endpoints and known
# traps for getting data out of it.
#
# What deliberately does NOT ship is `holdings=` -- the per-county,
# per-year, per-record-type coverage findings. Those are the output of
# somebody's own research and they belong in your own tree, not in a shared
# package. Add yours as you establish them:
#
#     register(Archive(
#         key="my-county-clerk",
#         name="Example County Clerk",
#         base_url="https://example.gov",
#         operator="Example County",
#         verdict=NO_MACHINE_INTERFACE,
#         verified_on="2026-01-15",
#         holdings=(
#             Holding("kansas", "example", 1885, 1920, None,
#                     "Probate minutes, confirmed by phone 2026-01-15. "
#                     "No gap. Not digitised -- copies by mail, $1/page.",
#                     record_type="probate"),
#         ),
#     ))
#
# ⚠️ EVERY `verified_on` BELOW IS A PAST OBSERVATION, NOT A PROMISE.
# robots.txt changes, archives go offline, and free tiers get withdrawn.
# A verdict older than a few months should be re-checked before you build
# a plan on it.
# ==========================================================================

register(Archive(
    key="advantage-archives-corporate",
    name="Advantage Archives (corporate site)",
    base_url="https://advantagearchives.com",
    operator="Advantage Companies",
    verdict=BLOCKED,
    verified_on="2026-08-26",
    robots="disallowed",
    disallow_line="Disallow: /",
    recipe=("DO NOT REQUEST. The per-library *.advantage-preservation.com hosts "
        "are a separate entry and are open."),
))

register(Archive(
    key="advantage-preservation",
    name="Advantage Preservation — Community History Archives",
    base_url="https://*.advantage-preservation.com",
    operator="Advantage Companies, hosted per-library",
    verdict=OPEN,
    verified_on="2026-08-26",
    robots="restricts only Twitterbot; full text is open and keyless",
    recipe=("31 separate Kansas instances, one per host library, each on its "
        "own *.advantage-preservation.com subdomain. Keyless full-text "
        "search. NOTE the operator's own corporate site "
        "advantagearchives.com is robots-BLOCKED — see the separate entry. "
        "The per-library archive hosts are not."),
    default_record_type="newspapers",
    notes=("Coverage is thin exactly where this family needs it. Delyte "
        "Ashlock returning zero is a COVERAGE GAP: Greenwood County, where "
        "she lived, has never been digitised here."),
))

register(Archive(
    key="agn-peru-registros-civiles",
    name=("Archivo General de la Nación del Perú — Búsqueda de Registros "
        "Civiles"),
    base_url="https://regciviles.agn.gob.pe/registrociviles/",
    operator="Archivo General de la Nación del Perú",
    verdict=OPEN,
    verified_on="2026-08-26",
    robots="no robots.txt at all (404) — nothing is disallowed",
    recipe=("A name-level index of civil-registry books, keyless, POST JSON "
        "out. POST to ajax/datatable-registro-na.ajax.php (births), "
        "ajax/datatable-registro-de.ajax.php (deaths), "
        "ajax/datatable-registro-ma.ajax.php (marriages) with "
        "serie_id=1|2|3 and ape_pater / ape_mater / nombres. Returns "
        "{\"data\": [[#, fondo, serie, subserie, año, codLibro, numFolio, "
        "apellido paterno, apellido materno, nombres, fecha del hecho, "
        "fecha de inscripción, ubicación topográfica], ...]}. For a "
        "fondo-scoped search use ajax/datatable-registro.ajax.php with "
        "fondo_id. THE POINT: the search fields are paternal surname and "
        "maternal surname separately, which is exactly the Spanish "
        "two-surname structure this project needs and which US-clerk forms "
        "destroy. Marriage rows give BOTH spouses' full two-surname names. "
        "It is an INDEX, not images: it returns book, folio and shelf "
        "location so a human can order the acta."),
    default_record_type="vital",
    notes=("Found 2026-08-26 and it overturns the prior expectation that no "
        "non-FamilySearch route to Lima civil registration existed. AGN's "
        "own AtoM repository (fondosdocumentales.agn.gob.pe) has no OAI-PMH "
        "endpoint; this search app is the useful interface."),
))

register(Archive(
    key="ancestry",
    name="Ancestry",
    base_url="https://www.ancestry.com",
    operator="Ancestry.com Operations Inc.",
    verdict=AUTH_WALLED,
    verified_on="2026-08-25",
    robots="403 to automated fetches; terms prohibit automation",
    recipe=("DO NOT REQUEST PROGRAMMATICALLY. URL grammar derived from URLs "
        "Ancestry itself generated plus four open-source builders: there is "
        "NO dbid= parameter — the collection is a path segment. 1910 census "
        "= 7884, 1920 = 6061."),
    adapter="treetools.worklist (pre-built URLs for a human only)",
))

register(Archive(
    key="chronicling-america",
    name="Chronicling America",
    base_url="https://www.loc.gov/collections/chronicling-america/",
    operator="Library of Congress / NEH",
    verdict=OPEN,
    verified_on="2026-08-25",
    robots=("no relevant disallow; published limit 20 requests/minute, one-hour "
        "block if exceeded"),
    recipe=("q=<terms>&dl=page&fo=json&dates=YYYY/YYYY&fa=location_state:<state>|location_county:<county>. "
        "TRAPS, all of which return HTTP 200 with the filter silently "
        "dropped: qs= is ignored (returns all 23.8M pages); start_date= and "
        "end_date= are ignored; location_state= is ignored (a Kansas query "
        "returned an Iowa paper). Hit counts are UNSTABLE — q=fairview "
        "returned six different totals in one session and one batch "
        "returned zero for everything including a known-good control, so A "
        "ZERO CAN BE FALSE; always run a positive control. The search "
        "`description` field is the HEAD OF THE PAGE, not the matched text "
        "— verify every hit against the real OCR via the item JSON's "
        "undocumented `fulltext_service` link. The legacy "
        "chroniclingamerica.loc.gov search API is dead (308 then 404)."),
    adapter="treetools.newspapers",
    default_record_type="newspapers",
    notes=("Checked against all ten counties this family lives in: only two "
        "hold anything and neither reaches past 1920, so the collection's "
        "1963 ceiling never comes into play. The US Newspaper Directory "
        "confirms the papers existed — Enid 53 records, Battle Creek 49, "
        "Galena 47, Denton 23, Yates Center 23 — with 0 digitised in every "
        "case. They are microfilm."),
))

register(Archive(
    key="contentdm-state-archives",
    name="CONTENTdm state digital archives (TN, AL, DE, KY)",
    base_url="https://teva.contentdm.oclc.org",
    operator=("Tennessee State Library and Archives; Alabama Dept of Archives and "
        "History; Delaware Public Archives; Kentucky Virtual Library"),
    verdict=NO_MACHINE_INTERFACE,
    verified_on="2026-08-28",
    robots=("A second vendor pattern, and a milder one. Every CONTENTdm "
        "instance disallows /digital/search/ and then enumerates every "
        "per-collection /digital/collection/<code>/search/ path "
        "individually — dozens of lines, deliberately written, all of them "
        "the search. Nothing else on the host is disallowed. Checked "
        "2026-08-28: teva.contentdm.oclc.org (Tennessee Virtual Archive), "
        "digital.archives.alabama.gov, cdm16397.contentdm.oclc.org "
        "(Delaware), kdl.kyvl.org."),
    disallow_line=("User-agent: * / Disallow: /digital/search/ (+ every "
        "/digital/collection/<code>/search/ path)"),
    recipe=("Browser only. The CONTENTdm API lives on a path robots.txt does "
        "not name, and this project is NOT taking that door: the operator "
        "disallowed the search function, and calling the same function "
        "under a different path is working round the block, not respecting "
        "it. Settled 2026-08-28 with the rest of the access question."),
    default_record_type="mixed",
    notes=("Two adjacent hosts ARE open and are worth knowing: "
        "alabamamosaic.org disallows only /vufind/ (Crawl-delay: 30), and "
        "archives.delaware.gov disallows only /wp-admin. Neither is a "
        "newspaper or vital-record index, so neither has been given its own "
        "entry yet — evaluate before searching."),
))

register(Archive(
    key="county-and-court-gov-hosts",
    name=("County and state-court .gov hosts naming this agent (Clay Co MO; "
        "Kansas Judicial Branch)"),
    base_url="https://www.claycountymo.gov",
    operator="various US county and state governments",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("Both claycountymo.gov and www.kscourts.gov serve the same "
        "Cloudflare-managed pattern: 'User-agent: *' with 'Content-Signal: "
        "search=yes,ai-train=no,use=reference' and 'Allow: /', followed by "
        "named groups — Amazonbot, Applebot-Extended, Bytespider, CCBot, "
        "**ClaudeBot**, CloudflareBrowserRenderingCrawler, Google-Extended, "
        "GPTBot, meta-externalagent and more — each 'Disallow: /'. Fetched "
        "directly 2026-08-28. DO NOT REQUEST."),
    disallow_line="User-agent: ClaudeBot Disallow: /",
    notes=("⚠️ AND THEIR WILDCARD GROUP SAYS THE OPPOSITE OF THE NAMED ONE. "
        "Both declare `Content-Signal: "
        "search=yes,ai-train=no,use=reference` followed by `Allow: /`. The "
        "operators permitted REFERENCE use explicitly and blocked the "
        "TRAINING crawlers — ClaudeBot, GPTBot, CCBot, Google-Extended and "
        "the rest of the Cloudflare AI bundle. **Claude-User is not named "
        "on either host.** These are the two sites where writing to ask is "
        "most likely to work, and where the records are not online anyway: "
        "the answer for a county clerk is a letter. One row because it is "
        "one pattern, and the pattern IS the finding: a Cloudflare-supplied "
        "default now appearing on ordinary county and court websites, "
        "rather than a decision each county made. It closes the "
        "custodian-side research this project needs — Clay County "
        "Missouri's own pages (Robert Louis Hartley Sr's 1974 estate) and "
        "the Kansas Judicial Branch (Wilson County probate, and the 1914 "
        "guardianship that could move Daniel S. Marsh off 10%). Both are "
        "free to a human. NOT in this group: www.circuit7.net, the 7th "
        "Judicial Circuit, whose robots disallows only /WebResource.axd — "
        "that is where the Clay County probate contact and fee order were "
        "read."),
))

register(Archive(
    key="dpla",
    name="Digital Public Library of America",
    base_url="https://dp.la",
    operator="DPLA",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("Names this agent explicitly: 'User-agent: ClaudeBot / Disallow: "
        "/', alongside GPTBot, anthropic-ai, CCBot, Google-Extended and "
        "Amazonbot. api.dp.la returns 404 to robots.txt and to its own "
        "root."),
    disallow_line="User-agent: ClaudeBot Disallow: /",
    recipe=("DO NOT REQUEST. Free to a human in a browser. DPLA aggregates "
        "records it does not hold, so its practical loss here is discovery, "
        "not content — the underlying state archives are all in this "
        "registry with their own verdicts."),
))

register(Archive(
    key="familysearch",
    name="FamilySearch",
    base_url="https://www.familysearch.org",
    operator="The Church of Jesus Christ of Latter-day Saints",
    verdict=AUTH_WALLED,
    verified_on="2026-08-25",
    robots="terms prohibit automated access; the API is closed to individuals",
    recipe=("DO NOT REQUEST PROGRAMMATICALLY. Free account required; a human "
        "clicks. treetools.worklist emits pre-built search URLs instead. "
        "URL grammar verified 2026-08-25: places are plain strings, not "
        "numeric IDs; wildcards * and ? work with a 3-letter minimum. "
        "Confirmed collection IDs: 1910 census 1727033, 1920 census "
        "1488411, 1940 census 2000219, 1950 census 4464515, Kansas Deaths "
        "and Burials 1885-1930 1674844, Peru/Lima Civil Registration "
        "1683-1998 1430936, WWI draft 1968530. TRAP: do NOT use collection "
        "2384979 (Kansas Deaths 1811-1940) — its indexed counties are "
        "Atchison, Cherokee, Crawford, Miami, Montgomery and Osage only, so "
        "Wilson County is not in it and a miss there would mean nothing."),
    adapter="treetools.worklist (pre-built URLs for a human only)",
    default_record_type="mixed",
    notes=("Everything auth-walled becomes a pre-built URL in Worklist.md. ⚠️ "
        "This row is the catalog/record SEARCH only. The free-text Research "
        "Wiki (one article per county, no login) is a separate row — see "
        "key 'familysearch-wiki', added 2026-08-29."),
))

register(Archive(
    key="familysearch-wiki",
    name="FamilySearch Research Wiki — county finding-aid pages",
    base_url="https://www.familysearch.org/en/wiki/",
    operator="The Church of Jesus Christ of Latter-day Saints",
    verdict=OPEN,
    verified_on="2026-08-29",
    robots=("checked 2026-08-29: /en/wiki/ is NOT in the disallow list. "
        "Disallowed paths are /auth/, /campaign, /frontier/, /identity/, "
        "/learningcenter, /mgmt/, /pal:/, /photos/*, /profile/, "
        "/records/pal:/, /recover/, /register/, /Search/, /tree/* "
        "(several), /search/all-collections/results/ and "
        "/search/catalog/results — the CATALOG and record SEARCH paths are "
        "walled, the WIKI is not. No ClaudeBot-specific group."),
    recipe=("⭐ A DIFFERENT PART OF FAMILYSEARCH THAN THE 'familysearch' ROW "
        "ABOVE. That row (AUTH_WALLED) is the record catalog and search — "
        "login required, confirmed again 2026-08-29 when "
        "familysearch.org/search/catalog/<id> returned only a sign-in page "
        "to a plain fetch. THIS row is the free-text Research Wiki, one "
        "article per county: /en/wiki/<County>_County,_<State>_Genealogy — "
        "readable with a plain GET, no login, no JS render required for the "
        "prose content. It answers coverage questions directly: what record "
        "series exist, what years, whether a courthouse burned, and where "
        "the record physically sits today. It is NOT a search interface and "
        "holds no images — it is the finding aid that tells you which "
        "FamilySearch catalog entry (AUTH_WALLED) or which courthouse to go "
        "to next. ⚠️ The wiki page's own catalog-record links still resolve "
        "to the AUTH_WALLED search — reading the wiki does not open the "
        "record."),
    default_record_type="mixed",
    notes=("Added 2026-08-29 for the Kentucky Wall session (John Hartley / "
        "Amelia Lightfoot / Leroy Smith Vale estates). The wiki cannot "
        "answer whether the SPECIFIC 1833/1848/1853 volume of a series "
        "survives and what a copy costs — that is a question for the county "
        "clerk, named per-county in your action items. Jefferson County, "
        "Pennsylvania added 2026-08-30 for the same reason, one state over. "
        "⚠️ GENERATION SIX PART D (2026-08-30): a plain `curl` fetch of "
        "/en/wiki/Virginia_Vital_Records returned an Incapsula "
        "bot-challenge page (856 bytes, an <iframe> to /_Incapsula_Resource "
        "with an incident ID), not article content — a live counter-example "
        "to this row's own 2026-08-29 verdict that /en/wiki/ renders to a "
        "plain fetch. Coverage varies by day and by page even on a host "
        "already marked OPEN; do not assume yesterday's success repeats. "
        "See the new lva-virginia-libguides entry for the source that DID "
        "work for the same question."),
))

register(Archive(
    key="findagrave",
    name="Find a Grave",
    base_url="https://www.findagrave.com",
    operator="Ancestry.com Operations Inc.",
    verdict=AUTH_WALLED,
    verified_on="2026-08-25",
    robots="403 to automated fetches",
    recipe=("DO NOT REQUEST PROGRAMMATICALLY. There is no 'within N miles' "
        "parameter."),
    adapter="treetools.worklist (pre-built URLs for a human only)",
))

register(Archive(
    key="gateway-oklahoma",
    name="Gateway to Oklahoma History",
    base_url="https://gateway.okhistory.org",
    operator="Oklahoma Historical Society",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("CHANGED VERDICT 2026-08-28, in the same read as portal-texas and "
        "for the same reason: robots.txt is BYTE-FOR-BYTE the same policy, "
        "which is itself the finding. UNT runs one platform for both, so "
        "one robots decision closed both archives at once. Named group: "
        "'User-agent: ClaudeBot' / 'Disallow: /'. The wildcard group "
        "disallows only /stats/, /feedback/ and */zoom/ and declares "
        "Crawl-delay: 3 — this is a decision about this agent, not about "
        "crawlers. Fetched directly 2026-08-28; nothing else requested."),
    disallow_line="User-agent: ClaudeBot Disallow: /",
    recipe=("*** DO NOT REQUEST — FOR A HUMAN IN A BROWSER ONLY from "
        "2026-08-28. *** Identical UNT software to portal-texas: same "
        "/search/feed/ Atom endpoint, same metadata.untl.xml and "
        "m1/<page>/ocr.txt paths, same 'no special key' notice. "
        "treetools.portal drives both from one code path — adding a state "
        "is one dictionary entry. TRAP: unquoted multi-word queries "
        "returned exactly 50 results, all from the Muskogee Daily Phoenix, "
        "on every attempt. Quote phrases."),
    adapter="treetools.portal — GUARDED, raises portal.BlockedArchive",
    default_record_type="newspapers",
    notes=("⚠️ Same agent-specific shape as portal-texas: **ClaudeBot** named, "
        "**Claude-User not named**, wildcard group permissive at "
        "Crawl-delay 3. Cross-state searching paid off here: a police captain named in "
        "one state's papers surfaced in a NEIGHBOURING state's papers "
        "because they carried the same murder case. Cross-state searching "
        "pays off more often than people expect."),
))

register(Archive(
    key="georgia-historic-newspapers",
    name="Georgia Historic Newspapers",
    base_url="https://gahistoricnewspapers.galileo.usg.edu",
    operator="Digital Library of Georgia, University System of Georgia",
    verdict=OPEN,
    verified_on="2026-08-28",
    robots=("Disallow: /data/, /*.pdf$, /*.txt$, /*.xml$ only. **/search/ is "
        "NOT disallowed**, which is what separates this from South "
        "Carolina's otherwise identical setup."),
    recipe=("Open ONI — the open-source rebuild of the Chronicling America "
        "software — so the grammar is the one treetools.newspapers already "
        "knows: "
        "/search/pages/results/?andtext=<terms>&format=json[&rows=N&page=N] "
        "-> {startIndex, endIndex, totalItems, items[]}, each item carrying "
        "id, title, lccn, date, county and edition. /newspapers.json "
        "enumerates every digitised title. TRAP: some parameter orderings "
        "return HTTP 500 — '?andtext=x&format=json&rows=3' failed where "
        "'?andtext=x&format=json' and "
        "'?andtext=x&rows=5&format=json&page=1' both worked. If you get a "
        "500, reorder before concluding anything. Honour the site's /*.txt$ "
        "disallow: take page text from the JSON, not by fetching ocr.txt."),
    default_record_type="newspapers",
    notes=("The one state programme of the fifteen that is open, keyless and "
        "machine-searchable. A control query for 'Hartley' returned 4,084 "
        "hits, so the index is live."),
))

register(Archive(
    key="hathitrust",
    name="HathiTrust Digital Library",
    base_url="https://babel.hathitrust.org",
    operator="HathiTrust, University of Michigan",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("Cloudflare interstitial — 'Just a moment...' with <meta "
        "name=\"robots\" content=\"noindex,nofollow\"> — returning HTTP 403 "
        "to every request including robots.txt itself, on BOTH "
        "babel.hathitrust.org and catalog.hathitrust.org. "
        "solr-sdr-search.hathitrust.org does not resolve."),
    disallow_line=("(HTTP 403 behind a Cloudflare challenge on every path, robots.txt "
        "included — same shape as illinois-idnc)"),
    recipe=("DO NOT REQUEST. Browser only. The 2026-08-28 prompt expected "
        "HathiTrust to have an open API; it does not have one this project "
        "can reach. Use the Internet Archive instead — it holds the same "
        "county-history and biographical-album genre and is open."),
    default_record_type="books",
))

register(Archive(
    key="ia-census-microfilm",
    name=("US census microfilm on the Internet Archive (NARA "
        "M432/M653/M593/T9/T623/T624/T625/T626)"),
    base_url="https://archive.org",
    operator=("Internet Archive; scanned by the Allen County Public Library "
        "Genealogy Center"),
    verdict=OPEN,
    verified_on="2026-08-29",
    robots=("archive.org/robots.txt disallows only /control/ and /report/, read "
        "again 2026-08-29. The download nodes serve no robots.txt at all. "
        "No ClaudeBot group anywhere."),
    recipe=("⭐⭐ THIS OVERTURNS THE 2026-08-28 FINDING THAT 'EXACTLY ONE OF TEN "
        "CENSUS YEARS IS MACHINE-REACHABLE'. That was true of NARA's own "
        "sites and of the auth-walled indexes; it was never checked against "
        "the Internet Archive, which holds the NARA microfilm itself. "
        "`treetools census --locate` drives everything below.   ⭐⭐⭐ THE "
        "THING THAT MAKES THIS TRACTABLE, FOUND 2026-08-29: **ONE ITEM'S "
        "METADATA CARRIES THE WHOLE STATE'S REEL-TO-COUNTY MAP.** The "
        "`description` field of any item is NARA's own reel list for that "
        "state and year — 'reel 1292. Coryell, Dallas, Dawson, Denton, De "
        "Witt Counties -- reel 1293. Eastland, Ellis, El Paso, ...' — so "
        "COUNTY -> REEL is a single metadata lookup and not a search. For "
        "1880, 1900, 1910 and 1920 the same clause also gives the "
        "ENUMERATION DISTRICT and SHEET at which a county splits across two "
        "reels, e.g. 'Jo Daviess (part: EDs 1-55, sheet 16)'. "
        "ENUMERATION:   search "
        "https://archive.org/advancedsearch.php?q=collection:(<year>_census)+AND+subject:(\"<State>\")&fl[]=identifier&fl[]=volume&fl[]=imagecount&rows=500&output=json "
        "⚠️ USE `subject:`, NOT `title:` — the 1920 and 1930 titles do not "
        "name the state ('14th census of population, 1920. [microform]') "
        "while `subject` always does.   metadata "
        "https://archive.org/metadata/<identifier>   REEL NUMBER -> "
        "IDENTIFIER: read the `volume` field ('Reel 1293'). ⚠️ DO NOT BUILD "
        "AN IDENTIFIER FROM THE REEL NUMBER. The prefix changes with the "
        "year and the collision is silent: reel 1608 is "
        "`populationschedu1608unit` in 1870 and `12thcensusofpopu1608unit` "
        "in 1900, and asking for the wrong one returns a real page from the "
        "wrong decade. Prefixes seen: 1850 `7thcensus####unit`, 1860 "
        "`populationschedu####unix`, 1870 `populationschedu####unit`, 1880 "
        "`10thcensus####unit`, 1900 `12thcensusofpopu####unit`, 1910 "
        "`13thcensus1910po###unit`, 1920 `14thcensusofpopu###unit`, 1930 "
        "`15thcensus####unit` and `michigancensus00reel###`.   ONE PAGE AT "
        "A TIME, which is the only sane way — the jp2.zip for a single reel "
        "is ~1.9 GB: https://archive.org/download/<identifier>/page/leaf<N> "
        "(~3 MB; 1860 sheets are portrait ~6900x9200, 1930 landscape "
        "~8100x5576; one microfilm frame = one census sheet side). "
        "/page/n<N>.jpg also works.   FINDING THE LEAF: leaves run in reel "
        "order, so fetch a leaf, read the printed header band (top ~10-12% "
        "of the page, full width) — it gives State, County, "
        "Township/Division, Enumeration District (1880 onward) and Sheet or "
        "Page No. — then binary-search the county boundary. Six to ten "
        "probes fixes a county on a 500-leaf reel. A CONTACT SHEET OF EIGHT "
        "BANDS IN ONE IMAGE is the cheap unit of search; the NAME COLUMN of "
        "one leaf, split into two halves side by side, is the cheap unit of "
        "scanning (about 40 names, legible at 820px a column). ⚠️ THE OCR "
        "IS WORTHLESS — these are handwritten ledgers. The item metadata "
        "says so itself: `ocr: language not currently OCRable`. There is an "
        "hOCR file; do not plan around it. READ THE IMAGE. ⚠️ PAGE NUMBERS "
        "ARE NOT LEAF ARITHMETIC. On 1860 Texas reel 1293 the page numbers "
        "restart per Division and the reel interleaves two sequences — leaf "
        "9 is page 64, leaf 12 is page 2. Do not interpolate a leaf from a "
        "page number; scan. ⚠️ MACOS sips CROPS FROM THE CENTRE and its "
        "--cropOffset is measured from the centre, which will silently hand "
        "you the black microfilm border and look like an empty page. Use "
        "PIL: im.crop((left, top, right, bottom))."),
    adapter="treetools.ia_census",
    default_record_type="census",
    notes=("Found 2026-08-28; enumerated and made usable 2026-08-29. ⭐⭐ THE "
        "RE-MEASUREMENT: `treetools census` reported **3 of 143** "
        "person-census-years with an open machine route. Against this "
        "archive and NARA's 1940 bucket the real number is **143 of 143** — "
        "3 `indexed` (1950, searchable by NAME) and 140 `browse` (free and "
        "keyless, but you must know the county and then read the pages). "
        "The old 3 was not a lie; it was measured against the INDEXES and "
        "never against the archives that hold the FILM. ⚠️ AND REACHABLE IS "
        "NOT CHEAP. There is no name index on any of this. A big county is "
        "several hundred sheets and the OCR cannot help, so a `browse` row "
        "costs a scan, not a query. Say which. NARA itself has NOT "
        "digitised the 1850-1930 schedules: the catalog file unit for "
        "Michigan/Calhoun 1930 is naId 236690692 with zero digitalObjects, "
        "there is no nara-1930-census bucket, and no "
        "1930census.archives.gov host. 1940 and 1950 are different and both "
        "have their own entries.   ⭐ GENERATION SIX PART D (2026-08-30) — "
        "two NO-ROUTE counties, confirmed live by `census --locate`, not "
        "assumed from a prompt: (1) VIRGINIA / CARROLL, 1870 does not "
        "resolve — 'Virginia 1870 has 72 items on the Internet Archive, and "
        "the reel-to-county list in their description does not name "
        "Carroll. Check the spelling against the reel map, and note that "
        "some counties did not exist yet in 1870.' Carroll County, VA was "
        "formed in 1842 and certainly existed by 1870, so this reads as a "
        "metadata gap in the archive's own reel-to-county description, not "
        "a genuine absence of the county from the 1870 census — but the "
        "correct reel was NOT tracked down this session. 1860 and 1880 "
        "Carroll County DO resolve on this same platform (reels 1339 and "
        "1360). (2) NEW YORK / HERKIMER, 1850 is NOT DIGITISED at all — a "
        "genuine absence, not a metadata gap: 'Herkimer County, New York "
        "1850 is on reel(s) 197, 198 according to the archive's own reel "
        "map, and none of those reels has been digitised into this "
        "collection.' Mehitable Alden (Marsh) Gould was born there in "
        "1797; no 1850 Herkimer route exists on this platform at all."),
))

register(Archive(
    key="illinois-idnc",
    name="Illinois Digital Newspaper Collections",
    base_url="https://idnc.library.illinois.edu",
    operator="University of Illinois",
    verdict=BLOCKED,
    verified_on="2026-08-25",
    robots="HTTP 403 to every automated request",
    disallow_line="(HTTP 403, not a robots rule)",
    recipe="DO NOT REQUEST. Browser only.",
    default_record_type="newspapers",
))

register(Archive(
    key="internet-archive",
    name="Internet Archive",
    base_url="https://archive.org",
    operator="Internet Archive",
    verdict=OPEN,
    verified_on="2026-08-28",
    robots=("User-agent: * with only Disallow: /control/ and Disallow: "
        "/report/. Search, metadata and item text are open."),
    recipe=("METADATA SEARCH: "
        "/advancedsearch.php?q=<lucene>&fl[]=identifier&fl[]=title&fl[]=year&rows=N&output=json "
        "-> response.numFound / response.docs. Lucene syntax, so "
        "mediatype:texts AND \"Owen County, Kentucky\" works. FULL TEXT of "
        "an item: /download/<identifier>/<identifier>_djvu.txt — the entire "
        "OCR of the book in one file, which is exactly what the 2026-08-27 "
        "Alma Rice lesson says to budget for. The Portal's phrase search "
        "proved unreliable and a page-by-page scan was what actually found "
        "the record; here the whole book comes down at once and grep does "
        "the scan. TRAP: the full-text SEARCH hosts are not reachable — "
        "ia-fts.archive.org and ia-pub-fts-api.archive.org both fail DNS "
        "(checked 2026-08-28). Find candidate items by metadata, then grep "
        "their text. TRAP: modern in-copyright books are lending-restricted "
        "and _djvu.txt returns HTTP 401. 'History of Owen County, Kentucky, "
        "\"Sweet Owen\"' (1976, historyofowencou0000houc) is one of them — "
        "a free IA account borrows it in a browser. ⭐ archive.org_bot is "
        "the ONE crawler the Veridian state newspaper sites allow through, "
        "so material blocked at Michigan, New York, Indiana and Virginia "
        "may be reachable here."),
    default_record_type="books",
    notes=("The class of source that produced the Alma Rice find on 2026-08-27 "
        "was a county history, and this is where county histories are. "
        "Open, keyless, and it takes whole books."),
))

register(Archive(
    key="k-state-digital",
    name="K-State Libraries Digital Collections",
    base_url="https://digital.lib.k-state.edu",
    operator="Kansas State University",
    verdict=BLOCKED,
    verified_on="2026-08-26",
    robots="disallowed",
    disallow_line="Disallow: /",
    recipe="DO NOT REQUEST.",
    default_record_type="mixed",
))

register(Archive(
    key="kansas-historical-society",
    name="Kansas Historical Society / Kansas Memory",
    base_url="https://kansashistory.gov",
    operator="Kansas Historical Society",
    verdict=NO_MACHINE_INTERFACE,
    verified_on="2026-08-26",
    robots=("kansashistory.gov: not blocked, but every machine-interface path "
        "404s. kansasmemory.gov: robots.txt DISALLOWS /search, /locate and "
        "/locate.php — re-checked 2026-08-26. So even scraping the search "
        "UI is off the table, not merely inconvenient."),
    disallow_line=("kansasmemory.gov — User-agent: * / Disallow: /search / Disallow: "
        "/locate / Disallow: /locate.php"),
    recipe=("Browse and search by hand only, and DO NOT REQUEST "
        "kansasmemory.gov/search. No OAI-PMH, no CONTENTdm web services, no "
        "IIIF, no JSON, no SPARQL — every candidate path returns a genuine "
        "404. Domains moved: kshs.org -> kansashistory.gov, "
        "kansasmemory.org -> kansasmemory.gov. The county catalog search "
        "does work in a browser, e.g. "
        "/dart/units/search/creator:example%20county/mattype:A/level:D."),
    default_record_type="mixed",
))

register(Archive(
    key="kansas-unt-gateway",
    name="A Kansas UNT-style gateway",
    base_url="(none)",
    operator="(none)",
    verdict=ABSENT,
    verified_on="2026-08-26",
    robots="n/a",
    default_record_type="newspapers",
    notes=("Does not exist. kansashistory.unt.edu, gateway.kshs.org and "
        "gateway.kansashistory.gov all fail DNS. Texas and Oklahoma both "
        "have one; Kansas does not. Do not go looking again."),
))

register(Archive(
    key="kentucky-digital-newspaper-program",
    name=("Kentucky newspaper and digital-library programmes (KDNP, KDL, "
        "ExploreUK)"),
    base_url="https://kdl.kyvl.org",
    operator="University of Kentucky Libraries / Kentucky Virtual Library",
    verdict=NO_MACHINE_INTERFACE,
    verified_on="2026-08-28",
    robots=("Three hosts, three different walls, none of them passable. "
        "kdl.kyvl.org is CONTENTdm and its robots.txt disallows "
        "/digital/search/ and every per-collection "
        "/digital/collection/<code>/search/ path — the search itself. "
        "exploreuk.uky.edu serves an ANUBIS proof-of-work interstitial "
        "titled 'Making sure you're not a bot!' to a plain request. "
        "kentuckynewspapers.org is an Ex Libris Primo discovery UI carrying "
        "<meta name=\"robots\" content=\"noindex\"> and no API. nyx.uky.edu "
        "refuses the connection outright."),
    disallow_line="kdl.kyvl.org — User-agent: * / Disallow: /digital/search/",
    recipe=("Browser only, by hand, and it is free to a human. DO NOT probe the "
        "CONTENTdm API to get round the disallowed search paths."),
    default_record_type="newspapers",
    notes=("HIGHEST PRIORITY of the fifteen, because Job and John Hartley are "
        "here. The honest answer is that Kentucky has no open machine route "
        "and its digitised newspapers do not cover the Hartley counties "
        "anyway. What DID work for Kentucky was the Internet Archive — see "
        "internet-archive — and NARA's open dataset, which is where W. 8839 "
        "came from."),
))

register(Archive(
    key="kshs-open-access-portal",
    name="KSHS Open Access Portal (Kansas newspapers)",
    base_url="https://kansashistoricalopencontent.newspapers.com",
    operator="Kansas Historical Society, hosted by Newspapers.com",
    verdict=BLOCKED,
    verified_on="2026-08-26",
    robots="User-agent: ClaudeBot / Disallow: /",
    disallow_line="User-agent: ClaudeBot Disallow: /",
    recipe=("DO NOT REQUEST. robots.txt was read and nothing beyond it. Free to "
        "a human in a browser; permanently closed to automation."),
    default_record_type="newspapers",
    notes=("THE single highest-value Kansas source, and it is a manual job. "
        "Daniel S. Marsh d. 8 Jan 1914 at Fredonia falls squarely inside "
        "the 1854-1923 window; his death notice may well be sitting there. "
        "He is the weakest join on the Marsh line at 10%."),
))

register(Archive(
    key="lva-virginia-libguides",
    name="Library of Virginia — Birth, Marriage, and Death Records guide",
    base_url="https://lva-virginia.libguides.com/bmd",
    operator="Library of Virginia",
    verdict=OPEN,
    verified_on="2026-08-30",
    robots=("www.lva.virginia.gov/robots.txt disallows /core/, /profiles/, "
        "/admin/, /search/ and a handful of Drupal utility paths — general "
        "content pages are open. The libguides.com subdomain is a separate "
        "host (Springshare) and was fetched directly; its own robots.txt "
        "was not separately checked, but the page rendered in full to a "
        "plain `curl` with no bot challenge."),
    recipe=("One page (`/bmd`), plain HTML, ~56KB, renders in full to a plain "
        "GET — no login, no JS render required. Answers a coverage question "
        "directly: what the state's birth/marriage/death record series are, "
        "what years they span, where they physically sit, and — critically "
        "— whether they are online. THIS PAGE IS NOT A SEARCH INTERFACE and "
        "holds no images or index."),
    default_record_type="vital",
    notes=("Added 2026-08-30, Generation Six Part D, for Nancy Elizabeth "
        "Newman (b. 1859, Carroll County, VA) — a register entry naming "
        "BOTH parents at the time of the event would be PRIMARY evidence "
        "and would move ahn 78/79 (Isaac Newman, Sarah M 'Sally' Spencer) "
        "from 10% toward 90% in one document. Coverage established; the "
        "record itself was not requested this session — that is a task for you, in a browser, "
        "either an ILL microfilm loan or a VDH application."),
))

register(Archive(
    key="michigan-gendis",
    name="GENDIS — Michigan Genealogical Death Indexing System",
    base_url="https://vitalstats.michigan.gov/osr/gendisx/",
    operator="Michigan Department of Health and Human Services",
    verdict=OPEN,
    verified_on="2026-08-28",
    robots=("User-Agent: * disallows /osr/css, /osr/CHI, /osr/jquery. "
        "/osr/gendisx/ is NOT disallowed. No ClaudeBot group."),
    recipe=("POST /osr/gendisx/scripts/search.asp, form-encoded: LastName, "
        "FirstName, FatherLastName, CountyName (exact county name, or %25 "
        "for all), YearRange, SortClause. Wildcards in LastName: '?' one "
        "character, '*' many. Returns an HTML table of Decedent's Name / "
        "Date of Death / Father's Last Name / County. ⭐ IT INDEXES FATHER'S "
        "LAST NAME, a search axis almost nothing else offers — the same "
        "inversion the Missouri database allowed."),
    default_record_type="vital",
    notes=("Searched 2026-08-28: LastName=Cunn*, CountyName=Calhoun, all years "
        "returned 8 Calhoun County Pell deaths, 1868-1889. Background "
        "texture only — NO connection to Marguerite is established, Pell "
        "is a common surname, and none of it may drift into the tree."),
))

register(Archive(
    key="michiganology",
    name=("Michiganology — Michigan death certificates 1897-1952 (Archives of "
        "Michigan)"),
    base_url="https://michigan.access.preservica.com",
    operator="Archives of Michigan / Library of Michigan",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("UNREADABLE. Every path on michigan.access.preservica.com, "
        "/robots.txt included, returns HTTP 403 with 'cf-mitigated: "
        "challenge' and a ~147 KB Cloudflare interstitial. The access "
        "policy cannot be read, so permission cannot be established. DO NOT "
        "REQUEST."),
    disallow_line=("HTTP 403 + cf-mitigated: challenge on every path including "
        "/robots.txt"),
    default_record_type="vital",
    notes=("⭐ THE HIGHEST-VALUE MANUAL TASK OF THIS SESSION, and it is five "
        "minutes in a browser. michiganology.org ITSELF is open (robots: "
        "'User-agent: * / Disallow:' — an empty Disallow) and its "
        "/vital-records/ page carries the Death Records advanced-search "
        "form inline. Its field list was read directly: Deceased First "
        "Name, Deceased Last Name, City, County, Death Range, Age, "
        "**Fathers First Name, Fathers Last Name, Mothers First Name, "
        "Mothers Last Name**. THE PARENT FIELDS ARE INDEXED, NOT MERELY "
        "IMAGED — the maiden name is searchable, not just readable. The "
        "search itself runs on the Preservica host, which is what is "
        "blocked. AND IT IS UNRESTRICTED: MDHHS form DCH-0569-DX (Rev. "
        "02/2025) says 'Death records are not restricted documents in "
        "Michigan. Anyone can request that a search be conducted' — no "
        "relationship, no ID. $34.00 from the state, or $20.00 from the "
        "Calhoun County Clerk, who holds 'Deaths: 1867 - Present'."),
))

register(Archive(
    key="missouri-death-certificates",
    name="Missouri Death Certificates, 1910-1975 (Missouri State Archives)",
    base_url="https://s1.sos.mo.gov/records/archives/archivesmvc/deathcertificates",
    operator="Missouri Secretary of State, Missouri State Archives",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("CHANGED VERDICT 2026-08-28, and this one hurts. On 2026-08-26 "
        "s1.sos.mo.gov served 'User-agent: * / Disallow:' — allow all — and "
        "this project read TWO death certificates through it in one "
        "session: Robert L. Hartley's (1974, Clay County) and Avice B. "
        "Henderson's (1940, Jackson County), the second of which surfaced "
        "only because every 1940 Henderson death in the county could be "
        "opened. TODAY BOTH s1.sos.mo.gov AND www.sos.mo.gov RETURN HTTP "
        "403 WITH A CLOUDFLARE INTERACTIVE CHALLENGE, to /robots.txt "
        "itself. The body is the 'Just a moment...' interstitial carrying "
        "'noindex,nofollow' and cType: 'interactive'. **The access policy "
        "cannot even be read**, so permission cannot be established and "
        "nothing may be requested. Fetched directly 2026-08-28. Same shape "
        "as HathiTrust and the Michigan Preservica host. DO NOT REQUEST — "
        "the recipe below is kept because it is correct and because it "
        "still works for a human."),
    disallow_line=("HTTP 403 + Cloudflare interactive challenge on every path "
        "including /robots.txt — the access policy is unreadable, so there "
        "is no permission to rely on"),
    recipe=("*** DO NOT REQUEST from 2026-08-28 — this is now a human job. The "
        "steps below are kept because they still work in a browser. *** "
        "Three steps, and the middle one is the trap. (1) GET the form page "
        "to get an ASP.NET session cookie. (2) POST the query to the SAME "
        "url; it 302s and stores the search in session. Do NOT follow the "
        "redirect it gives you — the capitalised path it returns 404s. (3) "
        "GET .../deathcertificates/results (lowercase) with the same cookie "
        "jar. Fields: "
        "DeathCertNameSearchType=Deceased|Spouse|Father|Mother, "
        "LastName/FirstName/MiddleName with "
        "LNSearchMethod/FNSearchMethod/MNSearchMethod=Contains|StartsWith|EndsWith|Exact, "
        "BeginMonth/BeginYear/EndMonth/EndYear, CountyName, Search=Search. "
        "TRAPS: an EndYear past 1975 silently returns the blank form "
        "instead of results or an error. Spouse/Father/Mother name search "
        "is only available for 1954-1975 (the site says so). AND THE INDEX "
        "IS A TRANSCRIPTION: 'Avice B. Henderson' is indexed as 'Alice'. "
        "Always open the PDF. Results carry a direct free PDF link per row."),
    default_record_type="vital",
    notes=("Produced the two best documents of 2026-08-26: Robert L. Hartley's "
        "3 Jan 1974 certificate (father Leroy Hartley, mother Mary Fenn, "
        "informant his son Everett Hartley) and Avice B. Henderson's 16 Oct "
        "1940 certificate (father T. R. Bram, mother Alma Rice, informant "
        "Robert Hartley). Under CLAUDE.md the PARENT fields on a death "
        "certificate are SECONDARY, so neither lifts a join past 75%."),
))

register(Archive(
    key="missouri-unt-gateway",
    name="A Missouri UNT-style newspaper gateway",
    base_url="(none)",
    operator="(none)",
    verdict=ABSENT,
    verified_on="2026-08-26",
    robots="n/a",
    default_record_type="newspapers",
    notes=("Does not exist in usable form. gateway.mohistory.org, "
        "missourihistory.unt.edu and gateway.mo.gov all fail DNS; "
        "gateway.shsmo.org resolves but the host does not answer (no TCP "
        "response, repeated). Texas and Oklahoma have one; Missouri does "
        "not. Missouri's usable open interface is the death-certificate "
        "database, not newspapers."),
))

register(Archive(
    key="nara-1940-census",
    name="1940 Census population schedules — NARA's public S3 bucket",
    base_url="https://nara-1940-census.s3.amazonaws.com",
    operator="NARA",
    verdict=OPEN,
    verified_on="2026-08-29",
    robots=("No robots.txt (HTTP 404) — this is NARA's own published open-data "
        "distribution, the same family of buckets as `nara-catalog`, which "
        "produced pension file W. 8839 on 2026-08-28. Anonymous LIST and "
        "GET both work."),
    recipe=("⭐⭐ FOUND 2026-08-29, AND IT IS BETTER INDEXED THAN THE FILM. The "
        "Internet Archive holds **ZERO** 1940 items — "
        "`collection:(1940_census)` returns numFound 0, measured, against "
        "2,669 for 1930 — and that null is what sent this search to NARA. "
        "THE POINT: THE KEYS ARE THE INDEX. There is no reel map and no "
        "leaf hunting, because the county AND the enumeration district are "
        "the path: "
        "population-schedules/<st>/<county>-county/ed/<ED>/m-t0627-<roll>-<frame>.jpg "
        "e.g. population-schedules/tx/Example-county/ed/5-1/ — Example "
        "County has EDs 5-1 through 5-11, eleven folders.   LIST: "
        "?list-type=2&delimiter=/&prefix=<prefix>  (XML; `<Prefix>` "
        "elements are the child folders, `<Key>` the images).   ⭐ AND THE "
        "ED DESCRIPTIONS ARE MACHINE-READABLE. `metadata/json/<st>.json` is "
        "one file per state carrying, for every county, every ED with a "
        "written boundary description naming the streets — 'JUSTICE "
        "PRECINCT 1, PALESTINE CITY WARD 1 BOUNDED BY (N) CITY LIMITS; (E) "
        "CITY LIMITS; (S) E LACY; (W) N SYCAMORE' — plus the schedule image "
        "keys and the ED map keys. Texas is 21 MB. That converts 'which ED "
        "was this street in' from a research question into a grep. "
        "Companion prefixes: ed-descriptions/, ed-maps/, zip/.   ⚠️ STILL "
        "NO NAME INDEX. This is `browse`, not `indexed`: it tells you which "
        "ED covers an address, and you then read the sheets."),
    adapter="treetools.ia_census",
    default_record_type="census",
    notes=("This entry exists because a null was taken seriously instead of "
        "being written down as a dead end. The Internet Archive's 1940 "
        "count is zero; the question 'then who does hold it' had a "
        "one-request answer, and the answer is better than the thing that "
        "was missing. It also closes the last hole in the census route "
        "table: with this and `nara-1950-census`, EVERY federal census year "
        "1850-1950 now has an open, keyless machine route."),
))

register(Archive(
    key="nara-1950-census",
    name="1950 Census (NARA) — name index, page images and IIIF",
    base_url="https://1950census.archives.gov",
    operator="NARA",
    verdict=OPEN,
    verified_on="2026-08-28",
    robots="User-agent: * / Crawl-delay: 1 — nothing disallowed.",
    recipe=("⭐ THE ONLY CENSUS YEAR WITH AN OPEN MACHINE ROUTE. SEARCH: GET "
        "/api/search/?name=<name>&state=<XX>[&county=<name>] -> {total, "
        "size, page, results[]}. Each result is a whole SHEET: scheduleId, "
        "state, county, ed, image, iiifUrl, and TWO name lists — `names[]`, "
        "the raw machine index, and `transcribe[]`, the human-corrected "
        "one. READ BOTH. On the Tarrant sheet the machine index reads 'hyle "
        "Weston O.' and only `transcribe` has 'Weston O Tarrant'; a name "
        "search against the machine field alone misses it. That is the "
        "FOURTH time this family has been hidden by a transcription, after "
        "'Haxtley', 'Alice' for Avice and Hazel under Cochran. IMAGE: the "
        "IIIF Image API 2.0. <iiifUrl> ends /info.json; strip that and "
        "append /full/full/0/default.jpg for the whole sheet (~4.5 MB, "
        "4076x4696) or /<x>,<y>,<w>,<h>/<width>,/0/default.jpg to crop — "
        "cropping is how you read one household's occupation columns "
        "without downloading and eyeballing the whole page. POST is not "
        "allowed on /api/1950census/search/ (405)."),
    default_record_type="census",
    notes=("Produced the first census record: "
        "a 1950 household entry giving a couple's ages and birth states, "
        "which corroborated both identities on four fields "
        "and moved no join, because Rosalind had left the household by 1950."),
))

register(Archive(
    key="nara-aad",
    name="NARA Access to Archival Databases (AAD)",
    base_url="https://aad.archives.gov",
    operator="NARA",
    verdict=BLOCKED,
    verified_on="2026-08-26",
    robots=("HTTP 403 to every automated request, robots.txt included. CHANGED "
        "VERDICT: on 2026-08-25 this was recorded as NO_MACHINE_INTERFACE — "
        "no API, but reachable. On 2026-08-26 both "
        "aad.archives.gov/robots.txt and the series-list page returned 403 "
        "to a plain GET. Treat as blocked and stop."),
    disallow_line="(HTTP 403 on every path, robots.txt included)",
    recipe=("DO NOT REQUEST. Browser only, by hand. Holds NUMIDENT and the SS-5 "
        "application files. File units are ALPHABETICAL BY THE SURNAME HELD "
        "AT THE TIME of the entry, so a woman who married sits in a "
        "different unit for each name — search by SSN across every "
        "candidate unit, because the number is constant and the surname is "
        "not."),
    default_record_type="federal",
    notes=("Produced Tarrant's and Hazel's SS-5 entries naming Everett R "
        "Hartley and ROSALIND T Tarrant — half the evidence behind the "
        "generation-3 join."),
))

register(Archive(
    key="nara-aws-open-data",
    name="National Archives Catalog dataset (AWS Registry of Open Data)",
    base_url="https://nara-national-archives-catalog.s3.us-east-2.amazonaws.com/",
    operator="NARA, in partnership with Amazon Web Services",
    verdict=OPEN,
    verified_on="2026-08-28",
    robots=("no robots.txt on the bucket (404 NoSuchKey) — nothing is "
        "disallowed. This is a DIFFERENT HOST from catalog.archives.gov and "
        "it is the channel NARA's own API terms page points at for bulk "
        "access."),
    recipe=("Anonymous HTTPS against a public S3 bucket; no key, no AWS "
        "credentials, no aws CLI needed. LIST: "
        "/?list-type=2&max-keys=1000&delimiter=/&prefix=<p> "
        "(&continuation-token=<tok> to page). Top level: descriptions/, "
        "authority-records/, backups/, zip/. "
        "descriptions/record-groups/rg_<N>/rg_<N>-<k>.jsonl — one JSON "
        "object per line, {\"record\": {...}} with naId, title, "
        "levelOfDescription, ancestors[] (recordGroup/series/fileUnit) and, "
        "for digitised items, digitalObjects[] carrying objectUrl AND "
        "extractedText — NARA's page-by-page transcription — plus "
        "otherExtractedText[] with FamilySearch-partner HTR contributions, "
        "which are consistently the better read of the two. SIZES, so "
        "nobody starts a download blind: RG 15 alone is 400 files and 22.3 "
        "GB; the zip/ exports are up to 187 GB and are not worth touching. "
        "Streaming `curl | grep` at 14 parallel connections swept all of RG "
        "15 for one surname in about 18 minutes. TRAPS: HTTP Range requests "
        "work and are the cheap way to sample a file's head, but records "
        "are NOT globally sorted by naId within a chunk — each chunk is "
        "grouped by series and each series' block is internally sorted, in "
        "several separate alphabetical batches. Binary-searching a chunk on "
        "surname therefore fails; grep the stream instead. Companion "
        "buckets, same pattern, both public and both us-east-2: "
        "nara-1950-census and nara-1940-census."),
    default_record_type="federal",
    notes=("⭐ FOUND 2026-08-28 and it is the session's best piece of "
        "infrastructure. It produced Revolutionary War pension file W. 8839 "
        "(Job Hartley, naId 54645300, M804 roll 1053) complete with all 30 "
        "pages of transcription — the first PRIMARY-backed join in this "
        "tree — without touching the blocked catalogue host. The series to "
        "know: naId 300022, 'Case Files of Pension and Bounty-Land Warrant "
        "Applications Based on Revolutionary War Service', inside RG 15. "
        "File-unit titles carry the pension file NUMBER, the pensioner's "
        "name and the state, so a surname grep finds a file by name even "
        "though M804 is filmed alphabetically."),
))

register(Archive(
    key="nara-catalog",
    name="National Archives Catalog (web + API), catalog.archives.gov",
    base_url="https://catalog.archives.gov/",
    operator="NARA",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("CHANGED VERDICT 2026-08-28. On 2026-08-25 this was recorded as "
        "KEY_REQUIRED with the note 'x-api-key, free' and nobody ever asked "
        "for the key. Fetching robots.txt first, as the standing rule "
        "requires, shows the whole host is disallowed to every user-agent. "
        "The file is 69 bytes, served from S3/CloudFront, last-modified "
        "2026-08-13 — a deliberately placed file, not an error page."),
    disallow_line="User-agent: * Disallow: /",
    recipe=("DO NOT REQUEST. This covers the documented API at "
        "/api/v2/records/search as well as the HTML catalogue and the "
        "catalogmedia image paths, because robots.txt is host-wide. USE THE "
        "OPEN BULK DATASET INSTEAD — see nara-aws-open-data — which NARA "
        "itself designates for this: 'To download all publicly available "
        "Catalog data, please access the National Archives Catalog dataset "
        "on the Amazon Web Services Registry of Open Data.' FOR THE RECORD, "
        "so the key question is closed rather than dropped again: the key "
        "IS free and self-service-by-email. NARA's API terms page "
        "(archives.gov/research/catalog/help/api, read 2026-08-28) says "
        "'Anyone may request an API key to access and use the API', the "
        "contact is Catalog_API@nara.gov, the default limit is '10,000 "
        "queries per month per API key', and two of its terms matter to "
        "this project regardless of robots: 'Users will not scrape data or "
        "attempt to download all data from the Catalog via the API' and "
        "'Please do not cache or store any content returned by the API' — "
        "that second one is flatly incompatible with keeping an evidence "
        "archive, which is a better reason to stay off the API than the "
        "robots line is. Getting the key is in your action items as a "
        "decision for him, not a task for the tooling."),
    default_record_type="federal",
    notes=("The images for pension file W. 8839 live behind this host "
        "(catalogmedia paths) and behind NARAprodstorage, whose S3 paths "
        "return HTTP 403 to anonymous requests — checked 2026-08-28 in four "
        "URL forms. So the page IMAGES are a browser job for you. The page "
        "TEXT is not: NARA's own extracted text for every page travels in "
        "the open bulk dataset."),
))

register(Archive(
    key="north-carolina-digitalnc",
    name="DigitalNC / North Carolina Newspapers",
    base_url="https://newspapers.digitalnc.org",
    operator="North Carolina Digital Heritage Center, UNC Chapel Hill",
    verdict=NO_MACHINE_INTERFACE,
    verified_on="2026-08-28",
    robots=("Unreadable — both newspapers.digitalnc.org and www.digitalnc.org "
        "reset the connection on every request including robots.txt, from "
        "two independent HTTP clients. NOT recorded as BLOCKED, because no "
        "rule was ever served and an unread robots.txt is not evidence of a "
        "policy. Re-check before concluding anything."),
    recipe=("Browser only for now. Chronicling America holds 128 North Carolina "
        "titles and IS open — but zero for Caswell County."),
    default_record_type="newspapers",
))

register(Archive(
    key="pennsylvania-panewsarchive",
    name="Pennsylvania Newspaper Archive",
    base_url="https://panewsarchive.psu.edu",
    operator="Penn State University Libraries",
    verdict=NO_MACHINE_INTERFACE,
    verified_on="2026-08-28",
    robots=("NO robots.txt at all — /robots.txt returns HTTP 404, so nothing is "
        "disallowed. The wall is not a robots wall: every application path "
        "(/search/pages/results/, /newspapers.json) resets the connection "
        "to a plain client, from two independent HTTP stacks, while the "
        "site answers a browser. Recorded as no usable machine interface "
        "rather than as a block, because there is no rule to respect and no "
        "evidence of an intentional bot policy."),
    recipe=("Open ONI software, so the Chronicling America grammar would apply "
        "— /search/pages/results/?andtext=<terms>&format=json — if the host "
        "answered. It does not. Browser only."),
    default_record_type="newspapers",
))

register(Archive(
    key="peru-datos-abiertos",
    name="Plataforma Nacional de Datos Abiertos del Perú",
    base_url="https://www.datosabiertos.gob.pe",
    operator="Presidencia del Consejo de Ministros (PCM), Peru",
    verdict=OPEN,
    verified_on="2026-08-26",
    robots="Drupal default; Crawl-delay: 10. /api/ is not disallowed.",
    recipe=("DKAN. /api/3/action/package_list returns all 4,662 dataset names "
        "as JSON; /api/3/action/package_show?id=<name> returns one. TRAP: "
        "/api/3/action/package_search?q=... 301-redirects into a rewrite "
        "that mangles the query into a path and 404s. Use package_list and "
        "filter client-side. Honour Crawl-delay: 10."),
    default_record_type="vital",
    notes=("Genuinely open and useless for genealogy. Recorded so nobody "
        "spends another session finding that out."),
))

register(Archive(
    key="portal-texas",
    name="The Portal to Texas History",
    base_url="https://texashistory.unt.edu",
    operator="University of North Texas Libraries",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("CHANGED VERDICT 2026-08-28, and it is the most expensive negative "
        "this project has recorded. robots.txt now carries a named group: "
        "'User-agent: ClaudeBot' / 'Disallow: /', alongside Bytespider, "
        "meta-externalagent, meta-webindexer and GoogleOther. The wildcard "
        "group still disallows only /stats/, /feedback/ and */zoom/ and "
        "declares 'Request-rate: 1/3' and 'Crawl-delay: 3' — so the site is "
        "not hostile to crawlers in general, it names this one. Fetched "
        "directly on 2026-08-28; nothing else on the host was requested "
        "after reading it. It was OPEN on 2026-08-25 and the policy changed "
        "between the two sessions."),
    disallow_line="User-agent: ClaudeBot Disallow: /",
    recipe=("Atom search: "
        "/search/feed/?q=<phrase>&t=fulltext[&fq=untl_collection:<CODE>]. "
        "Metadata: /ark:/67531/<ark>/metadata.untl.xml. Page OCR: "
        "/ark:/67531/<ark>/m1/<page>/ocr.txt. The archive's own API page "
        "states: 'You do not need to apply for a special key to use these "
        "APIs'. TRAPS: the HTML /search/ path sits behind an ALTCHA "
        "proof-of-work gate — use /search/feed/. Unquoted multi-word "
        "queries are tokenised and swamped by high-volume titles; quote "
        "every phrase. OCR errors are severe — 'Hartley' is rendered "
        "'Haxtley' on the 1940 Edith Bram notice, so search the other "
        "surname in the household too. AND, FOUND 2026-08-27: A QUOTED "
        "PHRASE IS NOT RELIABLY A PHRASE. q='Alma Rice' returned a book "
        "whose text contains Alma and Rice separately and the phrase "
        "nowhere at all. Verify every hit against the page OCR, exactly as "
        "loc.gov already requires. OAI-PMH, found 2026-08-27 and far better "
        "for enumeration than paging the Atom feed: /oai/?verb=ListSets, "
        "and "
        "/oai/?verb=ListRecords&metadataPrefix=oai_dc&set=collection:<CODE> "
        "(partner:<CODE> also works), ~900 records a page with a "
        "resumptionToken. dc:date carries the ISSUE date, so a complete "
        "per-year coverage table costs one harvest instead of a session. "
        "Collection codes are listed at /explore/collections/. *** DO NOT "
        "REQUEST — ALL OF THE ABOVE IS NOW FOR A HUMAN IN A BROWSER ONLY. "
        "The recipe is kept because it is correct and because you can still "
        "use every line of it; no program in this repo may. ***"),
    adapter="treetools.portal — GUARDED. Every network call now raises portal.BlockedArchive before opening a socket.",
    default_record_type="newspapers",
    notes=("⚠️ AGENT-SPECIFIC, and the distinction matters. The group named is "
        "**ClaudeBot — Anthropic's TRAINING crawler**. **Claude-User, the "
        "user-initiated agent, is NOT named**, and the wildcard group still "
        "allows everything except /stats/, /feedback/ and */zoom/ at "
        "Crawl-delay: 3. So a person in a browser, and a research fetcher "
        "run under its operator's own identity honouring the wildcard "
        "group, are addressed by a different rule from the one that blocks "
        "this package. 34 OF MANY OF ONE PROJECT'S ARCHIVED DOCUMENTS CAME "
        "FROM HERE — the 1940 Edith Bram death notice, the 1950 'keystone' "
        "naming Everett's grandparents, Mary Ann Fenn' 1959 obituary, Ben "
        "Fenn' 1908 death notice, the Sample County pioneer index, the 1889 "
        "Biographical Souvenir page that settled Alma Rice. NOTHING ALREADY "
        "ARCHIVED IS LOST: every stored document keeps its full text, its "
        "SHA-256 and a permanent ARK, and those ARKs still resolve FOR A "
        "HUMAN IN A BROWSER. The block is on automation. WHAT IS LOST is "
        "the ability to run new searches — which in this session cost the "
        "two highest-value ones available: probate and administration "
        "NOTICES for the estate of B. W. Fenn in The Graham Leader "
        "1908-1910 (52 issues in 1908 alone), and for Mary Ann Fenn in the "
        "Example County News 1959-1960. Both are now yours, in a browser, "
        "and both are in your action items. The COVERAGE rows below are "
        "kept in full and stay true — they are what makes a human search "
        "classifiable as an absence or a gap. Kept from the 2026-08-25 "
        "entry: it produced eight score changes, and ARKs are permanent, so "
        "free_source URLs in the evidence manifest stay resolvable."),
))

register(Archive(
    key="reniec",
    name="RENIEC — Registro Nacional de Identificación y Estado Civil",
    base_url="https://www.reniec.gob.pe",
    operator="RENIEC, Peru",
    verdict=NO_MACHINE_INTERFACE,
    verified_on="2026-08-26",
    robots="no robots.txt (404)",
    recipe=("No public name-level search. RENIEC's open-data contribution is "
        "aggregate only — see peru-datos-abiertos. Copies of actas are an "
        "over-the-counter or authenticated service."),
    default_record_type="vital",
))

register(Archive(
    key="south-carolina-historic-newspapers",
    name="Historic Newspapers of South Carolina",
    base_url="https://historicnewspapers.sc.edu",
    operator="University of South Carolina Libraries",
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("Disallow: /search/ (plus /data/, /images/tiles/, *.pdf, *.txt, "
        "*.xml), Crawl-delay: 10. Same Open ONI software as Georgia, "
        "opposite policy on the one path that matters. SEPARATELY, "
        "scmemory.org — South Carolina Digital Library — names ClaudeBot in "
        "a 93-user-agent group followed by 'Disallow: /'."),
    disallow_line=("historicnewspapers.sc.edu — User-agent: * / Disallow: /search/ "
        "scmemory.org — User-agent: ClaudeBot (in a group of 93) / "
        "Disallow: /"),
    recipe=("DO NOT REQUEST the search. Browsing a known issue is permitted but "
        "there is no way to find one without the search. Browser only, by "
        "hand. 136 South Carolina titles are in Chronicling America, which "
        "IS open — go there instead."),
    default_record_type="newspapers",
))

register(Archive(
    key="state-programs-thin-or-absent",
    name=("State programmes with nothing usable: Illinois, Iowa, New "
        "Hampshire, Maryland"),
    base_url="(various)",
    operator="various",
    verdict=NO_MACHINE_INTERFACE,
    verified_on="2026-08-28",
    robots=("Four states, four different dead ends, all checked 2026-08-28. "
        "ILLINOIS: idnc.library.illinois.edu sits behind a Cloudflare "
        "interstitial and returns 403 to robots.txt and to the home page — "
        "confirming the 2026-08-25 verdict from a second direction; "
        "www.illinoisdigitalarchives.net fails DNS. IOWA: idnc.uiowa.edu "
        "fails DNS; digital.lib.uiowa.edu returns a bare nginx 403; "
        "iowaculture.gov presents an EXPIRED TLS certificate, so it cannot "
        "be fetched safely at all. NEW HAMPSHIRE: www.nh.gov returns an "
        "Akamai 'Access Denied' on robots.txt; newspapers.nh.gov does not "
        "resolve. There appears to be no state digital newspaper programme. "
        "MARYLAND: msa.maryland.gov has no robots.txt (IIS 404) and no "
        "machine interface; www.digitalmaryland.org allows everything "
        "('User-agent: * / Disallow:') but is a Yoast/WordPress portal, not "
        "a searchable newspaper or vital-record index."),
    recipe=("Chronicling America is the open route for all four and it is "
        "already in this registry. Its county numbers for this family, "
        "enumerated 2026-08-28, are in that entry's holdings."),
    default_record_type="newspapers",
    notes=("Recorded as one entry rather than four because the finding is the "
        "same in each case — no open state-level interface — and four "
        "near-identical rows would read like four separate investigations."),
))

register(Archive(
    key="texas-digital-archive",
    name="Texas Digital Archive (TDA) — county records, Preservica",
    base_url="https://tsl.access.preservica.com",
    operator="Texas State Library and Archives Commission",
    verdict=OPEN,
    verified_on="2026-08-28",
    robots=("User-agent: * / Disallow: /wp-admin/ / Allow: "
        "/wp-admin/admin-ajax.php. Nothing else disallowed. No ClaudeBot or "
        "anthropic-ai group."),
    recipe=("⭐ THE ANSWER TO 'WHERE IS PROBATE', found 2026-08-28. Free, "
        "keyless, no login, no cookie — TSLAC's own page says so: 'There is "
        "no subscription or login needed to access digitized records "
        "through the TDA.' BROWSE BY COUNTY: "
        "/?s=&hh_cmis_filter=dcterms.dcterms_hierarchy_freetext%2F<County>+County+records "
        "returns the whole series tree — Deed records, Probate minutes, "
        "Probate Case papers, Will records, Naturalization, District Court. "
        "Each series node is /uncategorized/SO_<uuid>/, each volume "
        "/uncategorized/IO_<uuid>/, whose page carries "
        "/download/file/IO_<uuid> — the whole volume as one PDF. ⚠️ THE "
        "VOLUMES ARE ENORMOUS: Example probate Vol. 2 is 304 MB / 272 "
        "pages, Young probate Vol. 6 is 433 MB. Budget the download. ⚠️⚠️ "
        "THE TRAP, FOUND THE HARD WAY: **whether a volume carries a TEXT "
        "LAYER varies by series.** Example and Young PROBATE MINUTES have "
        "full OCR — 22,828 characters on one sampled page — and grep works. "
        "Example DEED RECORD Vol. 31 has NONE: zero non-space characters on "
        "pages 1, 50, 200 and 480 of 487. Deeds are digitised and "
        "UNSEARCHABLE, and the deed index is not on the TDA at all. Test "
        "the text layer with pdftotext on one page before planning a grep. "
        "⚠️ Ledger volumes are two-column and pdftotext -layout interleaves "
        "them: 'Mrs. Mary Hartley' came out as 'Mrs. Mery Hartley' and as "
        "'my ieughte'. Render the page with pdftoppm and READ THE IMAGE. ⚠️ "
        "ACCESS IS NOT UNIFORM. This host served two multi-hundred-MB "
        "downloads to curl's default user-agent on 2026-08-28, while a "
        "second client the same day got a Cloudflare bot challenge on the "
        "same URLs. A challenge is a stop, not something to retry around."),
    default_record_type="probate",
    notes=("TSLAC's microfilm guide at tsl.texas.gov/arc/local/ is separately "
        "OPEN (robots disallows only /core/, /profiles/, /admin/, /search/, "
        "/user/login) and is the finding aid for what was filmed at all, "
        "reel by reel. Read it first, then look for the volume on the TDA; "
        "the two do not match, and the guide is the honest denominator. "
        "TSLAC also states plainly that neither it nor a depository may "
        "certify a copy: 'If a certified copy is needed, the researcher "
        "should obtain it from the county clerk or district clerk who is "
        "the custodian of the original record.'"),
))

register(Archive(
    key="veridian-state-newspaper-programs",
    name="Veridian-hosted state newspaper programmes (MI, NY, IN, and VA)",
    base_url="https://digmichnews.cmich.edu",
    operator=("Central Michigan University; NY Historic Newspapers; Indiana State "
        "Library (Hoosier State Chronicles); Library of Virginia"),
    verdict=BLOCKED,
    verified_on="2026-08-28",
    robots=("One vendor, one policy, four states. Every Veridian instance ships "
        "the identical file, comment and all: '# Block all web crawlers "
        "from accessing the site' / 'User-agent: * / Disallow: /', with "
        "Applebot and Google-Extended named separately and archive.org_bot "
        "the only crawler allowed through. Confirmed 2026-08-28 on "
        "digmichnews.cmich.edu, nyshistoricnewspapers.org and "
        "newspapers.library.in.gov; virginiachronicle.com was already "
        "recorded blocked on 2026-08-25 and has its own entry."),
    disallow_line="User-agent: * Disallow: /",
    recipe=("DO NOT REQUEST any of them. All are FREE TO A HUMAN in a browser; "
        "the block is on automation. Hosts: digmichnews.cmich.edu "
        "(Michigan), nyshistoricnewspapers.org (New York), "
        "newspapers.library.in.gov (Indiana), virginiachronicle.com "
        "(Virginia). ⭐ NOTE the one crawler they DO allow is "
        "archive.org_bot — so material from these sites may be reachable "
        "through the Internet Archive, which is open. Try there before "
        "giving up."),
    default_record_type="newspapers",
))

register(Archive(
    key="virginia-chronicle",
    name="Virginia Chronicle",
    base_url="https://virginiachronicle.com",
    operator="Library of Virginia",
    verdict=BLOCKED,
    verified_on="2026-08-25",
    robots="User-agent: * / Disallow: /  (and HTTP 403 behind Cloudflare)",
    disallow_line="User-agent: * Disallow: /",
    recipe="DO NOT REQUEST. Browser only, by hand.",
    default_record_type="newspapers",
))

register(Archive(
    key="willard-calhoun-probate",
    name="Calhoun County Probate Court General Index (Willard Library)",
    base_url="https://archives.willardlibrary.org/probate/",
    operator="Willard Library, Battle Creek, Michigan",
    verdict=OPEN,
    verified_on="2026-08-28",
    robots=("robots.txt returns HTTP 200 but contains ONLY Cloudflare "
        "content-signal COMMENT lines — not one User-agent or Disallow "
        "directive in the whole 24-line file, and no content-signal value "
        "is actually declared. Verified by stripping comments and blank "
        "lines: zero directives remain."),
    recipe=("Keyless, no JS, and it indexes a PRIMARY court record. Volumes: "
        "/probate/index-no_header.php — each entry carries data-path and "
        "data-file. Open one with "
        "?path=CALHOUN_PROBATE/<RANGE>&file=CALHOUN_PROBATE_<RANGE>&title=<RANGE>; "
        "the inline JS gives 'max_page'. Per page: "
        "/probate/present_file.php?path=<path>&file=<file>&page=<n>&type=jpg|pdf|txt|xml. "
        "⚠️ TYPE=TXT IS USELESS — the OCR of these ledger pages is "
        "scrambled past reading ('GEMEBAL INDEX - PROBATE'). Fetch type=jpg "
        "(~3 MB, about 4000x4000) and read the image. Volumes are surname "
        "RANGES: Marsh is in TEE-TOL, PELL in COO-CUR. Within a "
        "volume the scan pages walk the physical book and each opening is "
        "one surname section running chronologically — page 4 of TEE-TOL "
        "covers filing years 1923-1934, page 5 covers 1934-1949."),
    default_record_type="probate",
    notes=("Found 2026-08-28 while looking for Marguerite (Marsh) Pell, "
        "and reached only because the search was run under Marsh as well "
        "as PELL. Willard Library's "
        "NEWSPAPER archive on the same host is a different matter: "
        "'Chronicling Battle Creek' covers 1846-2026 across ~40 titles, so "
        "a Battle Creek newspaper null is an ACCESS WALL and NOT a coverage "
        "gap — but remote cardholder access stops at pre-1928 and 1931 is "
        "on-site only."),
))

register(Archive(
    key="wsu-soar",
    name="SOAR — Shocker Open Access Repository, Wichita State University",
    base_url="https://soar.wichita.edu",
    operator="Wichita State University Libraries",
    verdict=OPEN,
    verified_on="2026-08-26",
    robots="not disallowed",
    recipe=("DSpace with a working OAI-PMH endpoint: /oai/request?verb=Identify "
        "| ListSets | ListRecords&metadataPrefix=oai_dc."),
    default_record_type="mixed",
))




# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------


@dataclass
class PlaceAnswer:
    """The answer to 'what can I search for this place and year?'

    Deliberately not a list. An empty list reads like 'nothing found', and
    this project's defining failure mode is exactly that confusion.

    `nationwide` is kept separate from the place-specific buckets on
    purpose. NARA's catalogue technically "covers" Ellis County, Texas in
    1860 the way it covers everywhere; folding it in would let a
    place-specific query answer SEARCHABLE when nothing local exists.
    """

    place: Place
    year: Optional[int]
    record_type: str = ""
    searchable: List[Tuple[Archive, Holding, str]] = field(default_factory=list)
    no_coverage: List[Tuple[Archive, str]] = field(default_factory=list)
    manual: List[Archive] = field(default_factory=list)
    blocked: List[Archive] = field(default_factory=list)
    nationwide: List[Archive] = field(default_factory=list)
    #: Archives a HUMAN can search that really do hold this place and year,
    #: with the coverage sentence. Added 2026-08-28, when the Portal to Texas
    #: History started blocking this agent by name and took the project's
    #: most productive route with it.
    #:
    #: Coverage and access are orthogonal questions and this class used to
    #: conflate them: a BLOCKED archive was filed under `blocked` before its
    #: holding was ever consulted, so the moment the Portal's verdict changed,
    #: every coverage fact it carried vanished from the answer. That is
    #: precisely backwards. "this county holds zero issues for 1924" is true
    #: whoever runs the search, and it is MOST needed exactly when the search
    #: has become a human job — otherwise you read a null by hand and have no
    #: way to tell an absence from a gap.
    manual_coverage: List[Tuple[Archive, Holding, str]] = field(
        default_factory=list)

    @property
    def unknown(self) -> bool:
        """No archive in the registry addresses this place at all.

        This is a THIRD outcome, distinct both from 'searchable' and from
        'checked and holds nothing'. It means: nobody has looked yet.
        Nationwide archives do not count — they are not evidence that this
        place has been evaluated.
        """
        return not (self.searchable or self.no_coverage or self.manual
                    or self.blocked or self.manual_coverage)

    @property
    def verdict(self) -> str:
        if self.searchable:
            return "SEARCHABLE"
        if self.unknown:
            return "UNKNOWN — no archive in the registry covers this place"
        if self.no_coverage and not (self.manual or self.manual_coverage):
            return "NO COVERAGE — do not log a null here as an absence"
        return "MANUAL ONLY"


def for_place(place: str, year: Optional[int] = None,
              registry: Optional[Dict[str, Archive]] = None,
              record_type: Optional[str] = None) -> PlaceAnswer:
    reg = REGISTRY if registry is None else registry
    p = parse_place(place)
    ans = PlaceAnswer(place=p, year=year, record_type=record_type or "")
    for a in sorted(reg.values(), key=lambda x: x.key):
        if a.verdict == ABSENT:
            continue
        h = a.holding_for(p, record_type)
        # An archive with no holdings, or whose matching holding names no
        # region, is nationwide. It says nothing about whether this
        # particular county has been evaluated, so it is reported apart.
        if h is None or not h.region:
            if h is None and a.holdings:
                continue          # holds places, none of them this one
            if record_type is not None:
                # A nationwide archive with no declared record type says
                # nothing about whether it holds THIS class of record, and
                # reporting it would read as reassurance.
                continue
            ans.nationwide.append(a)
            continue
        ok, reason = h.holds(year)
        # Coverage first, access second. A place/year the archive does not
        # hold is a coverage gap for EVERYONE, including a human, and saying
        # so is more useful than saying "blocked".
        if not ok:
            ans.no_coverage.append((a, reason))
            if a.verdict == BLOCKED:
                ans.blocked.append(a)
        elif a.verdict == BLOCKED:
            ans.blocked.append(a)
            if h.informative:
                ans.manual_coverage.append((a, h, reason))
        elif a.verdict in AUTOMATABLE:
            ans.searchable.append((a, h, reason))
        else:
            ans.manual.append(a)
            if h.informative:
                ans.manual_coverage.append((a, h, reason))
    return ans


def for_person(xref: str, gedcom, pedigree=None,
               registry: Optional[Dict[str, Archive]] = None
               ) -> List[Tuple[str, Optional[int], PlaceAnswer]]:
    """Every (place, year) on a person's record, answered.

    The lineal tenet applies to what you *do* with this, not to the lookup:
    if `pedigree` is supplied and the person is not a direct ancestor, the
    caller is told so rather than silently served.
    """
    ind = gedcom.individuals.get(xref)
    if ind is None:
        raise RegistryError(f"{xref} is not in this GEDCOM")
    out = []
    seen = set()
    for ev in ind.events:
        if not ev.place:
            continue
        key = (ev.place, ev.date.year)
        if key in seen:
            continue
        seen.add(key)
        out.append((ev.place, ev.date.year,
                    for_place(ev.place, ev.date.year, registry)))
    return out


def validate_registry(registry: Optional[Dict[str, Archive]] = None
                      ) -> List[str]:
    reg = REGISTRY if registry is None else registry
    problems = []
    for a in reg.values():
        problems.extend(a.validate())
    return problems


def by_verdict(registry: Optional[Dict[str, Archive]] = None
               ) -> Dict[str, List[Archive]]:
    reg = REGISTRY if registry is None else registry
    out: Dict[str, List[Archive]] = {v: [] for v in VERDICTS}
    for a in sorted(reg.values(), key=lambda x: x.key):
        out[a.verdict].append(a)
    return out


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------


def format_list(registry: Optional[Dict[str, Archive]] = None,
                verbose: bool = False) -> str:
    reg = REGISTRY if registry is None else registry
    L = [f"{len(reg)} archive(s) with a recorded verdict", ""]
    for verdict, group in by_verdict(reg).items():
        if not group:
            continue
        L.append(f"--- {verdict} ({len(group)}) ---")
        for a in group:
            L.append(f"  {a.key:<28} {a.name}")
            L.append(f"  {'':28} {a.base_url}   verified {a.verified_on}")
            if a.adapter:
                L.append(f"  {'':28} adapter: {a.adapter}")
            if a.verdict == BLOCKED:
                first = a.disallow_line.replace("\n", " / ")
                L.append(f"  {'':28} DO NOT REQUEST — {first}")
            if verbose and a.recipe:
                L.append(f"  {'':28} {' '.join(a.recipe.split())}")
            if verbose and a.notes:
                L.append(f"  {'':28} note: {' '.join(a.notes.split())}")
        L.append("")
    return "\n".join(L)


def format_place_answer(ans: PlaceAnswer) -> str:
    where = str(ans.place) or "(unparsed place)"
    L = [f"{where}" + (f", {ans.year}" if ans.year else "")
         + (f"  [record type: {ans.record_type}]" if ans.record_type else ""),
         f"verdict: {ans.verdict}", ""]
    if ans.unknown:
        if ans.record_type:
            L.append(f"  No archive in the registry declares a "
                     f"{ans.record_type} holding for this place.")
        else:
            L.append("  No archive in the registry addresses this place.")
        L.append("  This is NOT 'nothing exists' — it is 'nobody has looked'.")
        L.append("  Evaluate one and register the verdict, negative or not.")
        return "\n".join(L)
    if ans.searchable:
        L.append(f"SEARCHABLE NOW ({len(ans.searchable)}):")
        for a, _h, reason in ans.searchable:
            L.append(f"  {a.key} [{a.type_of(_h) or 'class not stated'}]"
                     f" — {a.name}")
            L.append(f"      {reason}")
            if a.adapter:
                L.append(f"      adapter: {a.adapter}")
        L.append("")
    if ans.no_coverage:
        L.append(f"CHECKED, HOLDS NOTHING FOR THIS PLACE/YEAR "
                 f"({len(ans.no_coverage)}):")
        for a, reason in ans.no_coverage:
            L.append(f"  {a.key} — {reason}")
        L.append("  *** These are COVERAGE GAPS. A null from a search you "
                 "cannot run is not an absence. ***")
        L.append("")
    if ans.manual:
        L.append(f"A HUMAN CAN, YOU CANNOT ({len(ans.manual)}):")
        for a in ans.manual:
            L.append(f"  {a.key} [{a.verdict}] — {a.name}  {a.base_url}")
        L.append("")
    if ans.manual_coverage:
        L.append(f"A HUMAN CAN SEARCH THIS, AND IT REALLY HOLDS THE YEAR "
                 f"({len(ans.manual_coverage)}):")
        for a, _h, reason in ans.manual_coverage:
            L.append(f"  {a.key} [{a.verdict}] "
                     f"[{a.type_of(_h) or 'class not stated'}] — {a.name}")
            L.append(f"      {reason}")
        L.append("  *** Carry this sentence into your action items with the "
                 "search. A hand-run null is only worth logging if he knows "
                 "whether the collection covers the year. ***")
        L.append("")
    if ans.blocked:
        L.append(f"BLOCKED — DO NOT REQUEST ({len(ans.blocked)}):")
        for a in ans.blocked:
            L.append(f"  {a.key} — {a.name}")
            L.append(f"      {a.disallow_line.replace(chr(10), ' / ')}")
        L.append("")
    if ans.nationwide:
        L.append(f"NATIONWIDE — not place-specific ({len(ans.nationwide)}):")
        for a in ans.nationwide:
            L.append(f"  {a.key} [{a.verdict}] — {a.name}")
        L.append("  These cover everywhere, so they are NOT evidence that "
                 "this county has been evaluated.")
    return "\n".join(L).rstrip()
