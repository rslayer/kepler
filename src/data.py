"""Download M5, build the CA_1 / FOODS_3 snapshot, write MANIFEST.txt.

`python -m src.data`               download + build snapshot + manifest
`python -m src.data --cut-holdout` HUMAN ONLY: move the final 28 days into holdout/

Never reads, prints, or moves ~/.kaggle/kaggle.json; the Kaggle CLI handles auth itself.

Filled in during Phase 1.
"""
