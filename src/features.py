"""Feature construction. The researcher edits this file.

LEAK-FREE CONTRACT
------------------
Every builder receives the fold `origin` explicitly. `origin` is the FIRST forecast date.
Only data strictly before `origin` may enter a feature derived from the target.

The design that makes this true by construction is "as-of-origin" features: all
sales-derived features (lags, rolling means) are evaluated once, at the origin, and are
constant across the 28-day horizon. Nothing is recomputed inside the horizon, so there
is no path by which a horizon-day value can reach a feature. Horizon-varying features
are restricted to quantities genuinely known in advance: calendar flags, price, and the
horizon index itself.

Training rows are built the same way from SIMULATED origins strictly before the fold
origin, so train and predict see identically-shaped features. This is a direct
multi-horizon setup: no recursion, no error feedback.

DATA CONTRACT (v3)
------------------
This file reads only contract tables (src/contract.py) and roles; it never names a
dataset's columns. `bind(dataset)` resolves the roles into the module-level lists below
(FEATURE_COLUMNS, CATEGORICAL_COLUMNS, CALENDAR_FLAGS, PRICE_COLUMN) once per process,
so models can keep referring to FEATURE_COLUMNS by name. The feature names in the frame
are the dataset's own column names (whatever the adapter's roles resolve to), which keeps
configs and their hashes stable across harness versions.

KNOWN ASSUMPTION: the price feature for horizon days is whatever the adapter's exog_series
table says; the adapter documents why that is known in advance. For M5 it is the
competition's published price table, a mild future-information assumption inherited by every
model including the baseline. Flag it, do not silently "fix" it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contract import Dataset

LAGS = (7, 14, 28)
ROLL_WINDOWS = (7, 28)
TARGET_LAGS = (7, 14, 21, 28, 35)  # recipe ingredient 3; NaN where not yet observed at the origin
HORIZON = 28
MIN_HISTORY = max(max(LAGS), max(ROLL_WINDOWS))

# Resolved by bind(); defaults describe the baseline's shape with no dataset bound.
CALENDAR_FLAGS: list[str] = []
PRICE_COLUMN: str = "price"
CATEGORICAL_COLUMNS: list[str] = []
FEATURE_COLUMNS: list[str] = []
_BOUND: str | None = None


def _feature_columns(flags: list[str], price: str, categoricals: list[str]) -> list[str]:
    return [
        "horizon", "dow", "month",
        *flags,
        price,
        *[f"lag_{k}" for k in LAGS],
        *[f"roll_mean_{w}" for w in ROLL_WINDOWS],
        *categoricals,
    ]


def bind(ds: Dataset) -> None:
    """Resolve the dataset's roles into the module-level feature lists."""
    global PRICE_COLUMN, _BOUND
    if _BOUND is not None and _BOUND != ds.dataset_id:
        raise RuntimeError(f"features already bound to {_BOUND}; one dataset per process")
    # in-place so names imported elsewhere (`from .features import FEATURE_COLUMNS`) stay live
    CALENDAR_FLAGS[:] = list(ds.roles["calendar_flags"])
    PRICE_COLUMN = ds.roles["price"]
    CATEGORICAL_COLUMNS[:] = list(ds.roles["categoricals"])
    FEATURE_COLUMNS[:] = _feature_columns(CALENDAR_FLAGS, PRICE_COLUMN, CATEGORICAL_COLUMNS)
    _BOUND = ds.dataset_id


class Panel:
    """Dense (series x date) view of a Dataset, plus calendar and price lookups.

    values        float32 (n_series, n_days) target
    ids           series ids, row order of `values`
    dates         DatetimeIndex, column order of `values`
    attrs         dict: series attribute column -> array aligned with ids
    calendar      frame indexed by date: dow, month, every exog_date column
    price_matrix  float32 (n_series, n_days) price, NaN where the dataset lists none
    """

    def __init__(self, ds: Dataset):
        if _BOUND != ds.dataset_id:
            bind(ds)
        wide = ds.panel.pivot(index="series_id", columns="date", values="y")
        self.dates = pd.DatetimeIndex(sorted(wide.columns))
        wide = wide[self.dates]
        self.ids = wide.index.to_numpy()
        self.values = wide.to_numpy(dtype=np.float32)
        self._pos = {ts: i for i, ts in enumerate(self.dates)}

        meta = ds.series.set_index("series_id").loc[self.ids]
        self.attrs = {c: meta[c].to_numpy() for c in meta.columns}

        cal = ds.exog_date.copy()
        cal["dow"] = cal["date"].dt.dayofweek.astype("int16")
        cal["month"] = cal["date"].dt.month.astype("int16")
        self.calendar = cal.set_index("date")
        # Numeric calendar columns available to experiments by name (merged into every
        # frame; the baseline's FEATURE_COLUMNS decide what a model actually consumes).
        self.flag_columns = [
            c for c in self.calendar.columns
            if c not in ("dow", "month") and pd.api.types.is_numeric_dtype(self.calendar[c])
        ]

        # Exog (calendar, price) may extend past the panel: that is what a forecast as of
        # the day after the snapshot needs. exog dates must be daily-contiguous from the
        # panel's first day so a column index means the same date in both matrices.
        self.exog_dates = pd.DatetimeIndex(sorted(ds.exog_date["date"].unique()))
        if self.exog_dates[0] != self.dates[0] or (
            (self.exog_dates[1:] - self.exog_dates[:-1]) != pd.Timedelta(days=1)
        ).any():
            raise ValueError("exog_date must be daily-contiguous and start on the panel's first day")
        pm = getattr(ds, "price_matrix", None)
        if pm is not None and list(getattr(ds, "price_matrix_dates", [])) == list(self.exog_dates) \
                and list(ds.series["series_id"]) == list(self.ids):
            self.price_matrix = np.asarray(pm, dtype=np.float32)  # adapter fast path
        else:
            px = ds.exog_series.pivot(index="series_id", columns="date", values=PRICE_COLUMN)
            px = px.reindex(index=self.ids, columns=self.exog_dates)
            self.price_matrix = px.to_numpy(dtype=np.float32)
        self.price_column = PRICE_COLUMN
        # other per-(series, date) exog columns as matrices (recipe ingredient 6: snap_own)
        self.sd_matrices: dict[str, np.ndarray] = {}
        fast = getattr(ds, "series_date_matrices", None) or {}
        for col in ds.roles.get("series_flags", []):
            if col in fast:
                self.sd_matrices[col] = np.asarray(fast[col])
            else:
                mx = ds.exog_series.pivot(index="series_id", columns="date", values=col)
                self.sd_matrices[col] = mx.reindex(index=self.ids, columns=self.exog_dates).to_numpy(dtype=np.float32)
        # price group (recipe ingredient 5): attribute column for relative-price features
        self.price_group = ds.roles.get("price_group")

    def pos(self, date: pd.Timestamp) -> int:
        """Column index of `date`. The day after the last panel day is allowed as an
        origin (it has no target column, but every as-of feature reads before it)."""
        ts = pd.Timestamp(date)
        if ts in self._pos:
            return self._pos[ts]
        if ts == self.dates[-1] + pd.Timedelta(days=1):
            return len(self.dates)
        raise KeyError(f"{ts.date()} is not in the snapshot")

    @property
    def last_date(self) -> pd.Timestamp:
        return self.dates[-1]


def asof_features(panel: Panel, origin_pos: int) -> dict[str, np.ndarray]:
    """Sales-derived features evaluated at the origin. Reads only columns < origin_pos."""
    if origin_pos < MIN_HISTORY:
        raise ValueError(f"origin needs at least {MIN_HISTORY} days of history before it")
    out: dict[str, np.ndarray] = {}
    for k in LAGS:
        src = origin_pos - k
        assert src < origin_pos, "lag would read at or after the origin"
        out[f"lag_{k}"] = panel.values[:, src]
    for w in ROLL_WINDOWS:
        lo, hi = origin_pos - w, origin_pos
        assert hi <= origin_pos, "rolling window would read at or after the origin"
        out[f"roll_mean_{w}"] = panel.values[:, lo:hi].mean(axis=1)
    # --- recipe extras (SPEC_v4 Part C); computed for every frame, consumed only by models
    #     that list them. All windows end strictly before the origin.
    # Ingredient 2: level growth = last-28-day mean / last-365-day mean (the level shift
    # between the training window and the forecast window that Tweedie under-forecasts).
    lo365 = max(origin_pos - 365, 0)
    m28 = panel.values[:, origin_pos - 28:origin_pos].mean(axis=1)
    m365 = panel.values[:, lo365:origin_pos].mean(axis=1)
    out["level_ratio_28_365"] = np.where(m365 > 0, m28 / np.maximum(m365, 1e-9), 1.0).astype(np.float32)
    # Ingredient 4: rolling statistics at the origin and intermittency state.
    hist = panel.values[:, :origin_pos]
    for w in (14, 56, 180):
        out[f"roll_mean_{w}"] = hist[:, max(origin_pos - w, 0):].mean(axis=1)
    for w in (7, 14, 28, 56, 180):
        win = hist[:, max(origin_pos - w, 0):]
        out[f"roll_std_{w}"] = win.std(axis=1)
        out[f"roll_max_{w}"] = win.max(axis=1)
    nz = hist > 0
    any_sale = nz.any(axis=1)
    first_idx = np.where(any_sale, np.argmax(nz, axis=1), origin_pos)
    last_idx = np.where(any_sale, origin_pos - 1 - np.argmax(nz[:, ::-1], axis=1), -1)
    out["days_since_first_sale"] = np.minimum(origin_pos - first_idx, 2000).astype(np.float32)
    out["days_since_last_sale"] = np.where(last_idx >= 0, origin_pos - last_idx, 2000).astype(np.float32)
    # zero-run length ending at origin-1 (0 if the last day had a sale)
    out["zero_run_length"] = np.where(last_idx >= 0, origin_pos - 1 - last_idx, origin_pos).astype(np.float32)
    return out


def build_frame(
    panel: Panel,
    origin: pd.Timestamp,
    horizon: int = HORIZON,
    with_target: bool = False,
) -> pd.DataFrame:
    """One (series x horizon) feature frame for a single origin.

    `origin` is the first forecast date. If `with_target`, the actual target for the
    window is attached as `y`; only valid when the window lies inside the snapshot.
    """
    origin_pos = panel.pos(origin)
    n_series = panel.values.shape[0]
    dates = pd.DatetimeIndex([pd.Timestamp(origin) + pd.Timedelta(days=h) for h in range(horizon)])
    cols = [origin_pos + h for h in range(horizon)]

    asof = asof_features(panel, origin_pos)
    frame = pd.DataFrame(
        {
            "id": np.repeat(panel.ids, horizon),
            **{c: np.repeat(panel.attrs[c], horizon) for c in CATEGORICAL_COLUMNS},
            "date": np.tile(dates.to_numpy(), n_series),
            "horizon": np.tile(np.arange(1, horizon + 1, dtype="int16"), n_series),
        }
    )
    for name, values in asof.items():
        frame[name] = np.repeat(values, horizon)

    cal_cols = ["dow", "month", *panel.flag_columns]
    frame = frame.merge(panel.calendar[cal_cols], left_on="date", right_index=True, how="left")

    if cols[-1] >= panel.price_matrix.shape[1]:
        raise ValueError("horizon runs past the snapshot's price coverage")
    frame[PRICE_COLUMN] = panel.price_matrix[:, cols].reshape(-1)

    # --- recipe ingredient 3: target-relative lags. For horizon day h (1-based) and lag k
    #     the source column is origin_pos + h - 1 - k, which is strictly before the origin
    #     iff k >= h; otherwise the value is NaN (unavailable at the origin). Every read is
    #     asserted < origin_pos.
    # --- recipe ingredient 5: price context (all from the price matrix; prices are
    #     known-in-advance by the adapter's claim, the same assumption as the baseline)
    pm = panel.price_matrix
    hist_max = np.nanmax(np.where(np.isnan(pm[:, :origin_pos]), -np.inf, pm[:, :origin_pos]), axis=1)
    hist_max = np.where(np.isfinite(hist_max), hist_max, np.nan)
    p_t = pm[:, cols]                                             # target-day price
    p_prev = pm[:, [max(c - 7, 0) for c in cols]]                 # price one week before the target day
    frame["price_rel_max"] = (p_t / hist_max[:, None]).reshape(-1)
    frame["price_momentum"] = (p_t / p_prev).reshape(-1)
    frame["on_promo"] = (p_t < 0.95 * hist_max[:, None]).astype(np.float32).reshape(-1)
    if panel.price_group:
        grp = panel.attrs[panel.price_group]
        gdf = pd.DataFrame(p_t, index=grp)
        gmean = gdf.groupby(level=0).transform("mean").to_numpy(dtype=np.float32)
        frame["price_rel_group"] = (p_t / gmean).reshape(-1)
        promo = pd.DataFrame((p_t < 0.95 * hist_max[:, None]).astype(np.float32), index=grp)
        frame["group_promo_share"] = promo.groupby(level=0).transform("mean").to_numpy(dtype=np.float32).reshape(-1)
    # --- recipe ingredient 6: calendar detail known in advance
    for col, mx in panel.sd_matrices.items():
        frame[col] = mx[:, cols].reshape(-1)
    cal_flags = panel.calendar["event_flag"].reindex(panel.exog_dates).fillna(0).to_numpy(dtype=np.float32) if "event_flag" in panel.calendar.columns else None
    if cal_flags is not None:
        for off in (-3, -2, -1, 1, 2, 3):
            idx = np.clip(np.array(cols) + off, 0, len(cal_flags) - 1)
            frame[f"event_{'lead' if off < 0 else 'lag'}{abs(off)}"] = np.tile(cal_flags[idx], n_series)
    frame["day_of_month"] = frame["date"].dt.day.astype("int16")
    frame["week_of_year"] = frame["date"].dt.isocalendar().week.astype("int16").to_numpy()

    for k in TARGET_LAGS:
        col = np.full((n_series, horizon), np.nan, dtype=np.float32)
        for h in range(1, horizon + 1):
            src = origin_pos + h - 1 - k
            if k >= h and src >= 0:
                assert src < origin_pos, "target-relative lag would read at or after the origin"
                col[:, h - 1] = panel.values[:, src]
        frame[f"tlag_{k}"] = col.reshape(-1)

    if with_target:
        end_pos = origin_pos + horizon
        if end_pos > panel.values.shape[1]:
            raise ValueError("target window runs past the end of the snapshot")
        frame["y"] = panel.values[:, origin_pos:end_pos].reshape(-1)

    for col in CATEGORICAL_COLUMNS:
        frame[col] = frame[col].astype("category")
    return frame


def training_origins(
    panel: Panel,
    fold_origin: pd.Timestamp,
    n_origins: int = 40,
    spacing_days: int = 7,
    horizon: int = HORIZON,
) -> list[pd.Timestamp]:
    """Simulated origins strictly before `fold_origin`, newest first.

    The newest usable origin is `fold_origin - horizon` days: its whole 28-day target
    window must close before the fold origin, or the training target would overlap the
    evaluation window.
    """
    latest = pd.Timestamp(fold_origin) - pd.Timedelta(days=horizon)
    origins = []
    for i in range(n_origins):
        candidate = latest - pd.Timedelta(days=i * spacing_days)
        if panel.pos(candidate) < MIN_HISTORY:
            break
        assert candidate + pd.Timedelta(days=horizon - 1) < pd.Timestamp(fold_origin)
        origins.append(candidate)
    if not origins:
        raise ValueError(f"no usable training origins before {fold_origin}")
    return origins


def build_training_set(
    panel: Panel,
    fold_origin: pd.Timestamp,
    n_origins: int = 40,
    spacing_days: int = 7,
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """Stack feature frames over simulated origins to form the training matrix."""
    origins = training_origins(panel, fold_origin, n_origins, spacing_days, horizon)
    frames = [build_frame(panel, o, horizon, with_target=True) for o in origins]
    out = pd.concat(frames, ignore_index=True)
    for col in CATEGORICAL_COLUMNS:
        out[col] = out[col].astype("category")
    return out
