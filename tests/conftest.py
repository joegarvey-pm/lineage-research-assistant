"""Shared test fixtures.

Every test in this repo runs against a small, hand-written synthetic
GEDCOM so expected values are obvious by inspection and no real family
data is needed to run the suite. Clone the repo and `pytest` passes.

The toy tree is four generations:

    Root (b.1985)  <-  Dad Root  <-  Grandpa Root  <-  Great Root
                        +- Mum Branch

Only the Dad->Grandpa join carries a citation. Great Root has a death
date before his birth date on purpose, so the audit checks have
something to catch.
"""


import pytest

from treetools import parse_string


# A four-generation toy tree.
#   Sam <- Dad <- Grandpa <- GreatGrandpa
#            \- Mum
# The Dad->Grandpa join carries a citation; nothing else does.
TOY = """0 HEAD
1 SOUR Ancestry.com Family Trees
2 _TREE Toy Tree
1 DATE 1 Jan 2026
2 TIME 12:00:00
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Sam /Root/
2 GIVN Sam
2 SURN Root
1 SEX M
1 FAMC @F1@
1 BIRT
2 DATE 7 Oct 1985
2 PLAC Rivertown, Example County, Kansas, USA
0 @I2@ INDI
1 NAME Dad /Root/
2 GIVN Dad
2 SURN Root
1 NAME Daddy /Root/
2 GIVN Daddy
2 SURN Root
1 SEX M
1 FAMS @F1@
1 FAMC @F2@
1 BIRT
2 DATE 1 Jan 1960
2 SOUR @S1@
3 PAGE Birth index
0 @I3@ INDI
1 NAME Mum /Branch/
2 GIVN Mum
2 SURN Branch
1 SEX F
1 FAMS @F1@
1 BIRT
2 DATE 1963
0 @I4@ INDI
1 NAME Grandpa /Root/
2 GIVN Grandpa
2 SURN Root
1 SEX M
1 FAMS @F2@
1 FAMC @F3@
1 BIRT
2 DATE 1930
0 @I5@ INDI
1 NAME Granny /Root/
2 GIVN Granny
2 SURN Root
1 SEX F
1 FAMS @F2@
1 BIRT
2 DATE 1932
0 @I6@ INDI
1 NAME Great /Root/
2 GIVN Great
2 SURN Root
1 SEX M
1 FAMS @F3@
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1899
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I3@
1 CHIL @I1@
0 @F2@ FAM
1 HUSB @I4@
1 WIFE @I5@
1 CHIL @I2@
1 MARR
2 DATE 1955
2 SOUR @S1@
3 PAGE Marriage record naming the join
0 @F3@ FAM
1 HUSB @I6@
1 CHIL @I4@
0 @S1@ SOUR
1 TITL A Real Collection, 1900-1950
1 AUTH Somebody
0 TRLR
"""

TOY_OVERRIDES = """
root: "@I1@"
root_name: Sam Root
defaults:
  unsourced_join: 10
  cited_join: 50
link:
  "@I2@":
    name: Dad Root
    score: 99
    basis: Direct knowledge.
  "@I3@":
    name: Mum Branch
    score: 99
    basis: Direct knowledge.
id: {}
"""


@pytest.fixture
def toy():
    return parse_string(TOY, path="<toy>")


@pytest.fixture
def toy_overrides(tmp_path):
    p = tmp_path / "overrides.yaml"
    p.write_text(TOY_OVERRIDES, encoding="utf-8")
    return str(p)
