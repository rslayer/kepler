"""Dataset adapters: raw data -> the contract in src/contract.py.

Register a dataset id here. Each adapter exposes:
  download(), build_snapshot(), cut_holdout()   dataset-native, human-run via make targets
  SNAPSHOT_FILES, snapshot_dir, holdout_dir      for manifest verification
  load(with_holdout=False) -> Dataset            contract translation
"""

from __future__ import annotations

from . import m5

ADAPTERS = {
    "m5_ca1": m5.M5Adapter(dataset_id="m5_ca1", store_id="CA_1", dept_id=None),
    # all 10 stores, competition setup: visible d_1-d_1913, holdout = evaluation period d_1914-d_1941
    "m5_all": m5.M5Adapter(dataset_id="m5_all", store_id=None, dept_id=None, layout="wide"),
}


def get_adapter(dataset_id: str):
    if dataset_id not in ADAPTERS:
        raise SystemExit(f"unknown dataset '{dataset_id}'. Registered: {', '.join(sorted(ADAPTERS))}")
    return ADAPTERS[dataset_id]
