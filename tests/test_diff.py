from treetools.diff import diff, format_report
from treetools.parse import parse_string

BEFORE = """0 HEAD
1 DATE 22 Aug 2026
2 TIME 23:14:24
0 @I1@ INDI
1 NAME Stable /Person/
1 BIRT
2 DATE 1900
2 SOUR @S1@
3 PAGE a record
0 @I2@ INDI
1 NAME Quietly /Grown/
1 BIRT
2 DATE 1880
0 @S1@ SOUR
1 TITL A Collection
0 TRLR
"""

AFTER = """0 HEAD
1 DATE 25 Aug 2026
2 TIME 04:50:16
0 @I1@ INDI
1 NAME Stable /Person/
1 BIRT
2 DATE 1900
2 SOUR @S1@
3 PAGE a record
0 @I2@ INDI
1 NAME Quietly /Grown/
1 BIRT
2 DATE 1880
2 PLAC Somewhere, Kansas, USA
1 DEAT
2 DATE 1955
2 PLAC Elsewhere, Kansas, USA
1 OBJE @O1@
0 @I3@ INDI
1 NAME Brand /New/
1 BIRT
2 DATE 1850
0 @O1@ OBJE
1 FILE
2 TITL x
0 @S1@ SOUR
1 TITL A Collection
0 TRLR
"""


def _d():
    return diff(parse_string(BEFORE), parse_string(AFTER))


def test_headline_counts():
    r = _d()
    assert (r.people_before, r.people_after) == (2, 3)
    assert r.net_people == 1
    assert r.net_sources == 0
    assert r.shared_people == 2


def test_added_and_removed():
    r = _d()
    assert r.people_added == ["@I3@"]
    assert r.people_removed == []
    assert r.added_without_citations == 1
    assert r.added_with_citations == 0


def test_the_headline_flag_finds_facts_without_sources():
    r = _d()
    assert [d.xref for d in r.unsourced_growth] == ["@I2@"]
    d = r.unsourced_growth[0]
    assert d.gained_facts == 1          # gained a DEAT
    assert d.gained_citations == 0
    assert d.gained_media == 1
    assert d.unsourced_growth is True


def test_new_fact_summary_names_what_arrived():
    d = _d().unsourced_growth[0]
    joined = " ".join(d.new_fact_summary)
    assert "DEAT" in joined and "1955" in joined
    # The birth changed too -- it gained a place.
    assert any("BIRT" in f and "Somewhere" in f for f in d.new_fact_summary)


def test_a_person_who_did_not_change_is_not_listed():
    r = _d()
    assert "@I1@" not in [d.xref for d in r.changed]
    assert r.unchanged_people == 1


def test_gaining_facts_with_a_citation_is_not_flagged():
    after = AFTER.replace(
        "1 DEAT\n2 DATE 1955\n2 PLAC Elsewhere, Kansas, USA\n",
        "1 DEAT\n2 DATE 1955\n2 SOUR @S1@\n3 PAGE death record\n")
    r = diff(parse_string(BEFORE), parse_string(after))
    assert r.unsourced_growth == []


def test_removal_is_detected():
    r = diff(parse_string(AFTER), parse_string(BEFORE))
    assert r.people_removed == ["@I3@"]
    assert r.net_people == -1


def test_name_matching_mode():
    """When xrefs are renumbered, fall back to name + birth year."""
    renumbered = AFTER.replace("@I1@", "@X99@")
    r = diff(parse_string(BEFORE), parse_string(renumbered),
             match_by_name=True)
    assert r.match_mode == "name+birth-year"
    assert r.people_added == ["@I3@"]
    assert r.people_removed == []


def test_xref_matching_would_see_a_renumber_as_churn():
    """Contrast with the above -- this is why the mode is explicit."""
    renumbered = AFTER.replace("@I1@", "@X99@")
    r = diff(parse_string(BEFORE), parse_string(renumbered))
    assert "@I1@" in r.people_removed
    assert "@X99@" in r.people_added


def test_report_states_the_denominator_on_a_clean_result():
    r = diff(parse_string(BEFORE), parse_string(BEFORE))
    text = format_report(r)
    assert "0 of 2 checked" in text
    assert "purely additive" in text


def test_report_renders():
    text = format_report(_d())
    assert "Quietly Grown" in text
    assert "+1" in text


# --- integration -----------------------------------------------------------

