"""One-time migration of runs/runs.csv from the v0 to the v1 column layout.

v1 adds, after `fold_count`: `fold_spacing` (backfilled 28 - v0 folds were 28 days apart)
and, after each of the six logged metrics, a `<metric>_spread` column (backfilled empty:
v0 runs were single-seed, so no spread exists), and a trailing `verdict` column (Part D;
backfilled empty - pre-v1 verdicts were the researcher's, not the harness's). Idempotent: re-running is a no-op.

    python tools/migrate_runs_v1.py [path/to/runs.csv]
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
V1_PARTC_COLUMNS = V1_COLUMNS[:-1]  # layout between Part C and Part D (no verdict yet)
V0_FOLD_SPACING = "28"


def migrate(path: Path) -> None:
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        rows = list(reader)
    if header == V1_COLUMNS:
        print(f"{path}: already v1 ({len(rows)} rows), nothing to do")
        return
    if header not in (V0_COLUMNS, V1_PARTC_COLUMNS):
        raise SystemExit(f"{path}: unexpected header, refusing to migrate:\n  {header}")
    out = []
    for r in rows:
        r = dict(r)
        if header == V0_COLUMNS:
            r["fold_spacing"] = V0_FOLD_SPACING
            for m in METRICS:
                r[f"{m}_spread"] = ""
        r.setdefault("verdict", "")
        out.append({k: r.get(k, "") for k in V1_COLUMNS})
    backup = path.with_suffix(".v0.bak" if header == V0_COLUMNS else ".partc.bak")
    backup.write_bytes(path.read_bytes())
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=V1_COLUMNS)
        w.writeheader()
        w.writerows(out)
    print(f"{path}: migrated {len(out)} rows to v1 (backup at {backup.name})")


if __name__ == "__main__":
    migrate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs" / "runs.csv")
