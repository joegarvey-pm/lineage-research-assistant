import pytest

from treetools.parse import parse_string
from treetools.pedigree import Pedigree
from treetools.score import (
    RUBRIC_TIERS, OverrideError, frontier, load_overrides, score_tree,
)
from .conftest import TOY


def _scored(toy, overrides_path):
    o = load_overrides(overrides_path)
    p = Pedigree(toy, o.root)
    return o, p, score_tree(toy, p, o)


def test_overrides_load(toy, toy_overrides):
    o = load_overrides(toy_overrides)
    assert o.root == "@I1@"
    assert o.unsourced_join == 10
    assert o.cited_join == 50
    assert o.validate(toy) == []


def test_manual_score_wins_over_mechanical(toy, toy_overrides):
    _, _, s = _scored(toy, toy_overrides)
    dad = s["@I2@"]
    assert dad.link == 99
    assert dad.link_origin == "override"
    assert dad.link_basis == "Direct knowledge."


def test_mechanical_default_uses_the_join_citation(toy, toy_overrides):
    _, _, s = _scored(toy, toy_overrides)
    # Grandpa's join to Dad sits on @F2@, which carries one citation.
    assert s["@I4@"].join_citation_count == 1
    assert s["@I4@"].link == 50
    assert s["@I4@"].link_origin == "mechanical"
    # Great's join to Grandpa sits on @F3@, which carries none.
    assert s["@I6@"].join_citation_count == 0
    assert s["@I6@"].link == 10


def test_chain_is_the_minimum_link_on_the_path(toy, toy_overrides):
    _, _, s = _scored(toy, toy_overrides)
    # Great(10) -> Grandpa(50) -> Dad(99) -> Sam
    assert s["@I6@"].chain == 10
    assert s["@I6@"].chain_weakest == "@I6@"
    # Grandpa(50) -> Dad(99) -> Sam
    assert s["@I4@"].chain == 50
    assert s["@I4@"].chain_weakest == "@I4@"


def test_chain_is_capped_by_a_weak_join_below_a_strong_one():
    """A perfectly documented ancestor above a guess is still a guess."""
    text = TOY.replace(
        "0 @F3@ FAM\n1 HUSB @I6@\n1 CHIL @I4@\n",
        "0 @F3@ FAM\n1 HUSB @I6@\n1 CHIL @I4@\n1 MARR\n2 DATE 1925\n"
        "2 SOUR @S1@\n3 PAGE names the join\n",
    )
    g = parse_string(text)
    from treetools.score import Overrides
    o = Overrides(root="@I1@", link={
        "@I2@": {"name": "Dad Root", "score": 99, "basis": "known"},
    })
    p = Pedigree(g, "@I1@")
    s = score_tree(g, p, o)
    assert s["@I6@"].link == 50          # its own join is now cited
    assert s["@I4@"].link == 50
    assert s["@I6@"].chain == 50         # still capped at the weakest


def test_root_has_no_chain(toy, toy_overrides):
    _, _, s = _scored(toy, toy_overrides)
    assert s["@I1@"].chain is None
    assert s["@I1@"].is_ancestor is False


def test_every_person_in_the_file_is_scored(toy, toy_overrides):
    _, _, s = _scored(toy, toy_overrides)
    assert set(s) == set(toy.individuals)


# --- overrides validation --------------------------------------------------


def test_score_outside_the_rubric_is_rejected(toy, tmp_path):
    p = tmp_path / "o.yaml"
    p.write_text('root: "@I1@"\nlink:\n  "@I2@":\n    name: Dad Root\n'
                 '    score: 38\n    basis: made up tier\n', encoding="utf-8")
    o = load_overrides(str(p))
    problems = o.validate(toy)
    assert any("not a rubric tier" in x for x in problems)
    with pytest.raises(OverrideError):
        score_tree(toy, Pedigree(toy, "@I1@"), o)


def test_missing_basis_is_rejected(toy, tmp_path):
    p = tmp_path / "o.yaml"
    p.write_text('root: "@I1@"\nlink:\n  "@I2@":\n    name: Dad Root\n'
                 '    score: 99\n', encoding="utf-8")
    o = load_overrides(str(p))
    assert any("no 'basis'" in x for x in o.validate(toy))


def test_unknown_xref_is_rejected(toy, tmp_path):
    p = tmp_path / "o.yaml"
    p.write_text('root: "@I1@"\nlink:\n  "@IGHOST@":\n    name: Nobody\n'
                 '    score: 99\n    basis: x\n', encoding="utf-8")
    assert any("not in this GEDCOM"
               in x for x in load_overrides(str(p)).validate(toy))


def test_name_mismatch_is_rejected(toy, tmp_path):
    """The guard against a renumbered export silently re-scoring."""
    p = tmp_path / "o.yaml"
    p.write_text('root: "@I1@"\nlink:\n  "@I2@":\n    name: Someone Else\n'
                 '    score: 99\n    basis: x\n', encoding="utf-8")
    assert any("name mismatch"
               in x for x in load_overrides(str(p)).validate(toy))


def test_name_check_tolerates_stray_double_spaces(toy, tmp_path):
    p = tmp_path / "o.yaml"
    p.write_text('root: "@I1@"\nlink:\n  "@I2@":\n    name: "Dad   Root"\n'
                 '    score: 99\n    basis: x\n', encoding="utf-8")
    assert load_overrides(str(p)).validate(toy) == []


def test_lax_mode_does_not_raise(toy, tmp_path):
    p = tmp_path / "o.yaml"
    p.write_text('root: "@I1@"\nlink:\n  "@IGHOST@":\n    name: Nobody\n'
                 '    score: 99\n    basis: x\n', encoding="utf-8")
    o = load_overrides(str(p))
    score_tree(toy, Pedigree(toy, "@I1@"), o, strict=False)


def test_missing_overrides_file_is_not_an_error(tmp_path):
    o = load_overrides(str(tmp_path / "nope.yaml"))
    assert o.link == {}
    assert o.unsourced_join == 10


def test_frontier_returns_the_shallowest_weak_row(toy, toy_overrides):
    _, _, s = _scored(toy, toy_overrides)
    rows = frontier(s, threshold=90)
    assert [r.xref for r in rows] == ["@I4@", "@I5@"]     # generation 2
    assert all(r.generation == 2 for r in rows)


# --- integration -----------------------------------------------------------

PROJECT_OVERRIDES = "overrides.yaml"

