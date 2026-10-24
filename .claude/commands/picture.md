Use the market-analyst agent to rebuild the market picture:

1. `python scripts/build_from_extracts.py` (verifies every extract against data/raw/browser/MANIFEST.csv)
2. `python scripts/build_picture.py` (writes reports/phase0_picture.md and data/processed/picture_*)
3. `python -m pytest`

The report opens with what could make its numbers wrong; keep that section first. Councils far
from their peers are leads for a person to look into, never findings. Then run the review
command before showing it to anyone.
