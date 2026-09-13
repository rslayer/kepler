"""Migration of runs/runs.csv across harness layouts (v0 -> v1 -> v2).

v1 adds, after `fold_count`: `fold_spacing` (backfilled 28 - v0 folds were 28 days apart)
and, after each of the six logged metrics, a `<metric>_spread` column (backfilled empty:
v0 runs were single-seed, so no spread exists), and a trailing `verdict` column (Part D;
backfilled empty - pre-v1 verdicts were the researcher's, not the harness's).
v2 (SPEC_v2_selfimprove.md) appends `session` and `hypothesis_id`, backfilled empty; the
v0 researcher runs' hypothesis mapping lives in hypotheses/ledger.csv.
v3 (SPEC_v3_engine.md) appends `dataset`, backfilled m5_ca1.
v4 (SPEC_v4_quality.md) appends `wrmsse_hier`, `wrmsse_hier_spread`, backfilled empty. Idempotent: re-running is a no-op.

    python tools/migrate_runs.py [path/to/runs.csv]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ["wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28"]
V0_COLUMNS = [
    "run_id", "timestamp", "git_commit", "model_name", "config_hash", "fold_count",
    *METRICS, "seconds", "status", "findings_file", "author",
]
V1_COLUMNS = [
    "run_id", "timestamp", "git_commit", "model_name", "config_hash", "fold_count", "fold_spacing",
    *METRICS, *[f"{m}_spread" for m in METRICS], "seconds", "status", "findings_file", "author",
    "verdict",
]
V1_PARTC_COLUMNS = V1_COLUMNS[:-1]  # layout between v1 Part C and Part D (no verdict yet)
V2_COLUMNS = V1_COLUMNS + ["session", "hypothesis_id"]
V3_COLUMNS = V2_COLUMNS + ["dataset"]
V4_COLUMNS = V3_COLUMNS + ["wrmsse_hier", "wrmsse_hier_spread"]
TARGET = V4_COLUMNS
V3_DEFAULT_DATASET = "m5_ca1"
KNOWN = {"v0": V0_COLUMNS, "v1-partc": V1_PARTC_COLUMNS, "v1": V1_COLUMNS, "v2": V2_COLUMNS, "v3": V3_COLUMNS, "v4": V4_COLUMNS}
V0_FOLD_SPACING = "28"


def migrate(path: Path) -> None:
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        rows = list(reader)
    layout = next((name for name, cols in KNOWN.items() if header == cols), None)
    if layout == "v4":
        print(f"{path}: already v4 ({len(rows)} rows), nothing to do")
        return
    if layout is None:
        raise SystemExit(f"{path}: unexpected header, refusing to migrate:\n  {header}")
    out = []
    for r in rows:
        r = dict(r)
        if layout == "v0":
            r["fold_spacing"] = V0_FOLD_SPACING
            for m in METRICS:
                r[f"{m}_spread"] = ""
        r.setdefault("verdict", "")
        r.setdefault("session", "")
        r.setdefault("hypothesis_id", "")
        r.setdefault("dataset", V3_DEFAULT_DATASET)
        r.setdefault("wrmsse_hier", ""); r.setdefault("wrmsse_hier_spread", "")
        out.append({k: r.get(k, "") for k in TARGET})
    backup = path.with_suffix(f".{layout}.bak")
    backup.write_bytes(path.read_bytes())
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TARGET)
        w.writeheader()
        w.writerows(out)
    print(f"{path}: migrated {len(out)} rows from {layout} to v4 (backup at {backup.name})")


if __name__ == "__main__":
    migrate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs" / "runs.csv")
