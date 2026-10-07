from treetools.parse import parse_string
from treetools.provenance import analyze, format_report

CLONED = """0 HEAD
0 @I1@ INDI
1 NAME William D /Marsh/
1 OBJE @O1@
0 @O1@ OBJE
1 FILE
2 TITL Portrait
1 _OID aaa
1 _CREA 2026-08-25 04:18:42.054
1 _CLON
2 _TID 46431316
2 _PID 111
2 _DATE 2013-05-24 10:00:00.000
1 _ORIG u
0 @O2@ OBJE
1 FILE
2 TITL Another from the same tree
1 _CREA 2026-08-25 05:00:00.000
1 _CLON
2 _TID 46431316
2 _PID 222
2 _DATE 2015-01-02 10:00:00.000
0 @O3@ OBJE
1 FILE
2 TITL Locally added
1 _CREA 2026-08-22 21:00:00.000
0 @O4@ OBJE
1 FILE
2 TITL Cloned but no tree id
1 _CREA 2026-08-25 06:00:00.000
1 _CLON
2 _DATE 2020-01-01 00:00:00.000
0 TRLR
"""


def test_counts_clones():
    r = analyze(parse_string(CLONED))
    assert r.total_objects == 4
    assert r.cloned_objects == 3
    assert r.native_objects == 1
    assert r.clone_share == 0.75


def test_groups_by_source_tree_id():
    r = analyze(parse_string(CLONED))
    assert r.tree_groups["46431316"].count == 2
    assert r.tree_groups["46431316"].earliest_upload == "2013-05-24"
    assert r.tree_groups["46431316"].latest_upload == "2015-01-02"


def test_clone_without_a_tid_is_bucketed_not_dropped():
    r = analyze(parse_string(CLONED))
    assert "(no _TID)" in r.tree_groups
    assert r.tree_groups["(no _TID)"].count == 1
    assert r.distinct_source_trees == 2      # 46431316 plus the no-TID bucket


def test_creation_histogram_is_by_day():
    r = analyze(parse_string(CLONED))
    assert dict(r.creation_histogram) == {
        "2026-08-22": 1, "2026-08-25": 3,
    }


def test_upload_histogram_uses_the_origin_tree_date():
    """A 2026 copy of a 2013 upload is a 2013 upload."""
    r = analyze(parse_string(CLONED))
    assert dict(r.upload_year_histogram) == {
        "2013": 1, "2015": 1, "2020": 1,
    }


def test_examples_name_the_person_the_media_hangs_off():
    r = analyze(parse_string(CLONED))
    first = r.examples[0]
    assert first["source_tree_id"] == "46431316"
    assert first["attached_to"] == ["William D Marsh"]


def test_no_media_does_not_divide_by_zero():
    r = analyze(parse_string("0 @I1@ INDI\n1 NAME A /B/\n"))
    assert r.total_objects == 0
    assert r.clone_share == 0.0
    assert "Media objects in file      : 0" in format_report(r)


def test_report_renders():
    text = format_report(analyze(parse_string(CLONED)))
    assert "_TID 46431316" in text
    assert "2026-08-25" in text


# --- integration -----------------------------------------------------------

