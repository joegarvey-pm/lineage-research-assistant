from treetools.audit import (
    check_country_conventions, check_date_quality, check_duplicate_people,
    check_lifespans, check_marriage_ages, check_name_fields,
    check_parent_ages, check_place_fields, check_posthumous_births,
    check_repeated_names, check_sibling_gaps, check_spouse_death_dates,
    run_audit, summarise,
)
from treetools.parse import parse_string


def _fam(children_and_dates, husb=None, wife=None, extra=""):
    """Build a tiny GEDCOM with one family."""
    parts = ["0 HEAD"]
    if husb:
        parts += [f"0 @H@ INDI", "1 NAME Father /X/", "1 FAMS @F@",
                  "1 BIRT", f"2 DATE {husb[0]}"]
        if len(husb) > 1 and husb[1]:
            parts += ["1 DEAT", f"2 DATE {husb[1]}"]
    if wife:
        parts += [f"0 @W@ INDI", "1 NAME Mother /X/", "1 FAMS @F@",
                  "1 BIRT", f"2 DATE {wife[0]}"]
        if len(wife) > 1 and wife[1]:
            parts += ["1 DEAT", f"2 DATE {wife[1]}"]
    for i, d in enumerate(children_and_dates):
        parts += [f"0 @C{i}@ INDI", f"1 NAME Child{i} /X/", "1 FAMC @F@",
                  "1 BIRT", f"2 DATE {d}"]
    parts += ["0 @F@ FAM"]
    if husb:
        parts.append("1 HUSB @H@")
    if wife:
        parts.append("1 WIFE @W@")
    for i, _ in enumerate(children_and_dates):
        parts.append(f"1 CHIL @C{i}@")
    if extra:
        parts.append(extra)
    parts.append("0 TRLR")
    return parse_string("\n".join(parts) + "\n")


# --- parent ages -----------------------------------------------------------


def test_mother_under_14_is_impossible():
    g = _fam(["1900"], wife=("1890",))
    flags = check_parent_ages(g)
    assert [f.code for f in flags] == ["MOTHER_TOO_YOUNG"]
    assert flags[0].severity == "impossible"


def test_mother_at_14_is_not_flagged():
    assert check_parent_ages(_fam(["1904"], wife=("1890",))) == []


def test_mother_over_50_is_implausible():
    g = _fam(["1941"], wife=("1890",))
    flags = check_parent_ages(g)
    assert flags[0].code == "MOTHER_TOO_OLD"
    assert flags[0].severity == "implausible"


def test_mother_at_50_exactly_is_not_flagged():
    assert check_parent_ages(_fam(["1940"], wife=("1890",))) == []


def test_father_under_15_is_flagged():
    g = _fam(["1904"], husb=("1890",))
    assert [f.code for f in check_parent_ages(g)] == ["FATHER_TOO_YOUNG"]


def test_father_at_15_is_not_flagged():
    assert check_parent_ages(_fam(["1905"], husb=("1890",))) == []


def test_parent_born_after_child():
    g = _fam(["1880"], wife=("1890",))
    assert [f.code for f in check_parent_ages(g)] == \
        ["PARENT_BORN_AFTER_CHILD"]


def test_precision_is_recorded():
    g = _fam(["1 Jan 1900"], wife=("1 Jan 1890",))
    assert check_parent_ages(g)[0].precision == "full date"
    g2 = _fam(["1900"], wife=("1890",))
    assert check_parent_ages(g2)[0].precision == "year only"


# --- posthumous ------------------------------------------------------------


def test_child_born_two_years_after_father_dies():
    g = _fam(["1905"], husb=("1870", "1902"))
    flags = check_posthumous_births(g)
    assert flags[0].code == "POSTHUMOUS_BIRTH"
    assert flags[0].severity == "impossible"


def test_child_born_six_months_after_father_dies_is_fine():
    g = _fam(["1 Jul 1902"], husb=("1 Jan 1870", "1 Jan 1902"))
    assert check_posthumous_births(g) == []


def test_ambiguous_birth_year_raises_the_softer_flag():
    """`1614 or 1628` against a 1615 death: which year is right decides."""
    g = _fam(["1614 or 1618 or 1620 or 14 Mar 1628"],
             husb=("1574", "28 Aug 1615"))
    flags = check_posthumous_births(g)
    assert [f.code for f in flags] == \
        ["POSTHUMOUS_BIRTH_IF_AMBIGUOUS_DATE_RESOLVED"]
    assert flags[0].severity == "implausible"
    assert flags[0].precision == "ambiguous"


# --- marriage, siblings, lifespan -----------------------------------------


def test_marriage_before_15():
    g = _fam([], husb=("1890",),
             extra="1 MARR\n2 DATE 1902")
    assert [f.code for f in check_marriage_ages(g)] == ["MARRIAGE_TOO_YOUNG"]


def test_marriage_at_15_is_fine():
    g = _fam([], husb=("1890",), extra="1 MARR\n2 DATE 1905")
    assert check_marriage_ages(g) == []


def test_sibling_gap_over_12_years():
    g = _fam(["1900", "1913"])
    assert [f.code for f in check_sibling_gaps(g)] == ["SIBLING_GAP"]


def test_sibling_gap_of_exactly_12_is_not_flagged():
    assert check_sibling_gaps(_fam(["1900", "1912"])) == []


def test_lifespan_over_100():
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 1815\n"
                     "1 DEAT\n2 DATE 1923\n")
    flags = check_lifespans(g)
    assert flags[0].code == "LONG_LIFESPAN"
    assert "108" in flags[0].message


def test_negative_lifespan():
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 1900\n"
                     "1 DEAT\n2 DATE 1899\n")
    flags = check_lifespans(g)
    assert flags[0].code == "NEGATIVE_LIFESPAN"
    assert flags[0].severity == "impossible"


def test_normal_lifespan_is_silent():
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 1900\n"
                     "1 DEAT\n2 DATE 1980\n")
    assert check_lifespans(g) == []


# --- duplicates and spouses ------------------------------------------------


DUPES = """0 @I1@ INDI
1 NAME Mary /Quill/
1 BIRT
2 DATE 1731
0 @I2@ INDI
1 NAME Mary /Quill/
1 BIRT
2 DATE 1731
0 @I3@ INDI
1 NAME John /Ashby/
1 BIRT
2 DATE 1732
0 @I4@ INDI
1 NAME John /Ashby/
1 BIRT
2 DATE 1760
0 TRLR
"""


def test_duplicate_name_and_birth_year():
    g = parse_string(DUPES)
    flags = check_duplicate_people(g)
    assert len(flags) == 1
    assert flags[0].code == "DUPLICATE_NAME_DATE"
    assert set(flags[0].people) == {"@I1@", "@I2@"}


def test_same_name_different_years_is_the_softer_flag():
    g = parse_string(DUPES)
    flags = check_repeated_names(g)
    assert [f.code for f in flags] == ["NAME_REPEATED_DIFFERENT_YEARS"]
    assert set(flags[0].people) == {"@I3@", "@I4@"}


def test_spouses_sharing_a_death_date():
    g = parse_string(
        "0 @H@ INDI\n1 NAME Amos /Tarrant/\n1 FAMS @F@\n1 DEAT\n"
        "2 DATE 14 Jan 1827\n"
        "0 @W@ INDI\n1 NAME Elizabeth /Vale/\n1 FAMS @F@\n1 DEAT\n"
        "2 DATE 14 Jan 1827\n"
        "0 @F@ FAM\n1 HUSB @H@\n1 WIFE @W@\n")
    flags = check_spouse_death_dates(g)
    assert [f.code for f in flags] == ["SPOUSES_SAME_DEATH_DATE"]


def test_spouses_with_different_death_dates_are_silent():
    g = parse_string(
        "0 @H@ INDI\n1 NAME A /B/\n1 FAMS @F@\n1 DEAT\n2 DATE 1827\n"
        "0 @W@ INDI\n1 NAME C /D/\n1 FAMS @F@\n1 DEAT\n2 DATE 1830\n"
        "0 @F@ FAM\n1 HUSB @H@\n1 WIFE @W@\n")
    assert check_spouse_death_dates(g) == []


# --- place and name hygiene ------------------------------------------------


def test_street_address_in_a_place_field():
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 DEAT\n"
                     "2 PLAC 925 South Seneca\n")
    flags = check_place_fields(g)
    assert flags[0].code == "PLACE_NOT_A_PLACE"
    assert "street address" in flags[0].message


def test_narrative_in_a_place_field():
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 DEAT\n"
                     "2 PLAC Drowned in New River in Montgomery Co, , "
                     "Virginia, USA\n")
    assert "narrative" in check_place_fields(g)[0].message


def test_a_long_but_legitimate_place_is_not_flagged():
    """Length alone is a bad signal -- a real hierarchy runs long."""
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 DEAT\n"
                     "2 PLAC Jackson Township, Dauphin County, "
                     "Pennsylvania, United States of America\n")
    assert check_place_fields(g) == []


def test_country_name_conventions():
    g = parse_string(
        "0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 PLAC Fairview, Kansas, USA\n"
        "0 @I2@ INDI\n1 NAME C /D/\n1 BIRT\n"
        "2 PLAC Fairview, Kansas, United States\n"
        "0 @I3@ INDI\n1 NAME E /F/\n1 BIRT\n"
        "2 PLAC Fairview, Kansas, United States of America\n")
    flags = check_country_conventions(g)
    assert flags[0].code == "COUNTRY_NAME_SPLIT"
    assert "3 different spellings" in flags[0].message


def test_one_country_convention_is_silent():
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n"
                     "2 PLAC Fairview, Kansas, USA\n")
    assert check_country_conventions(g) == []


def test_research_notes_in_a_name_field():
    g = parse_string("0 @I1@ INDI\n1 NAME Samuel D /ADAMS/ GGF6\n")
    assert [f.code for f in check_name_fields(g)] == ["NAME_FIELD_NOISE"]


def test_emoji_in_a_name_field():
    g = parse_string("0 @I1@ INDI\n1 NAME Richard West /Gregory/ \U0001FA78\n")
    assert [f.code for f in check_name_fields(g)] == ["NAME_FIELD_NOISE"]


def test_an_ordinary_name_is_silent():
    g = parse_string("0 @I1@ INDI\n1 NAME Henry Clayton /Tarrant/\n")
    assert check_name_fields(g) == []


# --- date quality ----------------------------------------------------------


def test_ambiguous_and_unparseable_dates_are_reported_separately():
    g = parse_string("0 @I1@ INDI\n1 NAME A /B/\n1 BIRT\n2 DATE 1614 or 1628\n"
                     "1 DEAT\n2 DATE Date Unknown\n")
    codes = {f.code for f in check_date_quality(g)}
    assert codes == {"AMBIGUOUS_DATE", "UNPARSEABLE_DATE"}


# --- runner ----------------------------------------------------------------


def test_coverage_distinguishes_clean_from_uncheckable():
    """A check with no eligible records must not read as 'all clear'."""
    g = _fam(["1900", "1913"])
    result = run_audit(g)
    sib = next(c for c in result.coverage if c.check.startswith("sibling"))
    assert sib.eligible == 1 and sib.flags == 1 and sib.ran
    marr = next(c for c in result.coverage if c.check == "marriage ages")
    assert marr.eligible == 0 and marr.ran is False


def test_flags_sort_impossible_first():
    g = parse_string(
        "0 @H@ INDI\n1 NAME A /B/\n1 FAMS @F@\n1 BIRT\n2 DATE 1890\n"
        "0 @C@ INDI\n1 NAME C /D/\n1 FAMC @F@\n1 BIRT\n2 DATE 1900\n"
        "1 DEAT\n2 DATE 1899\n"
        "0 @F@ FAM\n1 HUSB @H@\n1 CHIL @C@\n")
    result = run_audit(g)
    assert result.flags[0].severity == "impossible"


def test_summarise_counts_codes():
    g = _fam(["1900"], wife=("1890",))
    assert summarise(run_audit(g))["MOTHER_TOO_YOUNG"] == 1


# --- integration -----------------------------------------------------------

