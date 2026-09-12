"""Download M5, build the CA_1 / FOODS_3 snapshot, write MANIFEST.txt.

    python -m src.data                 download + build snapshot + manifest
    python -m src.data --cut-holdout   HUMAN ONLY: move the final 28 days into holdout/

This module never reads, prints, or moves anything under ~/.kaggle/. The Kaggle CLI is
invoked as a subprocess and handles its own credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SNAPSHOT = ROOT / "data" / "snapshot"
HOLDOUT = ROOT / "holdout"

COMPETITION = "m5-forecasting-accuracy"
STORE_ID = "CA_1"
DEPT_ID = None  # v1: all departments in the store (v0 was "FOODS_3")
HOLDOUT_DAYS = 28

SNAPSHOT_FILES = ("sales.parquet", "calendar.parquet", "prices.parquet")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(directory: Path, files: tuple[str, ...]) -> Path:
    manifest = directory / "MANIFEST.txt"
    lines = [f"{sha256(directory / name)}  {name}" for name in files]
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def verify_manifest(directory: Path = SNAPSHOT, files: tuple[str, ...] = SNAPSHOT_FILES) -> None:
    """Abort loudly if any snapshot file has drifted from its recorded hash."""
    manifest = directory / "MANIFEST.txt"
    if not manifest.exists():
        raise SystemExit(f"No manifest at {manifest}. Run `make data` first.")
    recorded = {}
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        recorded[name.strip()] = digest
    problems = []
    for name in files:
        path = directory / name
        if not path.exists():
            problems.append(f"missing: {name}")
        elif name not in recorded:
            problems.append(f"not in manifest: {name}")
        elif sha256(path) != recorded[name]:
            problems.append(f"hash mismatch: {name}")
    if problems:
        raise SystemExit("Snapshot failed manifest verification:\n  " + "\n  ".join(problems))


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if (RAW / "sales_train_validation.csv").exists():
        print(f"raw files already present in {RAW}, skipping download")
        return
    try:
        import kaggle, truststore  # noqa: F401  (presence check only)
    except ImportError:
        raise SystemExit("kaggle/truststore not installed. Run `make env` (installs the `data` extra).")
    print(f"downloading {COMPETITION} to {RAW} ...")
    # The Kaggle CLI is run in-process via the interpreter, with `truststore` injected
    # first so Python trusts the OS keychain. This machine sits behind TLS interception
    # (Zscaler); without it every HTTPS call fails CERTIFICATE_VERIFY_FAILED.
    shim = (
        "import sys, truststore; truststore.inject_into_ssl(); "
        "from kaggle.cli import main; sys.argv = ['kaggle'] + sys.argv[1:]; main()"
    )
    result = subprocess.run(
        [sys.executable, "-c", shim, "competitions", "download", "-c", COMPETITION, "-p", str(RAW)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-6:]
        raise SystemExit(
            "Kaggle download failed:\n  "
            + "\n  ".join(tail)
            + "\n\nCheck that ~/.kaggle/access_token (or legacy kaggle.json) exists with mode 600 and that the "
            f"competition rules are accepted at\n  https://www.kaggle.com/competitions/{COMPETITION}/rules"
        )
    archive = RAW / f"{COMPETITION}.zip"
    print(f"unzipping {archive.name} ...")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(RAW)


def build_snapshot() -> None:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)

    calendar = pd.read_csv(RAW / "calendar.csv", parse_dates=["date"])
    sales = pd.read_csv(RAW / "sales_train_validation.csv")
    prices = pd.read_csv(RAW / "sell_prices.csv")

    mask = sales["store_id"] == STORE_ID
    if DEPT_ID is not None:
        mask &= sales["dept_id"] == DEPT_ID
    sales = sales[mask].copy()
    if sales.empty:
        raise SystemExit(f"No rows for store {STORE_ID} / dept {DEPT_ID or 'ALL'}.")
    id_cols = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
    day_cols = [c for c in sales.columns if c.startswith("d_")]

    long = sales.melt(id_vars=id_cols, value_vars=day_cols, var_name="d", value_name="sales")
    day_to_date = calendar.set_index("d")["date"]
    long["date"] = long["d"].map(day_to_date)
    long["sales"] = long["sales"].astype("int32")
    long = long.sort_values(["id", "date"], kind="mergesort").reset_index(drop=True)

    days = sorted(long["date"].unique())
    calendar_out = calendar[calendar["date"].isin(days)].reset_index(drop=True)
    prices_out = prices[
        (prices["store_id"] == STORE_ID) & (prices["item_id"].isin(sales["item_id"].unique()))
    ].reset_index(drop=True)

    long.to_parquet(SNAPSHOT / "sales.parquet", index=False)
    calendar_out.to_parquet(SNAPSHOT / "calendar.parquet", index=False)
    prices_out.to_parquet(SNAPSHOT / "prices.parquet", index=False)
    write_manifest(SNAPSHOT, SNAPSHOT_FILES)

    print(
        f"snapshot: {long['id'].nunique()} series x {len(days)} days "
        f"({days[0].date()} .. {days[-1].date()}), {len(long):,} rows"
    )
    print(f"manifest written to {SNAPSHOT / 'MANIFEST.txt'}")
    print("NOTE: this snapshot is UNCUT. Human must run `make holdout` before any backtest.")


def snapshot_is_cut(sales: pd.DataFrame, calendar: pd.DataFrame) -> bool:
    """calendar.parquet always spans the full raw range; sales.parquet loses its final 28
    days at `make holdout`. Equal end dates therefore mean the holdout has not been cut."""
    return sales["date"].max() < calendar["date"].max()


def cut_holdout() -> None:
    """HUMAN ONLY. Move the final 28 days out of the agent-visible snapshot."""
    verify_manifest()
    HOLDOUT.mkdir(parents=True, exist_ok=True)

    sales = pd.read_parquet(SNAPSHOT / "sales.parquet")
    calendar = pd.read_parquet(SNAPSHOT / "calendar.parquet")
    if snapshot_is_cut(sales, calendar):
        raise SystemExit("snapshot is already cut (its last day precedes the calendar's). Refusing to cut twice.")
    if (HOLDOUT / "sales.parquet").exists():
        print("holdout/ from a previous snapshot exists; it will be replaced.")
    days = sorted(sales["date"].unique())
    if len(days) <= HOLDOUT_DAYS * 5:
        raise SystemExit("Snapshot too short to cut a holdout and still run four folds.")
    cut = days[-HOLDOUT_DAYS]

    held = sales[sales["date"] >= cut].reset_index(drop=True)
    visible = sales[sales["date"] < cut].reset_index(drop=True)

    held.to_parquet(HOLDOUT / "sales.parquet", index=False)
    write_manifest(HOLDOUT, ("sales.parquet",))
    visible.to_parquet(SNAPSHOT / "sales.parquet", index=False)
    write_manifest(SNAPSHOT, SNAPSHOT_FILES)

    print(f"holdout: {HOLDOUT_DAYS} days from {pd.Timestamp(cut).date()} -> holdout/sales.parquet")
    print(f"agent-visible snapshot now ends {pd.Timestamp(sorted(visible['date'].unique())[-1]).date()}")
    print("snapshot MANIFEST.txt regenerated. Commit it.")


def load_snapshot() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    verify_manifest()
    sales = pd.read_parquet(SNAPSHOT / "sales.parquet")
    calendar = pd.read_parquet(SNAPSHOT / "calendar.parquet")
    if not snapshot_is_cut(sales, calendar):
        raise SystemExit(
            "snapshot is UNCUT: its final 28 days are the future holdout. "
            "Human must run `make holdout` before any backtest."
        )
    return sales, calendar, pd.read_parquet(SNAPSHOT / "prices.parquet")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut-holdout", action="store_true", help="HUMAN ONLY")
    args = parser.parse_args(argv)
    if args.cut_holdout:
        cut_holdout()
    else:
        download()
        build_snapshot()
    return 0


if __name__ == "__main__":
    sys.exit(main())
