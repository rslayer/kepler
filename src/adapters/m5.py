"""M5 (Walmart) adapter: download, subset, snapshot, holdout cut, and the translation of
the M5-native snapshot into the contract.

Known-in-advance claim for exog: calendar flags (SNAP, events) are published ahead of
time. `sell_price` for horizon weeks is taken from the competition's sell_prices table,
which covers the forecast window; M5 supplies it by design and every published M5 solution
uses it. It is a mild future-information assumption, inherited by every model including
the baseline, and stated here so the adversary can rule on it.

Snapshot files stay M5-native (sales.parquet, calendar.parquet, prices.parquet) so their
hashes are stable across harness versions; the contract translation happens in load().
Nothing here reads, prints, or moves ~/.kaggle/*; the Kaggle CLI handles its own auth.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

from ..contract import Dataset

ROOT = Path(__file__).resolve().parents[2]
COMPETITION = "m5-forecasting-accuracy"
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
    manifest.write_text("\n".join(f"{sha256(directory / n)}  {n}" for n in files) + "\n")
    return manifest


def verify_manifest(directory: Path, files: tuple[str, ...]) -> None:
    manifest = directory / "MANIFEST.txt"
    if not manifest.exists():
        raise SystemExit(f"No manifest at {manifest}. Run `make data` first.")
    recorded = {}
    for line in manifest.read_text().splitlines():
        if line.strip():
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
        raise SystemExit(f"{directory} failed manifest verification:\n  " + "\n  ".join(problems))


class M5Adapter:
    def __init__(self, dataset_id: str, store_id: str, dept_id: str | None):
        self.dataset_id = dataset_id
        self.store_id = store_id
        self.dept_id = dept_id
        self.raw = ROOT / "data" / dataset_id / "raw"
        self.snapshot_dir = ROOT / "data" / dataset_id / "snapshot"
        self.holdout_dir = ROOT / "holdout" / dataset_id
        self.snapshot_files = SNAPSHOT_FILES

    # ------------------------------------------------------------------ native steps
    def download(self) -> None:
        self.raw.mkdir(parents=True, exist_ok=True)
        if (self.raw / "sales_train_validation.csv").exists():
            print(f"raw files already present in {self.raw}, skipping download")
            return
        try:
            import kaggle, truststore  # noqa: F401
        except ImportError:
            raise SystemExit("kaggle/truststore not installed. Run `make env`.")
        print(f"downloading {COMPETITION} to {self.raw} ...")
        shim = ("import sys, truststore; truststore.inject_into_ssl(); "
                "from kaggle.cli import main; sys.argv = ['kaggle'] + sys.argv[1:]; main()")
        result = subprocess.run(
            [sys.executable, "-c", shim, "competitions", "download", "-c", COMPETITION, "-p", str(self.raw)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-6:]
            raise SystemExit("Kaggle download failed:\n  " + "\n  ".join(tail)
                             + "\n\nCheck ~/.kaggle/access_token (mode 600) and that the competition rules are accepted.")
        with zipfile.ZipFile(self.raw / f"{COMPETITION}.zip") as zf:
            zf.extractall(self.raw)

    def build_snapshot(self) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        calendar = pd.read_csv(self.raw / "calendar.csv", parse_dates=["date"])
        sales = pd.read_csv(self.raw / "sales_train_validation.csv")
        prices = pd.read_csv(self.raw / "sell_prices.csv")
        mask = sales["store_id"] == self.store_id
        if self.dept_id is not None:
            mask &= sales["dept_id"] == self.dept_id
        sales = sales[mask].copy()
        if sales.empty:
            raise SystemExit(f"No rows for store {self.store_id} / dept {self.dept_id or 'ALL'}.")
        id_cols = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
        day_cols = [c for c in sales.columns if c.startswith("d_")]
        long = sales.melt(id_vars=id_cols, value_vars=day_cols, var_name="d", value_name="sales")
        long["date"] = long["d"].map(calendar.set_index("d")["date"])
        long["sales"] = long["sales"].astype("int32")
        long = long.sort_values(["id", "date"], kind="mergesort").reset_index(drop=True)
        days = sorted(long["date"].unique())
        calendar_out = calendar[calendar["date"].isin(days)].reset_index(drop=True)
        prices_out = prices[(prices["store_id"] == self.store_id)
                            & (prices["item_id"].isin(sales["item_id"].unique()))].reset_index(drop=True)
        long.to_parquet(self.snapshot_dir / "sales.parquet", index=False)
        calendar_out.to_parquet(self.snapshot_dir / "calendar.parquet", index=False)
        prices_out.to_parquet(self.snapshot_dir / "prices.parquet", index=False)
        write_manifest(self.snapshot_dir, SNAPSHOT_FILES)
        print(f"snapshot {self.dataset_id}: {long['id'].nunique()} series x {len(days)} days "
              f"({days[0].date()} .. {days[-1].date()}), {len(long):,} rows")
        print(f"manifest written to {self.snapshot_dir / 'MANIFEST.txt'}")
        print("NOTE: this snapshot is UNCUT. Human must run `make holdout` before any backtest.")

    def verify_manifest(self) -> None:
        verify_manifest(self.snapshot_dir, SNAPSHOT_FILES)

    def _native(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return (pd.read_parquet(self.snapshot_dir / "sales.parquet"),
                pd.read_parquet(self.snapshot_dir / "calendar.parquet"),
                pd.read_parquet(self.snapshot_dir / "prices.parquet"))

    @staticmethod
    def is_cut(sales: pd.DataFrame, calendar: pd.DataFrame) -> bool:
        """calendar spans the full raw range; sales loses its final 28 days at the cut."""
        return sales["date"].max() < calendar["date"].max()

    def cut_holdout(self) -> None:
        """HUMAN ONLY. Move the final 28 days out of the agent-visible snapshot."""
        self.verify_manifest()
        self.holdout_dir.mkdir(parents=True, exist_ok=True)
        sales, calendar, _ = self._native()
        if self.is_cut(sales, calendar):
            raise SystemExit("snapshot is already cut. Refusing to cut twice.")
        if (self.holdout_dir / "sales.parquet").exists():
            print("holdout from a previous snapshot exists; it will be replaced.")
        days = sorted(sales["date"].unique())
        if len(days) <= HOLDOUT_DAYS * 5:
            raise SystemExit("Snapshot too short to cut a holdout and still run the folds.")
        cut = days[-HOLDOUT_DAYS]
        held = sales[sales["date"] >= cut].reset_index(drop=True)
        visible = sales[sales["date"] < cut].reset_index(drop=True)
        held.to_parquet(self.holdout_dir / "sales.parquet", index=False)
        write_manifest(self.holdout_dir, ("sales.parquet",))
        visible.to_parquet(self.snapshot_dir / "sales.parquet", index=False)
        write_manifest(self.snapshot_dir, SNAPSHOT_FILES)
        print(f"holdout {self.dataset_id}: {HOLDOUT_DAYS} days from {pd.Timestamp(cut).date()} -> {self.holdout_dir}/sales.parquet")
        print(f"agent-visible snapshot now ends {pd.Timestamp(visible['date'].max()).date()}")
        print("snapshot MANIFEST.txt regenerated. Commit it.")

    # ------------------------------------------------------------------ contract
    def load(self, with_holdout: bool = False) -> Dataset:
        sales, calendar, prices = self._native()
        if not self.is_cut(sales, calendar):
            raise SystemExit("snapshot is UNCUT: its final 28 days are the future holdout. "
                             "Human must run `make holdout` before any backtest.")
        if with_holdout:
            verify_manifest(self.holdout_dir, ("sales.parquet",))
            sales = pd.concat([sales, pd.read_parquet(self.holdout_dir / "sales.parquet")], ignore_index=True)
            sales = sales.sort_values(["id", "date"], kind="mergesort").reset_index(drop=True)

        panel = sales[["id", "date", "sales"]].rename(columns={"id": "series_id", "sales": "y"})
        series = (sales.drop_duplicates("id")[["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]]
                  .rename(columns={"id": "series_id"}).reset_index(drop=True))

        cal = calendar.copy()
        cal["event_flag"] = (cal["event_name_1"].notna() | cal["event_name_2"].notna()).astype("int8")
        cal["snap_CA"] = cal["snap_CA"].astype("int8")
        # The store is closed on Christmas Day: sales are 0 on every 25 December in the data.
        cal["christmas"] = (cal["event_name_1"] == "Christmas").astype("int8")
        exog_date = cal.drop(columns=["d"]).reset_index(drop=True)

        # weekly prices -> one row per (series, day); days with no listed price are absent
        # (the price feature is NaN there, exactly as the v0-v2 left-merge produced).
        wk = calendar[["date", "wm_yr_wk"]]
        px = prices.merge(series[["series_id", "item_id"]], on="item_id", how="inner")
        px = px.merge(wk, on="wm_yr_wk", how="inner")
        exog_series = px[["series_id", "date", "sell_price"]].sort_values(["series_id", "date"]).reset_index(drop=True)

        roles = {
            "calendar_flags": ["snap_CA", "event_flag"],
            "price": "sell_price",
            "weight_price": "sell_price",
            "categoricals": ["item_id", "store_id"],
        }
        return Dataset(dataset_id=self.dataset_id, panel=panel, series=series, exog_date=exog_date,
                       exog_series=exog_series, roles=roles, horizon=HOLDOUT_DAYS, notes=__doc__)
