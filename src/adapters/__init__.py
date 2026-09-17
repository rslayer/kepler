"""Dataset adapters: raw data -> the contract in src/contract.py.

Register a dataset id here. Each adapter exposes:
  download(), build_snapshot(), cut_holdout()   dataset-native, human-run via make targets
  SNAPSHOT_FILES, snapshot_dir, holdout_dir      for manifest verification
  load(with_holdout=False) -> Dataset            contract translation
"""

from __future__ import annotations

from . import m5

ADAPTERS = {
    # screening tier. Budget 60 min: v1 sized 20 min for a 300-tree baseline; the v4 recipe
    # champion (early-stopped, up to 3000 rounds) needs ~20-40 min with JOBS=3 on this laptop.
    "m5_ca1": m5.M5Adapter(dataset_id="m5_ca1", store_id="CA_1", dept_id=None, timeout_minutes=60),
    # all 10 stores, competition setup: visible d_1-d_1913, holdout = evaluation period d_1914-d_1941
    "m5_all": m5.M5Adapter(dataset_id="m5_all", store_id=None, dept_id=None, layout="wide", timeout_minutes=180),
    # hierarchical screening tier: one store per state, all 12 levels, competition setup
    "m5_3": m5.M5Adapter(dataset_id="m5_3", store_id=None, dept_id=None, layout="wide", timeout_minutes=150,
                         store_ids=["CA_1", "TX_1", "WI_1"]),  # 120 min: a bagged recipe is ~90 min here
    # v8 screen: ALL 10 stores + all states/cats (non-degenerate hierarchy, unlike m5_3) but a
    # 1/3 item sample for speed; the trustworthy fast screen (validated to match m5_all verdicts).
    "m5_screen": m5.M5Adapter(dataset_id="m5_screen", store_id=None, dept_id=None, layout="wide",
                              timeout_minutes=150, item_frac=1/3, item_seed=0),
}


def get_adapter(dataset_id: str):
    if dataset_id not in ADAPTERS:
        raise SystemExit(f"unknown dataset '{dataset_id}'. Registered: {', '.join(sorted(ADAPTERS))}")
    return ADAPTERS[dataset_id]
