"""Command line interface.

Every command takes a GEDCOM path and (where it matters) an overrides path,
so nothing here assumes a particular directory layout or a particular
family. Defaults point at `my-research/` because that is what the setup
skill creates, but all of them can be overridden.

    treetools summary    --gedcom tree.ged
    treetools score      --gedcom tree.ged --overrides my-research/overrides.yaml
    treetools frontier   --gedcom tree.ged --overrides my-research/overrides.yaml
    treetools treemap    --gedcom tree.ged --overrides ... --format mermaid
    treetools audit      --gedcom tree.ged
    treetools provenance --gedcom tree.ged
    treetools diff       --gedcom new.ged --previous old.ged
    treetools archives   --place "Example County, Kansas" --year 1900
    treetools evidence   status|verify|add ...

Your agent runs these for you. You should not have to memorise any of it.
"""

import argparse
import os
import sys
from typing import Optional

from .parse import parse_file
from .pedigree import Pedigree, find_root
from .score import load_overrides, score_tree

DEFAULT_OVERRIDES = os.environ.get("TREETOOLS_OVERRIDES",
                                   "my-research/overrides.yaml")
DEFAULT_EVIDENCE = os.environ.get("TREETOOLS_EVIDENCE", "my-research/evidence")


# --------------------------------------------------------------------------
# shared loading
# --------------------------------------------------------------------------

def _load(args, need_scores: bool = True):
    """GEDCOM + overrides -> (gedcom, overrides, pedigree, scores).

    Overrides are optional on purpose: somebody opening their tree for the
    first time has not written any judgements yet, and every command that
    only needs structure should still work for them.
    """
    gedcom = parse_file(args.gedcom)
    overrides = None
    path = getattr(args, "overrides", None)
    if path and os.path.exists(path):
        overrides = load_overrides(path)

    if overrides is not None and overrides.root:
        root = overrides.root
    else:
        hint = getattr(args, "root", None)
        root = find_root(gedcom, hint) if hint else None
        if root is None:
            raise SystemExit(
                "No root person set.\n"
                "  Either add `root: \"@I1@\"` to your overrides file, or\n"
                "  pass --root \"<name>\" to pick one by name.")

    pedigree = Pedigree(gedcom, root)
    scores = None
    if need_scores and overrides is not None:
        scores = score_tree(gedcom, pedigree, overrides, strict=False)
    return gedcom, overrides, pedigree, scores


def _require_scores(scores) -> None:
    if scores is None:
        raise SystemExit(
            "This command needs an overrides file to score against.\n"
            "  Run the setup skill, or pass --overrides <path>.")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_summary(args) -> int:
    gedcom, overrides, pedigree, scores = _load(args, need_scores=False)
    people = len(gedcom.individuals)
    cited = sum(1 for i in gedcom.individuals.values()
                if getattr(i, "citations", None))
    print(f"file                  : {args.gedcom}")
    print(f"people                : {people}")
    print(f"direct ancestors      : {len(pedigree)}")
    print(f"with any citation     : {cited} ({100 * cited / people:.0f}%)"
          if people else "")
    if people and cited / people < 0.25:
        print()
        print("  Most of this tree has no source behind it. That is normal "
              "for a tree grown from hints, and it is the thing this kit "
              "exists to fix -- one join at a time, starting with the "
              "shallowest weak one.")
    return 0


def cmd_score(args) -> int:
    gedcom, overrides, pedigree, scores = _load(args)
    _require_scores(scores)
    rows = sorted((s for s in scores.values() if s.is_ancestor),
                  key=lambda s: (s.ahnentafel or 0))
    print(f"{'Ahn':>5}  {'Gen':>3}  {'LINK':>5}  {'CHAIN':>5}  Person")
    for s in rows:
        chain = "--" if s.chain is None else f"{s.chain}%"
        print(f"{s.ahnentafel or '':>5}  {s.generation:>3}  "
              f"{str(s.link) + '%':>5}  {chain:>5}  {s.name}")
    return 0


def cmd_frontier(args) -> int:
    """The shallowest weak join -- where work actually pays off."""
    gedcom, overrides, pedigree, scores = _load(args)
    _require_scores(scores)
    weak = [s for s in scores.values()
            if s.is_ancestor and s.generation is not None
            and s.ahnentafel != 1
            and s.chain is not None and s.chain < 75]
    if not weak:
        print("Every join on the direct line is documented to 75% or better.")
        print("The frontier is wherever the tree currently ends.")
        return 0
    weak.sort(key=lambda s: (s.generation, s.chain))
    print("The frontier -- work here first:")
    print()
    for s in weak[:8]:
        print(f"  gen {s.generation}  CHAIN {s.chain:>3}%  {s.name}")
    print()
    top = weak[0]
    print(f"Start with {top.name} (generation {top.generation}, "
          f"CHAIN {top.chain}%).")
    print("Everything above this person is capped by this number, so depth "
          "up there cannot exceed it.")
    return 0


def cmd_treemap(args) -> int:
    from . import treemap
    gedcom, overrides, pedigree, scores = _load(args)
    _require_scores(scores)
    out = treemap.render(gedcom, pedigree, scores,
                         fmt=args.format, generations=args.generations)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


#: Severities in the order a human should read them: things that cannot be
#: true, then things that probably aren't, then tidiness.
_SEVERITIES = (
    ("impossible", "IMPOSSIBLE — these cannot be true as recorded"),
    ("implausible", "IMPLAUSIBLE — worth a second look"),
    ("hygiene", "HYGIENE — tidiness, usually from an import"),
)


def cmd_audit(args) -> int:
    from .audit import run_audit
    gedcom = parse_file(args.gedcom)
    result = run_audit(gedcom)

    if not len(result):
        print("No flags. Either the tree is clean or it is very small.")
        return 0

    for severity, heading in _SEVERITIES:
        flags = result.by_severity(severity)
        if not flags:
            continue
        print(f"{heading}  ({len(flags)})")
        print("-" * len(heading))
        limit = args.limit if args.limit and args.limit > 0 else len(flags)
        for f in sorted(flags, key=lambda x: x.sort_key())[:limit]:
            print(f"  [{f.code}] {f.message}")
            if f.detail:
                print(f"      {f.detail}")
        if len(flags) > limit:
            print(f"  ... and {len(flags) - limit} more")
        print()

    print("A flag is a question, not a verdict. 'Mother aged 11' is almost "
          "always two people merged into one record, not a scandal.")
    return 0


def cmd_provenance(args) -> int:
    from .provenance import analyze, format_report
    gedcom = parse_file(args.gedcom)
    print(format_report(analyze(gedcom)))
    return 0


def cmd_diff(args) -> int:
    from .diff import diff, format_report
    new = parse_file(args.gedcom)
    old = parse_file(args.previous)
    print(format_report(diff(old, new)))
    return 0


def cmd_archives(args) -> int:
    from . import archives
    if args.place:
        ans = archives.for_place(args.place, args.year,
                                 record_type=args.record_type)
        print(archives.format_place_answer(ans))
    else:
        print(archives.format_list())
    return 0


# --- evidence -------------------------------------------------------------
# Ported from the original harness. The verify path matters more than it
# looks: a verify that checked zero documents must FAIL, not pass quietly.
# An "archive is INTACT" printed over an empty manifest is worse than no
# check at all, because it is believed.

def cmd_evidence(args) -> int:
    from .evidence import Document, EvidenceError, Manifest
    try:
        man = Manifest.load(args.evidence)
    except EvidenceError as exc:
        print(f"refused: {exc}")
        return 1

    if args.action == "status":
        st = man.stats()
        print(f"documents in manifest : {st['total']}")
        print(f"  archived            : {st['archived']} "
              f"({st['bytes'] / 1e6:.1f} MB)")
        print(f"  wanted              : {st['wanted']}")
        print(f"  primary evidence    : {st['primary']}")
        print(f"  free route known    : {st['free_route_known']}")
        print()
        print(f"joins with a document : {st['joins_documented']}")
        print(f"  of those, PRIMARY   : {st['joins_with_primary']}"
              + ("   <-- the ceiling is still 75% everywhere"
                 if not st['joins_with_primary'] else ""))
        return 0

    if args.action == "verify":
        report = man.verify()
        ok = report.get("ok", [])
        missing = report.get("missing", [])
        corrupt = report.get("corrupt", [])
        orphan = report.get("orphan", [])

        for doc_id in ok[:5]:
            print(f"       ok  {doc_id}")
        if len(ok) > 5:
            print(f"           ... and {len(ok) - 5} more")
        print(f" verified: {len(ok)}")
        print(f"  missing: {len(missing)}")
        print(f"  corrupt: {len(corrupt)}")
        print(f"   orphan: {len(orphan)}")
        for doc_id in missing:
            print(f"  MISSING  {doc_id}")
        for doc_id in corrupt:
            print(f"  CORRUPT  {doc_id}")

        # A verify that checked zero documents is a FAILURE, not a pass.
        # Printing "INTACT" over an empty manifest is worse than printing
        # nothing, because it gets believed.
        if not ok and not missing and not corrupt:
            print()
            print("*** VERIFIED NOTHING — this is a FAILURE, not a pass.")
            print("    An empty check that reports success is worse than no "
                  "check at all, because it gets believed.")
            return 1
        if missing or corrupt:
            print()
            print("*** archive is NOT intact")
            return 1
        print()
        print(f"archive is INTACT ({len(ok)} documents verified)")
        return 0

    if args.action == "add":
        if not args.file or not os.path.exists(args.file):
            print(f"refused: no such file: {args.file}")
            return 1
        doc = Document(
            id=args.id,
            title=args.title or "",
            tier=args.tier or "secondary",
            rights=args.rights or "unknown",
            repository=args.repository or "",
            collection=args.collection or "",
            entry=args.entry or "",
            free_source=args.free_source or "",
            retrieved=args.retrieved or "",
            supports=args.supports or "",
            notes=args.notes or "",
        )
        saved = man.add_file(args.file, doc, move=bool(args.move))
        man.save()
        print(f"archived {saved.id}")
        print(f"  sha256 {saved.sha256}")
        print(f"  stored {saved.stored_path}")
        return 0

    return 2


# --------------------------------------------------------------------------

def _add_tree_args(p, overrides=True, root=True):
    p.add_argument("--gedcom", required=True, help="path to your .ged export")
    if overrides:
        p.add_argument("--overrides", default=DEFAULT_OVERRIDES,
                       help="your scored judgements (default: %(default)s)")
    if root:
        p.add_argument("--root", default=None,
                       help="root person by name, if not set in overrides")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="treetools",
        description="A research harness for documented genealogy.")
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("summary", help="how big is the tree, how much is sourced")
    _add_tree_args(s, overrides=True)
    s.set_defaults(func=cmd_summary)

    s = sub.add_parser("score", help="LINK and CHAIN for every direct ancestor")
    _add_tree_args(s)
    s.set_defaults(func=cmd_score)

    s = sub.add_parser("frontier", help="the shallowest weak join")
    _add_tree_args(s)
    s.set_defaults(func=cmd_frontier)

    s = sub.add_parser("treemap", help="render the direct line")
    _add_tree_args(s)
    s.add_argument("--format", default="indent",
                   choices=["indent", "mermaid", "table"])
    s.add_argument("--generations", type=int, default=5)
    s.add_argument("--out", default=None, help="write to a file")
    s.set_defaults(func=cmd_treemap)

    s = sub.add_parser("audit", help="biological and data-hygiene flags")
    s.add_argument("--gedcom", required=True)
    s.add_argument("--limit", type=int, default=10,
                   help="max flags per severity (0 for all)")
    s.set_defaults(func=cmd_audit)

    s = sub.add_parser("provenance", help="how the media actually got here")
    s.add_argument("--gedcom", required=True)
    s.set_defaults(func=cmd_provenance)

    s = sub.add_parser("diff", help="two exports, and unsourced growth")
    s.add_argument("--gedcom", required=True, help="the newer export")
    s.add_argument("--previous", required=True, help="the older export")
    s.set_defaults(func=cmd_diff)

    s = sub.add_parser("archives", help="who holds what, and may you fetch it")
    s.add_argument("--place", default=None, help='e.g. "Logan County, Kansas"')
    s.add_argument("--year", type=int, default=None)
    s.add_argument("--record-type", dest="record_type", default=None,
                   help="probate | newspapers | census | vital | land")
    s.set_defaults(func=cmd_archives)

    s = sub.add_parser("evidence", help="the archive of records you hold")
    s.add_argument("action", choices=["status", "verify", "add"])
    s.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    s.add_argument("--gedcom", default=None)
    s.add_argument("--file", default=None)
    s.add_argument("--id", default=None)
    s.add_argument("--title", default=None)
    s.add_argument("--tier", choices=["primary", "secondary", "not-evidence"],
                   default=None)
    s.add_argument("--rights", default=None)
    s.add_argument("--repository", default=None,
                   help="who holds the ORIGINAL, not the website you used")
    s.add_argument("--collection", default=None)
    s.add_argument("--entry", default=None)
    s.add_argument("--free-source", dest="free_source", default=None)
    s.add_argument("--retrieved", default=None)
    s.add_argument("--supports", default=None)
    s.add_argument("--notes", default=None)
    s.add_argument("--move", action="store_true")
    s.set_defaults(func=cmd_evidence)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        from . import __version__
        print(__version__)
        return 0
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
