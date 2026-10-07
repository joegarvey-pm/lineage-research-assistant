import os
from types import SimpleNamespace

import pytest

from treetools.evidence import (
    Document, EvidenceError, Manifest, PUBLISHABLE, sha256_file,
)


def _doc(**kw):
    base = dict(id="d1", title="A record", tier="secondary",
                status="archived", rights="public-domain",
                repository="NARA", retrieved="2026-08-25")
    base.update(kw)
    return Document(**base)


@pytest.fixture
def archive(tmp_path):
    return Manifest(str(tmp_path / "evidence"))


@pytest.fixture
def a_file(tmp_path):
    p = tmp_path / "scan.jpg"
    p.write_bytes(b"\xff\xd8\xff not really a jpeg but bytes are bytes")
    return str(p)


# --- hashing and storage ---------------------------------------------------


def test_file_is_stored_under_its_own_hash(archive, a_file):
    d = archive.add_file(a_file, _doc())
    assert d.sha256 == sha256_file(a_file)
    stored = d.path(archive.root)
    assert os.path.exists(stored)
    assert d.sha256 in stored
    # fanned out by the first two hex characters
    assert os.path.basename(os.path.dirname(stored)) == d.sha256[:2]


def test_extension_is_preserved_for_humans(archive, a_file):
    d = archive.add_file(a_file, _doc())
    assert d.path(archive.root).endswith(".jpg")
    assert d.media_type == "image/jpeg"
    assert d.filename == "scan.jpg"


def test_the_same_file_twice_is_refused(archive, a_file, tmp_path):
    archive.add_file(a_file, _doc(id="first"))
    copy = tmp_path / "renamed.jpg"
    copy.write_bytes(open(a_file, "rb").read())
    with pytest.raises(EvidenceError, match="already archived as 'first'"):
        archive.add_file(str(copy), _doc(id="second"))


def test_duplicate_id_is_refused(archive, a_file, tmp_path):
    archive.add_file(a_file, _doc(id="dup"))
    other = tmp_path / "other.jpg"
    other.write_bytes(b"different bytes entirely")
    with pytest.raises(EvidenceError, match="already in the manifest"):
        archive.add_file(str(other), _doc(id="dup"))


def test_missing_source_file_is_refused(archive):
    with pytest.raises(EvidenceError, match="no such file"):
        archive.add_file("/nope/nothing.jpg", _doc())


# --- validation ------------------------------------------------------------


def test_repository_is_required():
    problems = _doc(repository="").validate()
    assert any("repository is required" in p for p in problems)


def test_bad_tier_is_rejected():
    assert any("tier" in p for p in _doc(tier="pretty-good").validate())


def test_bad_rights_is_rejected():
    assert any("rights" in p for p in _doc(rights="probably fine").validate())


def test_unavailable_must_say_why():
    d = _doc(status="unavailable", sha256="", notes="")
    assert any("must say why" in p for p in d.validate())
    d.notes = "Example County has no 1924 issues"
    assert not any("must say why" in p for p in d.validate())


def test_archived_without_a_hash_is_rejected():
    assert any("no sha256" in p for p in _doc(sha256="").validate())


def test_a_clean_document_validates(archive, a_file):
    d = archive.add_file(a_file, _doc())
    assert d.validate() == []


# --- rights ----------------------------------------------------------------


@pytest.mark.parametrize("rights,expected", [
    ("public-domain", True), ("own-copy", True),
    ("licensed-view-only", False), ("third-party", False),
    ("unknown", False),
])
def test_publishable_defaults_to_no(rights, expected):
    assert _doc(rights=rights).publishable is expected


def test_unknown_rights_is_not_publishable():
    """The default must be safe: unknown behaves like 'do not publish'."""
    assert "unknown" not in PUBLISHABLE


# --- integrity -------------------------------------------------------------


def test_verify_passes_on_a_clean_archive(archive, a_file):
    archive.add_file(a_file, _doc())
    rep = archive.verify()
    assert rep["ok"] == ["d1"]
    assert not rep["missing"] and not rep["corrupt"] and not rep["orphan"]


def test_verify_detects_corruption(archive, a_file):
    d = archive.add_file(a_file, _doc())
    with open(d.path(archive.root), "wb") as fh:
        fh.write(b"tampered")
    assert archive.verify()["corrupt"] == ["d1"]


def test_verify_detects_a_missing_file(archive, a_file):
    d = archive.add_file(a_file, _doc())
    os.remove(d.path(archive.root))
    assert archive.verify()["missing"] == ["d1"]


def test_verify_detects_an_orphan(archive, a_file):
    archive.add_file(a_file, _doc())
    stray = os.path.join(archive.root, "documents", "zz")
    os.makedirs(stray)
    open(os.path.join(stray, "loose.jpg"), "wb").write(b"x")
    assert archive.verify()["orphan"]


# --- round trip ------------------------------------------------------------


def test_manifest_round_trips(archive, a_file):
    archive.add_file(a_file, _doc(people=["@I1@"], free_source="NARA"))
    archive.save()
    again = Manifest.load(archive.root)
    assert len(again.documents) == 1
    d = again.documents[0]
    assert d.id == "d1" and d.people == ["@I1@"] and d.free_source == "NARA"
    assert again.validate() == []


def test_loading_a_missing_manifest_is_empty_not_an_error(tmp_path):
    """A path that does not exist yet is how a NEW archive is created:
    `evidence add` loads first and `save()` does the makedirs. Keep it."""
    assert Manifest.load(str(tmp_path / "nothing")).documents == []


# --- the false positive: verify used to pass while checking nothing --------
#
# `treetools evidence verify --evidence evidence/manifest.yaml` -- the manifest
# FILE rather than the evidence/ DIRECTORY -- printed "archive is INTACT" and
# exited 0 while checking ZERO documents, because Manifest.load joined the
# given path with "manifest.yaml", looked for evidence/manifest.yaml/manifest
# .yaml, did not find it, and quietly returned an empty manifest. Every
# session prompt in this project lists "evidence verify INTACT" as a pass
# condition, so this let that check pass while verifying nothing.
# Reproduced live and fixed 2026-08-31 (Part E; [[12 Tech Reduction Roadmap]]
# item 6). These four tests are the pass/fail criterion that item asked for.


def test_load_refuses_the_manifest_file_and_says_what_to_pass(archive, a_file):
    """The exact wrong path a human actually types."""
    archive.add_file(a_file, _doc())
    archive.save()
    with pytest.raises(EvidenceError) as exc:
        Manifest.load(archive.path)          # the FILE, not the directory
    msg = str(exc.value)
    assert "not a directory" in msg
    assert "--evidence " + archive.root in msg


def test_load_refuses_any_path_that_exists_but_is_not_a_directory(tmp_path):
    f = tmp_path / "some.txt"
    f.write_text("not an archive")
    with pytest.raises(EvidenceError):
        Manifest.load(str(f))


def test_cli_verify_exits_nonzero_when_it_checked_nothing(tmp_path, capsys):
    """The heart of it: a verify that checked no documents is NOT a pass,
    whatever the cause -- wrong path, empty manifest, unparsed manifest."""
    from treetools.cli import cmd_evidence

    empty = tmp_path / "evidence"
    empty.mkdir()
    args = SimpleNamespace(action="verify", evidence=str(empty), gedcom=None)
    rc = cmd_evidence(args)
    out = capsys.readouterr().out
    assert rc == 1
    assert "VERIFIED NOTHING" in out
    assert "archive is INTACT" not in out


def test_cli_verify_still_passes_on_a_real_archive(archive, a_file, capsys):
    from treetools.cli import cmd_evidence

    archive.add_file(a_file, _doc())
    archive.save()
    args = SimpleNamespace(action="verify", evidence=archive.root, gedcom=None)
    rc = cmd_evidence(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "archive is INTACT" in out
    assert "VERIFIED NOTHING" not in out


def test_cli_verify_refuses_the_manifest_file_path(archive, a_file, capsys):
    from treetools.cli import cmd_evidence

    archive.add_file(a_file, _doc())
    archive.save()
    args = SimpleNamespace(action="verify", evidence=archive.path, gedcom=None)
    rc = cmd_evidence(args)
    out = capsys.readouterr().out
    assert rc == 1
    assert "refused:" in out
    assert "archive is INTACT" not in out


def test_stats_counts_what_matters(archive, a_file, tmp_path):
    archive.add_file(a_file, _doc(id="have"))
    archive.documents.append(_doc(
        id="want", status="wanted", sha256="", retrieved="",
        free_source="FamilySearch"))
    st = archive.stats()
    assert st["archived"] == 1 and st["wanted"] == 1
    assert st["publishable"] == 1
    assert st["free_route_known"] == 1


def test_by_person(archive, a_file):
    archive.add_file(a_file, _doc(people=["@I1@", "@I2@"]))
    assert len(archive.by_person("@I1@")) == 1
    assert archive.by_person("@I9@") == []


# --- the real archive ------------------------------------------------------


def test_the_project_archive_is_intact():
    root = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "evidence")
    if not os.path.exists(os.path.join(root, "manifest.yaml")):
        pytest.skip("no manifest yet")
    man = Manifest.load(root)
    assert man.validate() == []
    rep = man.verify()
    assert not rep["missing"], rep["missing"]
    assert not rep["corrupt"], rep["corrupt"]
    assert not rep["orphan"], rep["orphan"]


# --- person links must resolve --------------------------------------------


def test_validate_without_a_gedcom_still_works(archive, a_file):
    archive.add_file(a_file, _doc(people=["@ANYTHING@"]))
    assert archive.validate() == []          # cannot check, does not crash



def test_every_portal_document_has_a_free_route():
    """The whole point of the Portal is that it is free and permanent."""
    root = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "evidence")
    if not os.path.exists(os.path.join(root, "manifest.yaml")):
        pytest.skip("no manifest")
    for d in Manifest.load(root).documents:
        if d.id.startswith("portal-"):
            assert d.free_source.startswith("https://texashistory.unt.edu/")
            assert d.repository and "Portal to Texas History" in d.repository


# --- join tier: the document vs what it proves about a relationship --------
#
# The distinction these tests defend is CLAUDE.md's, and it is the one that
# decides whether this tree's ceiling has actually moved: a death certificate
# is a PRIMARY record whose PARENT FIELDS are secondary, because the informant
# was not present at the birth. Collapsing the two would let "joins with a
# primary record" count death certificates and report a ceiling that has not
# been broken.


def test_a_document_may_be_primary_while_its_join_is_secondary():
    d = _doc(tier="primary", join_tier="secondary",
             joins=["@IPARENT@>@ICHILD@"])
    # sha256 is only set when the file is actually filed, so ignore that one.
    assert [p for p in d.validate() if "sha256" not in p] == []
    assert d.primary_for_join is False


def test_join_tier_may_not_exceed_the_document_tier():
    d = _doc(tier="secondary", join_tier="primary",
             joins=["@IPARENT@>@ICHILD@"])
    problems = " ".join(d.validate())
    assert "stronger than" in problems


def test_naming_a_join_without_a_join_tier_is_refused():
    d = _doc(joins=["@IPARENT@>@ICHILD@"], join_tier="")
    assert any("no join_tier" in p for p in d.validate())


def test_malformed_join_is_refused():
    d = _doc(joins=["@IPARENT@ and @ICHILD@"], join_tier="secondary")
    assert any("PARENT>CHILD" in p for p in d.validate())


def test_join_pairs_parses_both_xrefs():
    d = _doc(joins=["@IA@>@IB@", " @IC@ > @ID@ "], join_tier="secondary")
    assert d.join_pairs() == [("@IA@", "@IB@"), ("@IC@", "@ID@")]


def test_join_evidence_keeps_the_strongest_tier_per_join(archive, tmp_path):
    for i, tier in enumerate(("secondary", "primary")):
        p = tmp_path / f"f{i}.txt"
        p.write_text(f"doc {i}", encoding="utf-8")
        archive.add_file(str(p), _doc(
            id=f"d{i}", tier="primary", join_tier=tier,
            joins=["@IA@>@IB@"]))
    assert archive.join_evidence() == {("@IA@", "@IB@"): "primary"}
    assert archive.primary_joins() == [("@IA@", "@IB@")]


def test_stats_report_joins_and_how_many_are_primary(archive, tmp_path):
    p = tmp_path / "one.txt"
    p.write_text("x", encoding="utf-8")
    archive.add_file(str(p), _doc(tier="primary", join_tier="secondary",
                                  joins=["@IA@>@IB@"]))
    st = archive.stats()
    assert st["joins_documented"] == 1
    assert st["joins_with_primary"] == 0


def test_for_join_finds_documents_by_relationship(archive, tmp_path):
    p = tmp_path / "one.txt"
    p.write_text("x", encoding="utf-8")
    archive.add_file(str(p), _doc(tier="primary", join_tier="secondary",
                                  joins=["@IA@>@IB@"]))
    assert [d.id for d in archive.for_join("@IA@", "@IB@")] == ["d1"]
    assert archive.for_join("@IB@", "@IA@") == []


def test_manifest_validate_checks_join_xrefs_against_the_gedcom(archive,
                                                               tmp_path, toy):
    p = tmp_path / "one.txt"
    p.write_text("x", encoding="utf-8")
    archive.add_file(str(p), _doc(tier="primary", join_tier="secondary",
                                  joins=["@I4@>@I2@"]))
    assert archive.validate(toy) == []
    archive.documents[0].joins = ["@INOTREAL@>@I2@"]
    assert any("@INOTREAL@" in x for x in archive.validate(toy))
