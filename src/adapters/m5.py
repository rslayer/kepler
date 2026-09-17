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
import shutil
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
    def __init__(self, dataset_id: str, store_id: str | None, dept_id: str | None, layout: str = "long",
                 timeout_minutes: int = 20, store_ids: list[str] | None = None,
                 item_frac: float | None = None, item_seed: int = 0):
        """layout="long": v0-v3 snapshot (long sales.parquet; holdout cut from the snapshot).
        layout="wide": compact wide sales.parquet (one row per series, one int16 column per
        day) and the holdout taken from sales_train_evaluation.csv's 28 extra days
        (d_1914-d_1941, the competition's evaluation period) WITHOUT cutting the visible
        snapshot - the agents see exactly what competitors saw."""
        self.dataset_id = dataset_id
        self.store_id = store_id
        self.dept_id = dept_id
        self.layout = layout
        self.timeout_minutes = timeout_minutes
        self.store_ids = store_ids  # a subset of stores (wide layout); None = store_id filter or all
        self.item_frac = item_frac  # v8 screen: keep this fraction of items (all stores) for a non-degenerate fast screen
        self.item_seed = item_seed
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
        mask = pd.Series(True, index=sales.index)
        if self.store_ids:
            mask &= sales["store_id"].isin(self.store_ids)
        if self.store_id is not None:
            mask &= sales["store_id"] == self.store_id
        if self.dept_id is not None:
            mask &= sales["dept_id"] == self.dept_id
        sales = sales[mask].copy()
        if self.item_frac is not None:
            # keep a deterministic fraction of items across ALL stores: the full store/state
            # hierarchy is preserved (unlike m5_3's one-store-per-state), only the item count
            # is thinned, for a fast screen whose aggregation structure matches m5_all.
            import numpy as _np
            items = _np.sort(sales["item_id"].unique())
            k = int(round(len(items) * self.item_frac))
            keep = set(_np.random.default_rng(self.item_seed).choice(items, size=k, replace=False))
            sales = sales[sales["item_id"].isin(keep)].copy()
        if sales.empty:
            raise SystemExit(f"No rows for store {self.store_id or 'ALL'} / dept {self.dept_id or 'ALL'}.")
        id_cols = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
        day_cols = [c for c in sales.columns if c.startswith("d_")]
        if self.layout == "wide":
            wide = sales[id_cols + day_cols].copy()
            for c in day_cols:
                wide[c] = wide[c].astype("int16")
            wide = wide.sort_values("id", kind="mergesort").reset_index(drop=True)
            wide.to_parquet(self.snapshot_dir / "sales.parquet", index=False)
            calendar.drop(columns=[]).to_parquet(self.snapshot_dir / "calendar.parquet", index=False)
            prices_out = prices[prices["item_id"].isin(sales["item_id"].unique())]
            if self.store_ids:
                prices_out = prices_out[prices_out["store_id"].isin(self.store_ids)]
            if self.store_id is not None:
                prices_out = prices_out[prices_out["store_id"] == self.store_id]
            prices_out.reset_index(drop=True).to_parquet(self.snapshot_dir / "prices.parquet", index=False)
            write_manifest(self.snapshot_dir, SNAPSHOT_FILES)
            days = calendar.set_index("d").loc[day_cols, "date"]
            print(f"snapshot {self.dataset_id} (wide): {len(wide)} series x {len(day_cols)} days "
                  f"({days.iloc[0].date()} .. {days.iloc[-1].date()})")
            print(f"manifest written to {self.snapshot_dir / 'MANIFEST.txt'}")
            print("NOTE: holdout for this layout comes from sales_train_evaluation.csv; run `make holdout`.")
            return
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
        """HUMAN ONLY. long layout: move the final 28 days out of the agent-visible snapshot.
        wide layout: write the evaluation period (d_1914-d_1941) from sales_train_evaluation
        as the holdout; the visible snapshot is untouched."""
        self.verify_manifest()
        self.holdout_dir.mkdir(parents=True, exist_ok=True)
        if self.layout == "wide":
            if (self.holdout_dir / "sales.parquet").exists():
                raise SystemExit("holdout already written. Refusing to write twice.")
            ev = pd.read_csv(self.raw / "sales_train_evaluation.csv")
            snap = pd.read_parquet(self.snapshot_dir / "sales.parquet", columns=["id", "item_id", "store_id"])
            ev["id"] = ev["id"].str.replace("_evaluation", "_validation", regex=False)
            ev = ev[ev["id"].isin(snap["id"])]
            day_cols = [c for c in ev.columns if c.startswith("d_")][-HOLDOUT_DAYS:]
            held = ev[["id"] + day_cols].sort_values("id", kind="mergesort").reset_index(drop=True)
            for c in day_cols:
                held[c] = held[c].astype("int16")
            if len(held) != len(snap):
                raise SystemExit(f"evaluation file has {len(held)} of {len(snap)} snapshot series")
            held.to_parquet(self.holdout_dir / "sales.parquet", index=False)
            write_manifest(self.holdout_dir, ("sales.parquet",))
            print(f"holdout {self.dataset_id}: {day_cols[0]}..{day_cols[-1]} ({len(held)} series) -> {self.holdout_dir}/sales.parquet")
            print("visible snapshot untouched (competition setup). Commit holdout/<id>/MANIFEST.txt is NOT tracked; nothing to commit.")
            # Quarantine the raw evaluation file: it holds the true d_1914-d_1941 answers
            # and otherwise sits readable in data/<id>/raw/, outside the only directory
            # agents are told to avoid. Move it under holdout/ (forbidden + gitignored).
            # The backtest never needs it (it uses sales_train_validation); score_holdout
            # reads the parquet just written, not this csv.
            src_eval = self.raw / "sales_train_evaluation.csv"
            if src_eval.exists():
                q = self.holdout_dir / "raw"
                q.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_eval), str(q / "sales_train_evaluation.csv"))
                print(f"quarantined sales_train_evaluation.csv -> {q}/ (held-out answers, not agent-visible)")
            return
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
    def _load_wide(self, with_holdout: bool) -> Dataset:
        import numpy as np
        wide = pd.read_parquet(self.snapshot_dir / "sales.parquet")
        calendar = pd.read_parquet(self.snapshot_dir / "calendar.parquet")
        prices = pd.read_parquet(self.snapshot_dir / "prices.parquet")
        if not (self.holdout_dir / "sales.parquet").exists():
            raise SystemExit("holdout is not written for this dataset. Human must run `make holdout` before any backtest.")
        day_cols = [c for c in wide.columns if c.startswith("d_")]
        if with_holdout:
            verify_manifest(self.holdout_dir, ("sales.parquet",))
            held = pd.read_parquet(self.holdout_dir / "sales.parquet").set_index("id").loc[wide["id"]]
            hcols = [c for c in held.columns if c.startswith("d_")]
            for c in hcols:
                wide[c] = held[c].to_numpy()
            day_cols = day_cols + hcols
        d2date = calendar.set_index("d")["date"]
        dates = pd.DatetimeIndex(d2date.loc[day_cols])
        ids = wide["id"].to_numpy()
        values = wide[day_cols].to_numpy(dtype="int16")
        n, t = values.shape
        panel = pd.DataFrame({
            "series_id": pd.Categorical(np.repeat(ids, t), categories=ids),
            "date": np.tile(dates.to_numpy(), n),
            "y": values.reshape(-1),
        })
        series = wide[["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]].rename(columns={"id": "series_id"}).reset_index(drop=True)

        cal = calendar.copy()
        cal["event_flag"] = (cal["event_name_1"].notna() | cal["event_name_2"].notna()).astype("int8")
        for st in ("CA", "TX", "WI"):
            cal[f"snap_{st}"] = cal[f"snap_{st}"].astype("int8")
        cal["christmas"] = (cal["event_name_1"] == "Christmas").astype("int8")
        exog_date = cal.drop(columns=["d"]).reset_index(drop=True)
        exog_date = exog_date[exog_date["date"] >= dates[0]].reset_index(drop=True)
        exog_dates = pd.DatetimeIndex(exog_date["date"])

        # weekly prices -> (series x exog day) matrix directly; NaN where no price listed
        wk_of_day = calendar.set_index("date").loc[exog_dates, "wm_yr_wk"].to_numpy()
        weeks = np.unique(wk_of_day); wk_pos = {w: i for i, w in enumerate(weeks)}
        key = series["store_id"] + "|" + series["item_id"]
        row_of = {k: i for i, k in enumerate(key)}
        pm_w = np.full((n, len(weeks)), np.nan, dtype="float32")
        pk = (prices["store_id"] + "|" + prices["item_id"]).map(row_of)
        pw = prices["wm_yr_wk"].map(wk_pos)
        ok = pk.notna() & pw.notna()
        pm_w[pk[ok].astype(int).to_numpy(), pw[ok].astype(int).to_numpy()] = prices.loc[ok, "sell_price"].to_numpy(dtype="float32")
        price_matrix = pm_w[:, [wk_pos[w] for w in wk_of_day]]
        # long exog_series is required by the contract; keep it lean (categorical id, float32)
        # SNAP for the series' own state as a (series x exog day) int8 matrix
        snap_cols = {"CA": "snap_CA", "TX": "snap_TX", "WI": "snap_WI"}
        snap_state = {stt: exog_date.set_index("date").loc[exog_dates, snap_cols[stt]].to_numpy(dtype="int8")
                      for stt in snap_cols}
        snap_own = np.vstack([snap_state[stt] for stt in series["state_id"]])
        exog_series = pd.DataFrame({
            "series_id": pd.Categorical(np.repeat(ids, len(exog_dates)), categories=ids),
            "date": np.tile(exog_dates.to_numpy(), n),
            "sell_price": price_matrix.reshape(-1),
            "snap_own": snap_own.reshape(-1),
        })
        # rows with no listed price are absent in the long layout; drop NaN here too
        exog_series = exog_series[exog_series["sell_price"].notna()].reset_index(drop=True)

        roles = {
            "calendar_flags": ["snap_CA", "event_flag"],  # snap for the series' own state is a v4 Part C feature
            "price": "sell_price",
            "weight_price": "sell_price",
            "categoricals": ["item_id", "store_id"],
            "partition": "store_id",  # v5 Part C: per-partition models (ingredient 7) split on this series attribute
            "hierarchy": [[], ["state_id"], ["store_id"], ["cat_id"], ["dept_id"],
                          ["state_id", "cat_id"], ["state_id", "dept_id"], ["store_id", "cat_id"],
                          ["store_id", "dept_id"], ["item_id"], ["item_id", "state_id"], ["item_id", "store_id"]],
            "price_group": "dept_id",
            "series_flags": ["snap_own"],
        }
        ds = Dataset(dataset_id=self.dataset_id, panel=panel, series=series, exog_date=exog_date,
                     exog_series=exog_series, roles=roles, horizon=HOLDOUT_DAYS, notes=__doc__,
                     timeout_minutes=self.timeout_minutes)
        ds.price_matrix = price_matrix  # optional fast path for features.Panel (aligned to series order, exog dates)
        ds.price_matrix_dates = exog_dates
        ds.series_date_matrices = {"snap_own": snap_own}  # same alignment
        return ds

    def load(self, with_holdout: bool = False) -> Dataset:
        if self.layout == "wide":
            return self._load_wide(with_holdout)
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
        # SNAP for the series' own state (recipe ingredient 6); one state in this layout
        import numpy as np
        st = series.set_index("series_id")["state_id"]
        snap_cols = {"CA": "snap_CA", "TX": "snap_TX", "WI": "snap_WI"}
        cal_idx = calendar.set_index("date")
        row_state = exog_series["series_id"].map(st).to_numpy()
        snap_own = np.zeros(len(exog_series), dtype="int8")
        for stt, col in snap_cols.items():
            mask = row_state == stt
            if mask.any():
                snap_own[mask] = cal_idx[col].reindex(exog_series.loc[mask, "date"]).fillna(0).to_numpy(dtype="int8")
        exog_series["snap_own"] = snap_own

        roles = {
            "calendar_flags": ["snap_CA", "event_flag"],
            "price": "sell_price",
            "weight_price": "sell_price",
            "categoricals": ["item_id", "store_id"],
            "partition": "store_id",  # v5 Part C: per-partition models (ingredient 7) split on this series attribute
            "price_group": "dept_id",      # recipe ingredient 5: relative price within this group
            "series_flags": ["snap_own"],  # recipe ingredient 6: per-(series, date) flags
        }
        ds = Dataset(dataset_id=self.dataset_id, panel=panel, series=series, exog_date=exog_date,
                     exog_series=exog_series, roles=roles, horizon=HOLDOUT_DAYS, notes=__doc__,
                     timeout_minutes=self.timeout_minutes)
        # dense (series x exog day) snap_own, independent of which days have a listed price
        xd = pd.DatetimeIndex(sorted(exog_date["date"].unique()))
        snap_state = {stt: cal_idx[col].reindex(xd).fillna(0).to_numpy(dtype="int8") for stt, col in snap_cols.items()}
        ds.series_date_matrices = {"snap_own": np.vstack([snap_state[stt] for stt in series["state_id"]])}
        ds.series_date_matrices_dates = xd
        return ds
