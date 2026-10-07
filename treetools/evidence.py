"""The evidence archive — your own copies of the documents.

The problem this solves: Ancestry charges rent to hold record images you
already found. When the subscription lapses, the images go with it. This
module keeps your own copy, content-addressed, with enough metadata that a
file on disk is still *evidence* in five years rather than an orphan JPEG.

Three design decisions worth stating, because they are the whole module:

1. **Content-addressed storage.** A document is stored under its own SHA-256,
   not under a filename someone chose. Filenames drift, get renamed, and
   collide; a hash does not. It also makes bitrot detectable — `verify`
   re-hashes everything and tells you what changed.

2. **The manifest is the archive; the files are just bytes.** Every entry
   records what the record *is*, which repository actually holds the
   original, and — critically — **how to get it again for free**. A JPEG with
   no provenance is not evidence, it is a picture. This implements the
   playbook's citation rule: cite the record, not the website you reached it
   through.

3. **Rights are recorded, not assumed.** 184 of the 193 media objects in this
   tree were copied out of strangers' trees. US federal records (census,
   NUMIDENT) are public domain; a photograph someone else uploaded in 2013 is
   not yours to republish. The `rights` field decides what a shared family
   site may show.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

# --------------------------------------------------------------------------
# Vocabulary — small, closed, and enforced. An archive with free-text status
# fields becomes unqueryable within a year.
# --------------------------------------------------------------------------

TIERS = ("primary", "secondary", "not-evidence")

#: How strong a document is **for the parent-child join it evidences**, which
#: is not the same question as how strong the document is.
#:
#: CLAUDE.md is explicit about this and it is easy to get wrong: a death
#: certificate is a *primary* record — made at the time of the death by
#: officials present — but its **parent fields are listed under Secondary**,
#: because the informant was not present at the birth. A 1974 death
#: certificate naming the deceased's father is exactly this case: a primary
#: document, but only secondary evidence for the father -> son join.
#:
#: Without this split, "joins with a primary record" counts death certificates
#: and reports a ceiling the tree has not actually broken.
JOIN_TIERS = ("primary", "secondary", "not-evidence", "")

#: A join is primary-backed only when a primary record names the relationship
#: at the time the relationship came into being: a birth or baptismal
#: register, a marriage record naming parents, a contemporaneous
#: certificate. That is the tier that breaks 75%.
_TIER_RANK = {"not-evidence": 0, "": 0, "secondary": 1, "primary": 2}

RIGHTS = (
    "public-domain",       # US federal records: census, NUMIDENT, draft cards
    "own-copy",            # you photographed it or were given it
    "licensed-view-only",  # seen under a subscription; do NOT republish
    "third-party",         # someone else's upload; lead only, never publish
    "unknown",             # not yet determined — defaults to "do not publish"
)

# Whether a shared family site may display the file at all.
PUBLISHABLE = {"public-domain", "own-copy"}

STATUSES = (
    "archived",      # file is in evidence/documents/ and verified
    "wanted",        # we know it exists and where; not yet obtained
    "unavailable",   # checked, and no copy is obtainable (say why)
)


class EvidenceError(ValueError):
    pass


@dataclass
class Document:
    """One piece of evidence."""

    id: str                       # short human key, e.g. "1930-census-marsh"
    title: str                    # what the record is
    tier: str                     # primary | secondary | not-evidence
    status: str                   # archived | wanted | unavailable
    rights: str

    # Provenance — the four parts the playbook requires.
    record: str = ""              # what the record is, in full
    repository: str = ""          # who actually holds the original
    collection: str = ""          # the collection and unit
    entry: str = ""               # which entry within it
    retrieved: str = ""           # YYYY-MM-DD

    # How to get it again without paying for it. The most valuable field here.
    free_source: str = ""         # URL or plain description; "" = none known
    paid_source: str = ""         # where it was actually obtained, if paid

    # Storage
    sha256: str = ""
    filename: str = ""            # original filename, for humans
    bytes: int = 0
    media_type: str = ""

    # Links back into the tree
    people: List[str] = field(default_factory=list)   # GEDCOM xrefs
    supports: str = ""            # which join or fact this is evidence for
    notes: str = ""

    # Machine-readable joins, so "how many joins have a primary record?" is a
    # query rather than a reading exercise. Each entry is "PARENT>CHILD" in
    # GEDCOM xrefs. `supports` stays as the human sentence.
    joins: List[str] = field(default_factory=list)
    join_tier: str = ""           # strength FOR THE JOIN — see JOIN_TIERS

    def join_pairs(self) -> List[tuple]:
        out = []
        for j in self.joins:
            if ">" not in j:
                continue
            parent, child = j.split(">", 1)
            out.append((parent.strip(), child.strip()))
        return out

    def validate(self) -> List[str]:
        problems = []
        if not self.id:
            problems.append("id is required")
        if self.tier not in TIERS:
            problems.append(f"{self.id}: tier {self.tier!r} not in {TIERS}")
        if self.status not in STATUSES:
            problems.append(
                f"{self.id}: status {self.status!r} not in {STATUSES}")
        if self.rights not in RIGHTS:
            problems.append(
                f"{self.id}: rights {self.rights!r} not in {RIGHTS}")
        if self.status == "archived" and not self.sha256:
            problems.append(f"{self.id}: archived but has no sha256")
        if self.status == "unavailable" and not self.notes:
            problems.append(
                f"{self.id}: unavailable must say why, in notes")
        if not self.repository:
            problems.append(
                f"{self.id}: repository is required — 'Ancestry' is an access "
                f"point, not a repository")
        if not self.retrieved and self.status == "archived":
            problems.append(f"{self.id}: archived but no retrieval date")
        if self.join_tier not in JOIN_TIERS:
            problems.append(
                f"{self.id}: join_tier {self.join_tier!r} not in {JOIN_TIERS}")
        for j in self.joins:
            if ">" not in j:
                problems.append(
                    f"{self.id}: join {j!r} is not 'PARENT>CHILD'")
        if self.joins and not self.join_tier:
            problems.append(
                f"{self.id}: names a join but no join_tier. A document's tier "
                f"and its strength FOR THE JOIN are different questions — a "
                f"death certificate is primary and its parent fields are "
                f"secondary.")
        if _TIER_RANK.get(self.join_tier, 0) > _TIER_RANK.get(self.tier, 0):
            problems.append(
                f"{self.id}: join_tier {self.join_tier!r} is stronger than "
                f"tier {self.tier!r}. A document cannot be better evidence of "
                f"a relationship than it is a record.")
        return problems

    @property
    def primary_for_join(self) -> bool:
        return self.status == "archived" and self.join_tier == "primary"

    @property
    def publishable(self) -> bool:
        """May a shared family site display this file?"""
        return self.rights in PUBLISHABLE

    def path(self, root: str) -> str:
        """Content-addressed path: documents/ab/abcdef...ext"""
        if not self.sha256:
            return ""
        ext = os.path.splitext(self.filename)[1].lower() or ".bin"
        return os.path.join(root, "documents", self.sha256[:2],
                            self.sha256 + ext)


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


_EXT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".tif": "image/tiff", ".tiff": "image/tiff", ".pdf": "application/pdf",
    ".gif": "image/gif", ".webp": "image/webp", ".txt": "text/plain",
}


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------


class Manifest:
    """The list of everything, archived or merely wanted."""

    def __init__(self, root: str, documents: Optional[List[Document]] = None):
        self.root = root
        self.documents: List[Document] = documents or []

    # -- io -------------------------------------------------------------
    @property
    def path(self) -> str:
        return os.path.join(self.root, "manifest.yaml")

    @classmethod
    def load(cls, root: str) -> "Manifest":
        """`root` is the archive DIRECTORY, not the manifest file inside it.

        ⚠️ This method used to accept anything at all. Given
        ``evidence/manifest.yaml`` — the file rather than the directory — it
        looked for ``evidence/manifest.yaml/manifest.yaml``, did not find it,
        and returned an EMPTY manifest. ``evidence verify`` then printed
        "archive is INTACT" and exited 0 while checking ZERO documents. Every
        session prompt in this project lists "evidence verify INTACT" as a
        pass condition, so the bug let that check pass while verifying
        nothing — a false positive, which is exactly the failure mode this
        archive exists to refuse. Reproduced live 2026-08-31; fixed the same
        day (Part E, [[12 Tech Reduction Roadmap]] item 6).

        A path that does not exist is still allowed to yield an empty
        manifest, because that is how a NEW archive is created: `evidence add`
        loads first and `save()` does the `makedirs`. A path that exists and
        is *not a directory* is never legitimate, so it raises.
        """
        if yaml is None:
            raise RuntimeError("PyYAML is required for the evidence manifest")
        if os.path.exists(root) and not os.path.isdir(root):
            hint = ""
            if os.path.basename(root) == "manifest.yaml":
                hint = (" — that is the manifest FILE; pass the directory that"
                        " contains it, e.g. --evidence "
                        + (os.path.dirname(root) or "evidence"))
            raise EvidenceError(
                "evidence root is not a directory: " + root + hint)
        p = os.path.join(root, "manifest.yaml")
        if not os.path.exists(p):
            return cls(root)
        with open(p, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        docs = [Document(**d) for d in (raw.get("documents") or [])]
        return cls(root, docs)

    def save(self) -> None:
        os.makedirs(self.root, exist_ok=True)
        payload = {
            "version": 1,
            "documents": [
                {k: v for k, v in asdict(d).items()
                 if v not in ("", [], 0)}
                for d in sorted(self.documents, key=lambda d: d.id)
            ],
        }
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(
                "# evidence/manifest.yaml — the archive index.\n"
                "#\n"
                "# The files under documents/ are named by their SHA-256; this\n"
                "# file is what makes them evidence rather than pictures.\n"
                "# Add entries with `treetools evidence add`, never by hand-\n"
                "# copying files in, or the hashes will not match.\n"
                "#\n"
                "# `free_source` is the most valuable field: it is how you get\n"
                "# the record again without paying for it.\n\n"
            )
            yaml.safe_dump(payload, fh, sort_keys=False, allow_unicode=True,
                           width=100)

    # -- queries --------------------------------------------------------
    def by_id(self, doc_id: str) -> Optional[Document]:
        return next((d for d in self.documents if d.id == doc_id), None)

    def by_person(self, xref: str) -> List[Document]:
        return [d for d in self.documents if xref in d.people]

    def for_join(self, parent: str, child: str) -> List[Document]:
        """Every document naming this specific parent-child relationship."""
        return [d for d in self.documents
                if (parent, child) in d.join_pairs()]

    def join_evidence(self) -> Dict[tuple, str]:
        """{(parent, child): best join_tier} across archived documents.

        This is what makes "joins with a primary record" a number rather than
        an impression. On 2026-08-26 it is zero, and that is the single most
        important fact about this tree's state.
        """
        best: Dict[tuple, str] = {}
        for d in self.documents:
            if d.status != "archived" or not d.join_tier:
                continue
            for pair in d.join_pairs():
                if _TIER_RANK[d.join_tier] > _TIER_RANK.get(best.get(pair, ""),
                                                            0):
                    best[pair] = d.join_tier
        return best

    def primary_joins(self) -> List[tuple]:
        return sorted(k for k, v in self.join_evidence().items()
                      if v == "primary")

    def validate(self, gedcom=None) -> List[str]:
        """Check the manifest. Pass a Gedcom to also check person links.

        Without the GEDCOM this cannot tell a real xref from a typo, and a
        document silently attached to the wrong person is exactly the kind
        of quiet corruption this project exists to avoid. Two wrong links
        got in on 2026-08-25 and validated clean, which is why this
        argument exists.
        """
        problems: List[str] = []
        seen = set()
        if gedcom is not None:
            for d in self.documents:
                for x in d.people:
                    if x not in gedcom.individuals:
                        problems.append(
                            f"{d.id}: person {x} is not in this GEDCOM")
                for parent, child in d.join_pairs():
                    for x in (parent, child):
                        if x not in gedcom.individuals:
                            problems.append(
                                f"{d.id}: join names {x}, which is not in "
                                f"this GEDCOM")
        for d in self.documents:
            problems.extend(d.validate())
            if d.id in seen:
                problems.append(f"duplicate id: {d.id}")
            seen.add(d.id)
        hashes: Dict[str, List[str]] = {}
        for d in self.documents:
            if d.sha256:
                hashes.setdefault(d.sha256, []).append(d.id)
        for h, ids in hashes.items():
            if len(ids) > 1:
                problems.append(
                    f"same file archived under {len(ids)} ids "
                    f"({', '.join(ids)}) — sha {h[:12]}")
        return problems

    # -- mutation -------------------------------------------------------
    def add_file(self, source_path: str, doc: Document,
                 move: bool = False) -> Document:
        """Hash a file, copy it into the archive, and record it."""
        if not os.path.isfile(source_path):
            raise EvidenceError(f"no such file: {source_path}")
        if self.by_id(doc.id):
            raise EvidenceError(f"id already in the manifest: {doc.id}")

        digest = sha256_file(source_path)
        doc.sha256 = digest
        doc.filename = doc.filename or os.path.basename(source_path)
        doc.bytes = os.path.getsize(source_path)
        ext = os.path.splitext(doc.filename)[1].lower()
        doc.media_type = doc.media_type or _EXT_TYPES.get(ext, "")
        doc.status = "archived"

        existing = next((d for d in self.documents if d.sha256 == digest),
                        None)
        if existing:
            raise EvidenceError(
                f"identical file already archived as {existing.id!r} "
                f"(sha {digest[:12]}). Add a cross-reference instead of a "
                f"second copy.")

        dest = doc.path(self.root)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest):
            (shutil.move if move else shutil.copy2)(source_path, dest)

        problems = doc.validate()
        if problems:
            raise EvidenceError("; ".join(problems))
        self.documents.append(doc)
        return doc

    # -- integrity ------------------------------------------------------
    def verify(self) -> Dict[str, List[str]]:
        """Re-hash every archived file. This is the anti-bitrot check."""
        report: Dict[str, List[str]] = {
            "ok": [], "missing": [], "corrupt": [], "orphan": [],
        }
        expected = set()
        for d in self.documents:
            if d.status != "archived":
                continue
            p = d.path(self.root)
            expected.add(os.path.abspath(p))
            if not os.path.exists(p):
                report["missing"].append(d.id)
                continue
            if sha256_file(p) != d.sha256:
                report["corrupt"].append(d.id)
            else:
                report["ok"].append(d.id)

        docs_dir = os.path.join(self.root, "documents")
        if os.path.isdir(docs_dir):
            for dirpath, _dirs, files in os.walk(docs_dir):
                for f in files:
                    if f.startswith("."):
                        continue
                    full = os.path.abspath(os.path.join(dirpath, f))
                    if full not in expected:
                        report["orphan"].append(
                            os.path.relpath(full, self.root))
        return report

    # -- reporting ------------------------------------------------------
    def stats(self) -> Dict[str, object]:
        archived = [d for d in self.documents if d.status == "archived"]
        joins = self.join_evidence()
        return {
            "joins_documented": len(joins),
            "joins_with_primary": sum(1 for v in joins.values()
                                      if v == "primary"),
            "total": len(self.documents),
            "archived": len(archived),
            "wanted": len([d for d in self.documents
                           if d.status == "wanted"]),
            "unavailable": len([d for d in self.documents
                                if d.status == "unavailable"]),
            "bytes": sum(d.bytes for d in archived),
            "publishable": len([d for d in archived if d.publishable]),
            "primary": len([d for d in archived if d.tier == "primary"]),
            "free_route_known": len([d for d in self.documents
                                     if d.free_source]),
            "no_free_route": len([d for d in self.documents
                                  if not d.free_source]),
        }
