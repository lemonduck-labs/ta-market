# This public copy

The working repository is private. This copy holds the code, the agent team, the docs, the
synthetic caseload and the published MHCLG statistics the market picture is built from. It
leaves out, on purpose:

- **The council-by-council comparison tables** (`data/processed/picture_councils_*.csv`), which
  set every council's name beside its ratio to its peers. Nothing shared names a council in a
  comparison (`docs/adr/0001`): the published market picture shows two unnamed example councils
  against unnamed peers (`docs/adr/0006`).
- **The continuous-integration workflow.**
- **The deny list** of names the screen blocks, which never goes into git anywhere.

The scripts can recompute council-by-council comparisons from MHCLG's published tables, which
anyone can download: `scripts/build_picture.py` writes them to `data/processed/picture_councils_*.csv`
and its named outputs to `data/private/` and `reports/private/`, all of which this copy's
`.gitignore` keeps out of git. This copy publishes none.

Paths in the docs to the files above point to the private repository. The tests that need the
private council packs skip themselves here. Every household in the planner is synthetic: none is
or describes a real person.
