import pytest

from treetools.parse import parse_date, parse_string, parse_text


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------


def test_record_counts(toy):
    assert len(toy.individuals) == 6
    assert len(toy.families) == 3
    assert len(toy.sources) == 1


def test_header_facts(toy):
    assert toy.export_date == "1 Jan 2026 12:00:00"
    assert toy.tree_name == "Toy Tree"


def test_multiple_names_are_all_kept(toy):
    dad = toy.individuals["@I2@"]
    assert len(dad.names) == 2
    assert dad.alt_names() == ["Dad Root", "Daddy Root"]
    # The first NAME is the display name.
    assert dad.name == "Dad Root"
    assert dad.surname == "Root"


def test_pointers_and_links(toy):
    root = toy.individuals["@I1@"]
    assert root.famc == ["@F1@"]
    assert root.fams == []
    fam = toy.families["@F1@"]
    assert fam.husband == "@I2@"
    assert fam.wife == "@I3@"
    assert fam.children == ["@I1@"]


def test_citation_nested_under_an_event_is_found(toy):
    dad = toy.individuals["@I2@"]
    assert len(dad.citations) == 1
    cite = dad.citations[0]
    assert cite.source_xref == "@S1@"
    assert cite.page == "Birth index"
    # It must know which event it hung under -- that is what lets scoring
    # tell a birth citation from a name citation.
    assert cite.context_tag == "BIRT"


def test_family_join_citation_is_counted_separately(toy):
    assert toy.families["@F2@"].join_citation_count == 1
    assert toy.families["@F1@"].join_citation_count == 0


def test_events_carry_date_and_place(toy):
    root = toy.individuals["@I1@"]
    assert root.birth.date.raw == "7 Oct 1985"
    assert root.birth.place.startswith("Rivertown")
    assert root.birth_year == 1985


# --------------------------------------------------------------------------
# CONT / CONC
# --------------------------------------------------------------------------


def test_conc_joins_with_no_separator():
    recs = parse_text("0 @I1@ INDI\n1 NOTE part\n2 CONC one\n")
    assert recs[0].children[0].value == "partone"


def test_cont_joins_with_a_newline():
    recs = parse_text("0 @I1@ INDI\n1 NOTE line one\n2 CONT line two\n")
    assert recs[0].children[0].value == "line one\nline two"


def test_conc_at_depth_reassembles_a_split_url():
    """The real file splits a URL across PAGE + CONC at level 3/4."""
    text = (
        "0 @I1@ INDI\n"
        "1 BIRT\n"
        "2 SOUR @S1@\n"
        "3 PAGE The Example County Herald; URL: https://x.test/?xid=33\n"
        "4 CONC 55\n"
    )
    g = parse_string(text)
    page = g.individuals["@I1@"].citations[0].page
    assert page.endswith("xid=3355")
    assert "\n" not in page


def test_conc_does_not_create_a_child_node():
    recs = parse_text("0 @I1@ INDI\n1 NOTE a\n2 CONC b\n")
    assert recs[0].children[0].children == []


# --------------------------------------------------------------------------
# underscore tags must survive
# --------------------------------------------------------------------------


UNDERSCORE = """0 @O1@ OBJE
1 FILE
2 FORM jpg
2 TITL A portrait
1 _OID abc-123
1 _CREA 2026-08-25 04:18:42.054
1 _CLON
2 _TID 63767172
2 _PID 122181827977
2 _DATE 2020-04-18 23:05:58.000
1 _ORIG u
0 TRLR
"""


def test_underscore_tags_are_preserved():
    g = parse_string(UNDERSCORE)
    obj = g.objects["@O1@"]
    assert obj.is_clone
    assert obj.source_tree_id == "63767172"
    assert obj.source_person_id == "122181827977"
    assert obj.clone_date == "2020-04-18 23:05:58.000"
    assert obj.created == "2026-08-25 04:18:42.054"
    assert obj.origin == "u"
    assert obj.title == "A portrait"


def test_underscore_tags_survive_in_the_raw_tree():
    g = parse_string(UNDERSCORE)
    tags = {n.tag for n in g.objects["@O1@"].node.walk()}
    for t in ("_OID", "_CREA", "_CLON", "_TID", "_PID", "_DATE", "_ORIG"):
        assert t in tags, f"{t} was dropped"


def test_object_without_clone_is_not_a_clone():
    g = parse_string("0 @O2@ OBJE\n1 FILE\n2 TITL Local\n1 _CREA 2026-01-01\n")
    assert g.objects["@O2@"].is_clone is False
    assert g.objects["@O2@"].source_tree_id == ""


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw,year,month,day", [
    ("6 December 1924", 1924, 12, 6),
    ("6 Dec 1924", 1924, 12, 6),
    ("Dec 1924", 1924, 12, None),
    ("1924", 1924, None, None),
    ("May 01 1886", 1886, 5, 1),
    ("12/24/1879", 1879, 12, 24),
    ("Abt 1950", 1950, None, None),
    ("abt 1828", 1828, None, None),
    ("Bef. 10 Dec 1817", 1817, 12, 10),
])
def test_date_parsing(raw, year, month, day):
    d = parse_date(raw)
    assert d.parsed
    assert (d.year, d.month, d.day) == (year, month, day)
    assert d.raw == raw


@pytest.mark.parametrize("raw", ["Date Unknown", "unknown", "3 Nov", ""])
def test_unparseable_dates_are_not_guessed(raw):
    d = parse_date(raw)
    assert d.parsed is False
    assert d.year is None
    assert d.raw == raw          # kept verbatim


def test_qualifiers_are_recorded():
    assert parse_date("Abt 1695").qualifier == "abt"
    assert parse_date("Bef. 4 Jun 1746").qualifier == "bef"
    assert parse_date("After 15 Dec 1760").qualifier == "aft"


def test_ambiguous_date_keeps_every_year():
    d = parse_date("1614 or 1618 or 1620 or 14 Mar 1628")
    assert d.ambiguous
    assert d.years == (1614, 1618, 1620, 1628)
    assert d.year == 1614          # the headline reading is the first
    assert d.year_max == 1628      # but the widest reading is available
    assert d.approximate


def test_year_range_is_flagged_not_averaged():
    d = parse_date("1983-2009")
    assert d.ambiguous
    assert d.years == (1983, 2009)


def test_slash_date_with_impossible_month_is_not_swapped():
    d = parse_date("24/12/1879")
    assert d.year == 1879
    assert d.month is None       # refuses to guess d/m vs m/d
    assert d.day is None


# --------------------------------------------------------------------------
# robustness
# --------------------------------------------------------------------------


def test_bom_is_stripped(tmp_path):
    from treetools import parse_file
    p = tmp_path / "bom.ged"
    p.write_text("﻿0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME A /B/\n",
                 encoding="utf-8")
    g = parse_file(str(p))
    assert "@I1@" in g.individuals


def test_malformed_line_is_kept_not_dropped():
    recs = parse_text("0 @I1@ INDI\n1 NAME A /B/\nthis is not gedcom\n")
    tags = [n.tag for n in recs[0].walk()]
    assert "_UNPARSED" in tags


def test_blank_lines_are_ignored():
    recs = parse_text("0 @I1@ INDI\n\n\n1 NAME A /B/\n")
    assert len(recs) == 1
    assert len(recs[0].children) == 1


def test_find_by_name_matches_alternates(toy):
    assert [i.xref for i in toy.find_by_name("Daddy")] == ["@I2@"]


# --------------------------------------------------------------------------
# integration against the real export
# --------------------------------------------------------------------------

