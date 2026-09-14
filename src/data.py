"""Contract-only dataset access.

    python -m src.data --dataset <id>                download + build snapshot + manifest
    python -m src.data --dataset <id> --cut-holdout  HUMAN ONLY: move the final 28 days into holdout/<id>/

Everything dataset-specific lives in src/adapters/. This module loads a dataset by id,
verifies its manifest, refuses an uncut snapshot, validates the contract, and binds the
feature layer to the dataset's roles.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import features
from .adapters import get_adapter
from .contract import Dataset, validate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = "m5_3"


def load_dataset(dataset_id: str = DEFAULT_DATASET, with_holdout: bool = False) -> Dataset:
    adapter = get_adapter(dataset_id)
    adapter.verify_manifest()
    ds = adapter.load(with_holdout=with_holdout)
    validate(ds)
    features.bind(ds)
    return ds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--cut-holdout", action="store_true", help="HUMAN ONLY")
    args = parser.parse_args(argv)
    adapter = get_adapter(args.dataset)
    if args.cut_holdout:
        adapter.cut_holdout()
    else:
        adapter.download()
        adapter.build_snapshot()
    return 0


if __name__ == "__main__":
    sys.exit(main())
