"""The archive registry.

The tests that matter here are the ones about *negatives*. A registry that
only proves the open archives are listed would let the expensive knowledge —
the KSHS block, the Illinois 403, the missing Kansas gateway — rot out
silently, which is the exact failure this module exists to prevent.
"""

import pytest

from treetools import archives as A


# --------------------------------------------------------------------------
# Every entry is well-formed
# --------------------------------------------------------------------------


def test_registry_validates_clean():
    assert A.validate_registry() == []


def test_every_entry_has_a_verdict_and_a_date():
    for key, a in A.REGISTRY.items():
        assert a.verdict in A.VERDICTS, key
        assert a.verified_on, key
        # A verdict with no date is a rumour; the format is checked in
        # validate() and asserted here so a hand-edit cannot slip past.
        assert len(a.verified_on) == 10 and a.verified_on[4] == "-", key


def test_blocked_entries_carry_the_disallow_line():
    blocked = A.by_verdict()[A.BLOCKED]
    assert blocked, "the blocked sources are the point; do not empty this"
    for a in blocked:
        assert a.disallow_line or a.robots, (
            f"{a.key} is BLOCKED with no evidence — somebody will try again")
        assert "DO NOT REQUEST" in a.recipe.upper() or not a.recipe


def test_the_four_confirmed_blocks_are_present_and_stay_blocked():
    """These four cost real time to establish. Re-attempting one is a HARD
    FAIL in every session prompt this project has written."""
    for key in ("kshs-open-access-portal", "advantage-archives-corporate",
                "k-state-digital", "illinois-idnc"):
        assert A.REGISTRY[key].verdict == A.BLOCKED, key


def test_open_entries_carry_an_access_recipe():
    for a in A.by_verdict()[A.OPEN]:
        assert a.recipe, (
            f"{a.key} is OPEN but nobody knows how to call it, which is not "
            f"open in practice")


def test_duplicate_key_is_refused():
    existing = A.REGISTRY["portal-texas"]
    with pytest.raises(A.RegistryError):
        A.register(existing)


def test_bad_verdict_is_refused():
    with pytest.raises(A.RegistryError):
        A.register(A.Archive(key="nope", name="n", base_url="u",
                             operator="o", verdict="MAYBE",
                             verified_on="2026-08-26"))


def test_blocked_without_evidence_is_refused():
    with pytest.raises(A.RegistryError):
        A.register(A.Archive(key="nope2", name="n", base_url="u",
                             operator="o", verdict=A.BLOCKED,
                             verified_on="2026-08-26"))


def test_missing_verified_on_is_refused():
    with pytest.raises(A.RegistryError):
        A.register(A.Archive(key="nope3", name="n", base_url="u",
                             operator="o", verdict=A.OPEN,
                             recipe="GET /", verified_on=""))


# --------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text,region,county,city", [
    ("Ellis County, Texas", "texas", "ellis", ""),
    ("Denton County, Texas", "texas", "denton", ""),
    ("Fairview, Logan County, Kansas", "kansas", "logan", "fairview"),
    ("Fairview, Logan, Kansas", "kansas", "logan", "fairview"),
    ("Lima, Peru", "peru", "", "lima"),
    ("Kansas", "kansas", "", ""),
    ("Jo Daviess County, Illinois", "illinois", "jo daviess", ""),
    # Real GEDCOM place strings end with the country, in three spellings.
    ("Fairview, Logan County, Kansas, USA", "kansas", "logan",
     "fairview"),
    ("Denton, Denton, Texas, USA", "texas", "denton", "denton"),
    ("Elmdale, Benton, Texas, United States of America", "texas",
     "benton", "elmdale"),
])
def test_parse_place(text, region, county, city):
    p = A.parse_place(text)
    assert (p.region, p.county, p.city) == (region, county, city)


def test_parse_place_accepts_abbreviations():
    assert A.parse_place("Benton County, TX").region == "texas"


def test_parse_place_knows_all_fifty_states_and_dc():
    """The table held fifteen abbreviations, picked by whichever states this
    project had happened to touch. Harmless until something downstream asks
    'is this a real US state?' -- which census.place_for_year began asking on
    2026-08-31, and which decides whether a work-list row prints a place at
    all. Completed the same day."""
    assert len(A.STATE_NAMES) == 51
    for ab in ("de", "md", "nh", "ny", "sc", "wv", "dc", "or", "ut"):
        assert A.parse_place(f"Somewhere County, {ab.upper()}").region \
            == A.STATE_NAMES[ab]


def test_parse_place_strips_a_country_stuck_to_the_state_without_a_comma():
    """'Washington,Ky USA' is a real value seen in the wild, and it tends
    to sit on both parents of a couple at once -- so it breaks a whole
    generation, not one person. The comma split leaves 'Ky USA' as the
    region, which matches no state, so everything downstream treated a
    perfectly well-known Kentucky place as unrecognisable."""
    assert A.parse_place("Washington,Ky USA").region == "kentucky"
    assert A.parse_place("Dallas, Texas USA").region == "texas"
    assert A.parse_place("Somewhere, Illinois United States").region \
        == "illinois"


def test_parse_place_does_not_leave_punctuation_in_a_county():
    """'Carroll Co., VA.' used to parse to a county named 'carroll .', which
    matches nothing in VERIFIED_WINDOWS or the reel map."""
    p = A.parse_place("Carroll Co., VA.")
    assert (p.region, p.county) == ("virginia", "carroll")


# --------------------------------------------------------------------------
# The distinction the whole module exists for
# --------------------------------------------------------------------------


def test_a_place_nobody_evaluated_is_unknown_not_no_coverage():
    """Third outcome, and it is the one that generates work.

    The example moved on 2026-08-28. Schuylkill County, Pennsylvania used to
    stand here and no longer can: that session evaluated all fifteen
    unevaluated states, so Schuylkill now answers NO COVERAGE (one digitised
    title, 1891 only) instead of UNKNOWN. That is the registry working. The
    example is now a county in a state this project has never touched.
    """
    ans = A.for_place("Windsor County, Vermont", 1900)
    assert ans.unknown
    assert "UNKNOWN" in ans.verdict
    assert "nobody has looked" in A.format_place_answer(ans)


def test_nationwide_archives_do_not_make_a_county_look_evaluated():
    """NARA covers everywhere. If that counted as coverage, every county in
    the country would answer SEARCHABLE and the registry would be useless."""
    ans = A.for_place("Windsor County, Vermont", 1900)
    assert ans.unknown
    assert ans.nationwide, "they should still be listed, just apart"
    assert "nara-catalog" in [a.key for a in ans.nationwide]


def test_holding_zero_titles_is_a_gap_at_any_year():
    h = A.Holding("kansas", "greenwood", None, None, 0, "")
    for year in (1900, 1950, 2020):
        ok, why = h.holds(year)
        assert not ok
        assert "COVERAGE GAP" in why


# --------------------------------------------------------------------------
# Person lookup
# --------------------------------------------------------------------------


def test_for_person_rejects_an_unknown_xref(toy):
    with pytest.raises(A.RegistryError):
        A.for_person("@NOPE@", toy)


def test_for_person_dedupes_repeated_place_year_pairs(toy):
    rows = A.for_person("@I1@", toy)
    keys = [(p, y) for p, y, _ in rows]
    assert len(keys) == len(set(keys))


# --------------------------------------------------------------------------
# 2026-08-28 — the fifteen states, and NARA
#
# These exist for the same reason the BLOCKED tests do: the expensive part of
# this work is the negatives, and a registry that only proves the open rows
# are present would let them rot.
# --------------------------------------------------------------------------


STATES_EVALUATED_2026_08_28 = [
    "kentucky", "virginia", "pennsylvania", "illinois", "michigan",
    "tennessee", "north carolina", "georgia", "alabama", "indiana",
    "maryland", "delaware", "new york", "new hampshire", "south carolina",
    "iowa",
]


def test_nara_catalog_is_blocked_and_says_why():
    """CHANGED VERDICT 2026-08-28, and the change must not be quietly undone.

    It was KEY_REQUIRED for three sessions with a note saying the key was
    free, and nobody checked robots.txt. The whole host is disallowed.
    """
    a = A.REGISTRY["nara-catalog"]
    assert a.verdict == A.BLOCKED
    assert "Disallow: /" in a.disallow_line
    assert "DO NOT REQUEST" in a.recipe
    # The key process is recorded anyway, so the question stays closed
    # rather than being dropped a fourth time.
    assert "Catalog_API@nara.gov" in a.recipe


def test_the_open_nara_route_is_a_different_host_and_is_recorded():
    """The bulk dataset is what W. 8839 came out of.

    It is not a way round the robots block: NARA's own API terms page names
    it as the route for bulk access, and it is a different host with no
    robots.txt of its own.
    """
    a = A.REGISTRY["nara-aws-open-data"]
    assert a.verdict == A.OPEN
    assert "catalog.archives.gov" not in a.base_url
    assert "300022" in a.notes, "the pension series naId is the useful fact"


def test_the_open_census_routes_are_the_three_we_have_verified():
    """This test used to be called `test_only_one_census_year_has_an_open_route`
    and it asserted `== ["nara-1950-census"]`. Its docstring said a second
    OPEN census route would be "either a real find or somebody quietly
    deciding to automate FamilySearch."

    **It was a real find.** On 2026-08-28 the Internet Archive turned out to
    hold the NARA microfilm ITSELF — T626, the 1930 census, scanned by the
    Allen County Public Library Genealogy Center. Three pages of ED 13-58,
    Pennfield Township, Calhoun County were read off it that day. The old
    assertion was never a fact about the world; it was a fact about where
    this project had looked, and it hardened into the former.

    **And a THIRD arrived on 2026-08-29**, the same way: the Internet
    Archive holds ZERO 1940 items, and taking that null seriously instead of
    filing it as a dead end led to NARA's own public S3 bucket, which is
    better indexed than the film. Every federal census year 1850-1950 now
    has an open, keyless machine route.

    The guard that mattered is kept: FamilySearch stays AUTH_WALLED, and if
    that ever changes it is the second branch of the original docstring.
    """
    open_census = sorted(k for k, a in A.REGISTRY.items()
                         if a.verdict == A.OPEN and "census" in k)
    assert open_census == ["ia-census-microfilm", "nara-1940-census",
                           "nara-1950-census"]
    assert A.REGISTRY["familysearch"].verdict == A.AUTH_WALLED


def test_the_reel_map_discovery_is_written_down_not_just_used():
    """The whole locator rests on one sentence: an item's `description` is
    the state's reel-to-county map. If that sentence lives only in code, the
    next session re-derives it."""
    a = A.REGISTRY["ia-census-microfilm"]
    assert "REEL-TO-COUNTY MAP" in a.recipe
    assert "subject:" in a.recipe and "title:" in a.recipe
    assert "DO NOT BUILD AN IDENTIFIER FROM THE REEL NUMBER" in a.recipe
    assert a.adapter == "treetools.ia_census"


def test_the_1940_route_exists_because_a_null_was_taken_seriously():
    a = A.REGISTRY["nara-1940-census"]
    assert a.verdict == A.OPEN
    assert "ZERO" in a.recipe          # the Internet Archive's 1940 count
    assert "population-schedules/" in a.recipe
    assert "metadata/json/" in a.recipe
    assert "STILL NO NAME INDEX" in a.recipe


def test_the_blocked_state_programmes_all_quote_their_evidence():
    for key in ("veridian-state-newspaper-programs", "hathitrust", "dpla",
                "south-carolina-historic-newspapers"):
        a = A.REGISTRY[key]
        assert a.verdict == A.BLOCKED
        assert a.disallow_line, f"{key} is blocked with no evidence"


def test_dpla_and_hathitrust_are_not_re_attempted_as_task_3_sources():
    """The 2026-08-28 prompt assumed both had open APIs. Neither does.

    Recorded so Task 3 is not re-run against them next month.
    """
    assert "ClaudeBot" in A.REGISTRY["dpla"].robots
    assert "403" in A.REGISTRY["hathitrust"].robots
    assert A.REGISTRY["internet-archive"].verdict == A.OPEN


# --------------------------------------------------------------------------
# Record classes, and the gap years inside a span
#
# The registry grew up answering one question — "is there a digitised
# newspaper for this county and year?" — and its holdings model is
# newspaper-shaped down to the `titles` count. Probate is the first record
# class that does not fit it, so a holding now declares which class it is
# about and a query for one class is never answered from a row of another.
# --------------------------------------------------------------------------


def test_a_nationwide_archive_is_not_offered_as_reassurance_on_a_class():
    """A nationwide row with no declared record type says nothing about
    whether it holds probate, and listing it would read as comfort."""
    ans = A.for_place("Clay County, Missouri", 1974, record_type="probate")
    assert ans.nationwide == []


# --- gap years ------------------------------------------------------------


def test_gap_years_all_lie_inside_their_own_span():
    """A gap year outside the span is a typo, and would be invisible because
    the span check would reject it first anyway."""
    for key, a in A.REGISTRY.items():
        for h in a.holdings:
            for y in h.gap_years:
                if h.start_year:
                    assert y >= h.start_year, (key, h.county, y)
                if h.end_year:
                    assert y <= h.end_year, (key, h.county, y)


# --------------------------------------------------------------------------
# 2026-08-28: the Portal to Texas History started blocking this agent by name
#
# The most expensive negative this project has recorded. 34 of its 48
# archived documents came through texashistory.unt.edu. These tests exist so
# that nobody — including a future session reading an old recipe — quietly
# turns the adapter back on.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["portal-texas", "gateway-oklahoma"])
def test_both_unt_archives_are_blocked_and_quote_the_line(key):
    a = A.REGISTRY[key]
    assert a.verdict == A.BLOCKED, key
    assert a.verified_on == "2026-08-28"
    assert "ClaudeBot" in a.disallow_line
    assert "Disallow: /" in a.disallow_line


CLOSED_ON_08_28 = [
    "portal-texas",                  # 34 of 48 archived documents came from here
    "gateway-oklahoma",              # same UNT platform, same robots, same day
    "missouri-death-certificates",   # gave this tree two death certificates
    "michiganology",                 # Marguerite's 1931 record is behind it
    "county-and-court-gov-hosts",    # Clay Co MO and the Kansas courts
]


@pytest.mark.parametrize("key", CLOSED_ON_08_28)
def test_the_sources_that_closed_carry_the_date_and_the_evidence(key):
    a = A.REGISTRY[key]
    assert a.verdict == A.BLOCKED, key
    assert a.verified_on == "2026-08-28", key
    assert a.disallow_line, key
    assert "DO NOT REQUEST" in (a.recipe + a.robots).upper(), key


def test_the_missouri_recipe_is_kept_even_though_it_is_blocked():
    """The three-step session flow and the "Alice for Avice" trap cost a
    session to work out and are still true for a human. A blocked verdict
    deletes permission, not knowledge."""
    a = A.REGISTRY["missouri-death-certificates"]
    assert "session cookie" in a.recipe
    assert "Alice" in a.recipe


def test_every_archive_with_holdings_says_what_class_they_are():
    """A holding whose record class is unknown cannot be filtered, so it can
    only ever be answered by an unqualified query — which is the ambiguity
    this whole mechanism exists to remove."""
    unlabelled = sorted(
        a.key for a in A.REGISTRY.values()
        if a.holdings and any(not a.type_of(h) for h in a.holdings))
    assert unlabelled == [], unlabelled


def test_a_blocked_row_records_WHICH_agent_it_names():
    """Recording a block without recording which agent it names is the same
    failure as recording a null without its denominator.

    All five sources that closed on 2026-08-28 name ClaudeBot — Anthropic's
    TRAINING crawler — and none names Claude-User, the user-initiated agent.
    Four of them additionally declare `Content-Signal: use=reference` with
    `Allow: /` in their wildcard group. That does not licence this package to
    fetch them, and it must not: BLOCKED stays BLOCKED. What it does is keep
    the humane routes visible instead of buried under one flat word."""
    for key in ("portal-texas", "gateway-oklahoma",
                "county-and-court-gov-hosts"):
        a = A.REGISTRY[key]
        text = (a.robots + a.notes).lower()
        assert "claudebot" in text, key
        assert "claude-user" in text, key
        assert a.verdict == A.BLOCKED, key


def test_the_three_anthropic_agents_are_documented_with_their_purposes():
    assert set(A.CLAUDE_AGENTS) == {"claudebot", "claude-user",
                                    "claude-searchbot"}
    assert "training" in A.CLAUDE_AGENTS["claudebot"]
    assert "user-initiated" in A.CLAUDE_AGENTS["claude-user"]


# ==========================================================================
# Engine behaviour against a user's OWN registered data
# ==========================================================================
#
# The shipped registry deliberately carries no holdings -- coverage findings
# are the output of somebody's own research, not something to inherit. These
# tests therefore build a small private registry and prove the engine does
# the right thing with it, which is exactly how a user will actually use it.


def _own_registry():
    """A researcher's own findings, of the kind they'd add themselves."""
    reg = {}
    reg["county-clerk"] = A.Archive(
        key="county-clerk",
        name="Example County Clerk",
        base_url="https://clerk.example.gov",
        operator="Example County",
        verdict=A.NO_MACHINE_INTERFACE,
        verified_on="2026-01-15",
        holdings=(
            A.Holding("kansas", "example", 1885, 1920, None,
                    "Probate minutes. Confirmed complete by phone.",
                    record_type="probate"),
        ),
    )
    reg["state-papers"] = A.Archive(
        key="state-papers",
        name="Example State Newspapers",
        base_url="https://papers.example.org",
        operator="Example State Library",
        verdict=A.OPEN,
        verified_on="2026-01-15",
        holdings=(
            # Digitised, but this county holds zero titles -- a real,
            # recorded coverage gap rather than an untested silence.
            A.Holding("kansas", "example", 1885, 1920, 0,
                    "No titles digitised for this county.",
                    record_type="newspapers"),
        ),
    )
    return reg


def test_the_same_place_answers_differently_per_record_class():
    """'Can I search this county for 1900?' has no single answer.

    Probate is reachable; newspapers are a coverage gap. An answer that
    does not say which record class it is about is worse than no answer.
    """
    reg = _own_registry()
    probate = A.for_place("Example County, Kansas", 1900,
                          registry=reg, record_type="probate")
    papers = A.for_place("Example County, Kansas", 1900,
                         registry=reg, record_type="newspapers")
    # Probate is held (browser-only, but held). Newspapers are a recorded
    # zero -- digitised, but nothing for this county.
    assert probate.manual_coverage or probate.searchable
    assert papers.no_coverage


def test_a_zero_title_holding_is_a_coverage_gap_not_an_absence():
    """Zero digitised titles means a null result proves nothing."""
    reg = _own_registry()
    ans = A.for_place("Example County, Kansas", 1900,
                      registry=reg, record_type="newspapers")
    assert ans.no_coverage
    assert not ans.searchable


def test_a_year_outside_the_holding_span_is_not_offered_as_coverage():
    reg = _own_registry()
    ans = A.for_place("Example County, Kansas", 1870,
                    registry=reg, record_type="probate")
    assert not ans.searchable


def test_browser_only_coverage_is_still_reported_as_coverage():
    """Access and coverage are separate questions.

    An archive a program may not touch still tells you whether a null
    would mean anything -- and that sentence is worth more once the search
    becomes a human job, not less.
    """
    reg = _own_registry()
    ans = A.for_place("Example County, Kansas", 1900,
                      registry=reg, record_type="probate")
    # The clerk is NO_MACHINE_INTERFACE, so it must not appear as
    # machine-searchable -- but its coverage fact must still survive.
    assert not ans.searchable
    assert ans.manual_coverage
    holding_archives = [a.key for a in reg.values()
                        if a.holding_for(A.parse_place("Example County, Kansas"),
                                         "probate")]
    assert "county-clerk" in holding_archives


def test_an_unknown_county_is_unknown_not_empty():
    """An empty result must never read as 'nothing is there'."""
    reg = _own_registry()
    ans = A.for_place("Nowhere County, Kansas", 1900, registry=reg)
    assert ans.unknown or not ans.searchable
