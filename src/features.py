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
