"""treetools — a local harness for documented genealogy research.

Nothing in this package talks to a genealogy service, and nothing in it
phones home. It reads a GEDCOM export off your own disk, scores every
parent-child join against the LINK/CHAIN rubric in ``CLAUDE.md``, and
regenerates your reports so they are reproducible from
``export + overrides.yaml`` rather than hand-maintained.

The design rule the whole package follows: **generated files are never
hand-edited.** If a number is wrong, the fix goes in ``overrides.yaml``
next to the reason it changed, and the report is regenerated. That is
what makes a months-long research project survive its own history.

Modules
    parse       GEDCOM 5.5.1 -> objects, keeping Ancestry's ``_`` tags
    pedigree    ancestor walk, generation + Ahnentafel + child-toward-root
    score       LINK / CHAIN, with human judgement in overrides.yaml
    audit       biological and data-hygiene flags
    provenance  _CLON / _TID / _CREA — how the media actually got here
    diff        two exports, and who gained facts without gaining sources
    evidence    content-addressed archive of the records you actually have
    archives    which archives hold what, and which allow machine access
    census      which census year to search, and where
    ia_census   locating a county on NARA microfilm at the Internet Archive
    ledger      regenerate the confidence ledger as markdown
    worklist    pre-built manual search URLs for the auth-walled sites
    newspapers  loc.gov / Chronicling America harvester
    fetcher     robots.txt policy engine — decide before you request
"""

__version__ = "0.1.0"

from .parse import parse_file, parse_string, Gedcom, Individual, Family  # noqa: F401
from .pedigree import Pedigree, find_root  # noqa: F401
from .score import load_overrides, score_tree, Overrides  # noqa: F401

__all__ = [
    "parse_file", "parse_string", "Gedcom", "Individual", "Family",
    "Pedigree", "find_root",
    "load_overrides", "score_tree", "Overrides",
]
