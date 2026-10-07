import pytest

from treetools.parse import parse_string
from treetools.pedigree import Pedigree, find_root


def test_root_is_generation_zero_ahnentafel_one(toy):
    p = Pedigree(toy, "@I1@")
    info = p.info("@I1@")
    assert (info.generation, info.ahnentafel) == (0, 1)
    assert info.child_toward_root is None


def test_ahnentafel_father_is_2n_mother_is_2n_plus_1(toy):
    p = Pedigree(toy, "@I1@")
    assert p.info("@I2@").ahnentafel == 2      # father
    assert p.info("@I3@").ahnentafel == 3      # mother
    assert p.info("@I4@").ahnentafel == 4      # father's father
    assert p.info("@I5@").ahnentafel == 5      # father's mother
    assert p.info("@I6@").ahnentafel == 8      # father's father's father


def test_generations(toy):
    p = Pedigree(toy, "@I1@")
    assert p.generation("@I2@") == 1
    assert p.generation("@I4@") == 2
    assert p.generation("@I6@") == 3


def test_child_toward_root_is_the_home_path_child(toy):
    p = Pedigree(toy, "@I1@")
    assert p.info("@I6@").child_toward_root == "@I4@"
    assert p.info("@I4@").child_toward_root == "@I2@"
    assert p.info("@I2@").child_toward_root == "@I1@"


def test_join_family_is_the_family_where_the_child_appears(toy):
    p = Pedigree(toy, "@I1@")
    assert p.info("@I4@").join_family == "@F2@"
    assert p.info("@I2@").join_family == "@F1@"


def test_path_to_root(toy):
    p = Pedigree(toy, "@I1@")
    assert p.path_to_root("@I6@") == ["@I6@", "@I4@", "@I2@", "@I1@"]
    assert p.path_to_root("@I1@") == ["@I1@"]


def test_non_ancestor_has_no_path(toy):
    p = Pedigree(toy, "@I1@")
    assert p.path_to_root("@NOPE@") == []
    assert "@NOPE@" not in p


def test_ancestor_count_excludes_nobody_reachable(toy):
    p = Pedigree(toy, "@I1@")
    assert len(p) == 6           # everyone in the toy tree is an ancestor
    assert p.non_ancestors() == []


COLLAPSE = """0 HEAD
0 @I1@ INDI
1 NAME Child /X/
1 FAMC @F1@
0 @I2@ INDI
1 NAME Father /X/
1 FAMS @F1@
1 FAMC @F2@
0 @I3@ INDI
1 NAME Mother /X/
1 FAMS @F1@
1 FAMC @F2@
0 @I4@ INDI
1 NAME Shared Ancestor /X/
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I3@
1 CHIL @I1@
0 @F2@ FAM
1 HUSB @I4@
1 CHIL @I2@
1 CHIL @I3@
0 TRLR
"""


def test_pedigree_collapse_keeps_the_lowest_ahnentafel():
    """One person reachable by two paths keeps the shallower one."""
    g = parse_string(COLLAPSE)
    p = Pedigree(g, "@I1@")
    info = p.info("@I4@")
    # Reachable as 4 (father's father) and 6 (mother's father).
    assert info.ahnentafel == 4
    assert info.extra_paths == [6]
    assert info.generation == 2


def test_pedigree_collapse_does_not_loop():
    g = parse_string(COLLAPSE)
    p = Pedigree(g, "@I1@")
    assert p.path_to_root("@I4@") == ["@I4@", "@I2@", "@I1@"]


def test_find_root_rejects_ambiguity(toy):
    with pytest.raises(LookupError, match="ambiguous"):
        find_root(toy, "Root")


def test_find_root_rejects_a_miss(toy):
    with pytest.raises(LookupError, match="no individual"):
        find_root(toy, "Nobody At All")


def test_find_root_accepts_a_unique_match(toy):
    assert find_root(toy, "Granny") == "@I5@"


def test_unknown_root_is_an_error(toy):
    with pytest.raises(KeyError):
        Pedigree(toy, "@NOSUCH@")


# --- integration -----------------------------------------------------------

