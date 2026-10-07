"""Tests for the markdown / Mermaid tree renderers.

The property that matters most here is that the renderers colour by CHAIN,
never by LINK. A person can have a strong LINK of their own and still be
unproven from the root's point of view, and a picture that showed LINK would
make an undocumented tree look documented.
"""

import tempfile
import os

import pytest

from treetools import parse_string, Pedigree, score_tree
from treetools.score import load_overrides
from treetools import treemap


@pytest.fixture
def rendered(toy, toy_overrides):
    o = load_overrides(toy_overrides)
    ped = Pedigree(toy, o.root)
    scores = score_tree(toy, ped, o, strict=False)
    return toy, ped, scores


# --- tiers -----------------------------------------------------------------

def test_tier_boundaries_follow_the_rubric_not_round_numbers():
    assert treemap._tier(99) == "documented"
    assert treemap._tier(75) == "documented"      # 75 is the boundary itself
    assert treemap._tier(50) == "thin"
    assert treemap._tier(25) == "thin"            # 25 is the boundary itself
    assert treemap._tier(10) == "unproven"
    assert treemap._tier(0) == "unproven"


def test_a_missing_chain_is_unproven_not_an_error():
    assert treemap._tier(None) == "unproven"


def test_the_root_person_is_never_rendered_as_unproven():
    """The root has no join of their own, so CHAIN is None by design.

    Showing them greyed-out would misrepresent the one person in the tree
    nobody is uncertain about.
    """
    assert treemap._tier(None, is_root=True) == "root"
    assert treemap._tier(10, is_root=True) == "root"


# --- the central promise ---------------------------------------------------

def test_renderers_show_chain_not_link(rendered):
    """A strong LINK above a weak join must still render as weak."""
    gedcom, ped, scores = rendered
    great = next(s for s in scores.values() if s.name.startswith("Great"))
    # Deliberately give them a perfect LINK of their own...
    object.__setattr__(great, "link", 99)
    # ...while their CHAIN stays low because of the join below them.
    object.__setattr__(great, "chain", 10)

    out = treemap.render(gedcom, ped, scores, fmt="table")
    row = [ln for ln in out.split("\n") if "Great" in ln][0]
    assert "99%" in row          # LINK is shown
    assert "**10%**" in row      # but CHAIN is the bolded, honest one
    assert "unproven" in row     # and the verdict follows CHAIN


# --- formats ---------------------------------------------------------------

def test_all_three_formats_render_without_error(rendered):
    gedcom, ped, scores = rendered
    for fmt in ("indent", "mermaid", "table"):
        out = treemap.render(gedcom, ped, scores, fmt=fmt)
        assert out.strip()


def test_an_unknown_format_names_the_valid_ones(rendered):
    gedcom, ped, scores = rendered
    with pytest.raises(ValueError) as e:
        treemap.render(gedcom, ped, scores, fmt="svg")
    msg = str(e.value)
    assert "svg" in msg and "mermaid" in msg and "indent" in msg


def test_mermaid_is_a_fenced_block_so_it_renders_on_github(rendered):
    gedcom, ped, scores = rendered
    out = treemap.render(gedcom, ped, scores, fmt="mermaid")
    assert out.startswith("```mermaid")
    assert out.rstrip().endswith("```")
    assert "graph RL" in out


def test_mermaid_edges_follow_ahnentafel_arithmetic(rendered):
    """Parents of person N are always 2N and 2N+1 — no tree walk needed."""
    gedcom, ped, scores = rendered
    out = treemap.render(gedcom, ped, scores, fmt="mermaid")
    assert "A2 --> A1" in out      # father -> root
    assert "A3 --> A1" in out      # mother -> root
    assert "A4 --> A2" in out      # grandfather -> father


def test_mermaid_assigns_every_node_a_style_class(rendered):
    gedcom, ped, scores = rendered
    out = treemap.render(gedcom, ped, scores, fmt="mermaid")
    classed = set()
    for line in out.split("\n"):
        if line.strip().startswith("class "):
            ids = line.strip()[len("class "):].split()[0]
            classed.update(ids.rstrip(";").split(","))
    declared = {ln.strip().split("[")[0]
                for ln in out.split("\n") if ln.strip().startswith("A")
                and "[" in ln}
    assert declared and declared == classed


def test_mermaid_escapes_characters_that_break_the_parser():
    assert '"' not in treemap._escape('A "quoted" name')
    assert "[" not in treemap._escape("Name [bracketed]")


# --- the frontier ----------------------------------------------------------

def test_frontier_names_the_shallowest_weak_join(rendered):
    """Not the weakest overall -- the shallowest, because depth above a
    weak join is capped by it."""
    gedcom, ped, scores = rendered
    out = treemap.render(gedcom, ped, scores, fmt="indent")
    # Grandpa (gen 2, CHAIN 50) is shallower than Great (gen 3, CHAIN 10)
    assert "Grandpa Root" in out.split("Frontier")[1]


def test_frontier_never_reports_the_root_person(rendered):
    gedcom, ped, scores = rendered
    out = treemap.render(gedcom, ped, scores, fmt="indent")
    tail = out.split("Frontier")[1]
    assert "Sam Root" not in tail


def test_a_fully_documented_line_says_so_instead_of_inventing_a_frontier(toy,
                                                                        toy_overrides):
    o = load_overrides(toy_overrides)
    ped = Pedigree(toy, o.root)
    scores = score_tree(toy, ped, o, strict=False)
    for s in scores.values():
        if s.is_ancestor:
            object.__setattr__(s, "chain", 99)
    out = treemap.render(toy, ped, scores, fmt="indent")
    assert "documented to 75% or better" in out


# --- generation limit ------------------------------------------------------

def _table_rows(out):
    """Just the data rows, excluding the frontier note underneath."""
    return [ln for ln in out.split("\n")
            if ln.startswith("|") and not ln.startswith("|---")
            and not ln.startswith("| Ahn")]


def test_generation_limit_is_respected(rendered):
    gedcom, ped, scores = rendered
    shallow = _table_rows(treemap.render(gedcom, ped, scores,
                                         fmt="table", generations=1))
    assert not any("Grandpa Root" in r for r in shallow)
    deep = _table_rows(treemap.render(gedcom, ped, scores,
                                      fmt="table", generations=3))
    assert any("Grandpa Root" in r for r in deep)


def test_frontier_looks_at_the_whole_tree_not_just_the_rendered_range(rendered):
    """Deliberate: a shallow view should still tell you where the work is.

    Hiding the frontier because you asked for a two-generation picture
    would make the most useful line in the output disappear exactly when a
    beginner is most likely to be looking at it.
    """
    gedcom, ped, scores = rendered
    out = treemap.render(gedcom, ped, scores, fmt="table", generations=1)
    assert "Grandpa Root" not in "\n".join(_table_rows(out))   # not in the table
    assert "Grandpa Root" in out.split("Frontier")[1]           # but still flagged
