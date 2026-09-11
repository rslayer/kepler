"""Feature construction. The researcher edits this file.

LEAK-FREE CONTRACT
------------------
Every builder receives the fold `origin` explicitly. `origin` is the FIRST forecast date.
Only data strictly before `origin` may enter a feature derived from the target.

The design that makes this true by construction is "as-of-origin" features: all
sales-derived features (lags, rolling means) are evaluated once, at the origin, and are
constant across the 28-day horizon. Nothing is recomputed inside the horizon, so there
is no path by which a horizon-day value can reach a feature. Horizon-varying features
are restricted to quantities genuinely known in advance: calendar, SNAP, events, price,
and the horizon index itself.

Training rows are built the same way from SIMULATED origins strictly before the fold
origin, so train and predict see identically-shaped features. This is a direct
multi-horizon setup: no recursion, no error feedback.

KNOWN ASSUMPTION, stated so the adversary can rule on it: `sell_price` for horizon weeks
is taken from the competition's `sell_prices` table, which covers the forecast window.
M5 supplies these by design and every published M5 solution uses them. It is still a
mild future-information assumption, and it is inherited by every model in this repo
including the baseline. Flag it, do not silently "fix" it — changing it changes the
baseline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LAGS = (7, 14, 28)
ROLL_WINDOWS = (7, 28)
HORIZON = 28
MIN_HISTORY = max(max(LAGS), max(ROLL_WINDOWS))

FEATURE_COLUMNS = [
    "horizon",
    "dow",
    "month",
    "snap_CA",
    "event_flag",
    "sell_price",
    *[f"lag_{k}" for k in LAGS],
    *[f"roll_mean_{w}" for w in ROLL_WINDOWS],
    "item_id",
    "store_id",
]
CATEGORICAL_COLUMNS = ["item_id", "store_id"]

# --- Researcher additions -------------------------------------------------------------
# Every builder below is computed for every frame; a model chooses which columns it
# consumes via its FEATURES list. FEATURE_COLUMNS above is the baseline's list and is
# never changed, so lgbm_baseline stays bit-for-bit reproducible.
EXTRA_ROLL_WINDOWS = (56, 91, 182)
DOW_MEAN_WEEKS = 4
SHORT_LAGS = (1, 2, 3)
EXTRA_ASOF_COLUMNS = [
    *[f"lag_{k}" for k in SHORT_LAGS],
    *[f"roll_mean_{w}" for w in EXTRA_ROLL_WINDOWS],
    "roll_std_28",
    "zero_frac_28",
    "days_since_sale",
]
EXTRA_HORIZON_COLUMNS = [
    "dow_mean_4w",   # mean of the 4 most recent same-weekday days before origin
    "lag_364",       # sales one year before the target date
    "yoy_roll_7",    # 7-day mean centred one year before the target date
    "price_ratio_origin",  # target-week price / last known price before origin
    "price_rel_max",       # target-week price / item max price up to origin
    "event_name",          # categorical event name (none = "none")
    "christmas",           # store-closed day
    "day_of_month",
    "week_of_year",
]
EXTRA_CATEGORICAL_COLUMNS = ["event_name"]
ALL_FEATURE_COLUMNS = FEATURE_COLUMNS + EXTRA_ASOF_COLUMNS + EXTRA_HORIZON_COLUMNS


class Panel:
    """Dense (series x date) view of the snapshot, plus calendar and price lookups."""

    def __init__(self, sales: pd.DataFrame, calendar: pd.DataFrame, prices: pd.DataFrame):
        wide = sales.pivot(index="id", columns="date", values="sales")
        self.dates = pd.DatetimeIndex(sorted(wide.columns))
        wide = wide[self.dates]
        self.ids = wide.index.to_numpy()
        self.values = wide.to_numpy(dtype=np.float32)
        self._pos = {ts: i for i, ts in enumerate(self.dates)}

        meta = sales.drop_duplicates("id").set_index("id").loc[self.ids]
        self.item_id = meta["item_id"].to_numpy()
        self.store_id = meta["store_id"].to_numpy()

        cal = calendar.copy()
        cal["dow"] = cal["date"].dt.dayofweek.astype("int16")
        cal["month"] = cal["date"].dt.month.astype("int16")
        cal["event_flag"] = (
            cal["event_name_1"].notna() | cal["event_name_2"].notna()
        ).astype("int8")
        cal["snap_CA"] = cal["snap_CA"].astype("int8")
        cal["event_name"] = cal["event_name_1"].fillna("none").astype(str)
        cal["christmas"] = (cal["event_name_1"] == "Christmas").astype("int8")
        cal["day_of_month"] = cal["date"].dt.day.astype("int16")
        cal["week_of_year"] = cal["date"].dt.isocalendar().week.astype("int16")
        self.calendar = cal.set_index("date")[
            ["dow", "month", "snap_CA", "event_flag", "wm_yr_wk",
             "event_name", "christmas", "day_of_month", "week_of_year"]
        ]
        self.prices = prices[["item_id", "wm_yr_wk", "sell_price"]].drop_duplicates(
            ["item_id", "wm_yr_wk"]
        )

    def pos(self, date: pd.Timestamp) -> int:
        try:
            return self._pos[pd.Timestamp(date)]
        except KeyError as exc:
            raise KeyError(f"{pd.Timestamp(date).date()} is not in the snapshot") from exc

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
    # --- researcher additions: still strictly < origin_pos ---
    for k in SHORT_LAGS:
        assert origin_pos - k < origin_pos
        out[f"lag_{k}"] = panel.values[:, origin_pos - k]
    for w in EXTRA_ROLL_WINDOWS:
        lo, hi = max(origin_pos - w, 0), origin_pos
        assert hi <= origin_pos
        out[f"roll_mean_{w}"] = panel.values[:, lo:hi].mean(axis=1)
    win28 = panel.values[:, origin_pos - 28 : origin_pos]
    out["roll_std_28"] = win28.std(axis=1)
    out["zero_frac_28"] = (win28 == 0).mean(axis=1)
    hist = panel.values[:, :origin_pos]
    nz = hist > 0
    # position of last non-zero day strictly before origin; series with no sale -> cap
    last_idx = np.where(nz.any(axis=1), origin_pos - 1 - np.argmax(nz[:, ::-1], axis=1), -1)
    dss = np.where(last_idx >= 0, origin_pos - last_idx, 365).astype(np.float32)
    out["days_since_sale"] = np.minimum(dss, 365)
    return out


def horizon_features(panel: Panel, origin_pos: int, horizon: int) -> dict[str, np.ndarray]:
    """Sales-derived features that vary with the target date but read only < origin_pos.

    Returns arrays shaped (n_series, horizon)."""
    n = panel.values.shape[0]
    dow_mean = np.zeros((n, horizon), dtype=np.float32)
    lag364 = np.zeros((n, horizon), dtype=np.float32)
    yoy7 = np.zeros((n, horizon), dtype=np.float32)
    for h in range(1, horizon + 1):
        target_pos = origin_pos + h - 1
        # most recent same-weekday position strictly before the origin
        p = target_pos - 7 * ((h + 6) // 7)
        cols = [p - 7 * k for k in range(DOW_MEAN_WEEKS)]
        assert max(cols) < origin_pos and min(cols) >= 0
        dow_mean[:, h - 1] = panel.values[:, cols].mean(axis=1)
        src = target_pos - 364
        assert src < origin_pos
        if src >= 0:
            lag364[:, h - 1] = panel.values[:, src]
            lo, hi = max(src - 3, 0), min(src + 4, origin_pos)
            assert hi <= origin_pos
            yoy7[:, h - 1] = panel.values[:, lo:hi].mean(axis=1)
    return {"dow_mean_4w": dow_mean, "lag_364": lag364, "yoy_roll_7": yoy7}


def build_frame(
    panel: Panel,
    origin: pd.Timestamp,
    horizon: int = HORIZON,
    with_target: bool = False,
) -> pd.DataFrame:
    """One (series x horizon) feature frame for a single origin.

    `origin` is the first forecast date. If `with_target`, the actual sales for the
    window are attached as `y`; only valid when the window lies inside the snapshot.
    """
    origin_pos = panel.pos(origin)
    n_series = panel.values.shape[0]
    dates = pd.DatetimeIndex([pd.Timestamp(origin) + pd.Timedelta(days=h) for h in range(horizon)])

    asof = asof_features(panel, origin_pos)
    frame = pd.DataFrame(
        {
            "id": np.repeat(panel.ids, horizon),
            "item_id": np.repeat(panel.item_id, horizon),
            "store_id": np.repeat(panel.store_id, horizon),
            "date": np.tile(dates.to_numpy(), n_series),
            "horizon": np.tile(np.arange(1, horizon + 1, dtype="int16"), n_series),
        }
    )
    for name, values in asof.items():
        frame[name] = np.repeat(values, horizon)
    for name, values in horizon_features(panel, origin_pos, horizon).items():
        frame[name] = values.reshape(-1)

    frame = frame.merge(panel.calendar, left_on="date", right_index=True, how="left")
    frame = frame.merge(panel.prices, on=["item_id", "wm_yr_wk"], how="left")

    # Price context known at the origin: last observed week strictly before origin.
    origin_wk = panel.calendar.loc[panel.dates[origin_pos - 1], "wm_yr_wk"]
    past_prices = panel.prices[panel.prices["wm_yr_wk"] <= origin_wk]
    price_origin = past_prices[past_prices["wm_yr_wk"] == origin_wk].set_index("item_id")["sell_price"]
    price_max = past_prices.groupby("item_id")["sell_price"].max()
    frame["price_ratio_origin"] = frame["sell_price"] / frame["item_id"].map(price_origin).astype(float)
    frame["price_rel_max"] = frame["sell_price"] / frame["item_id"].map(price_max).astype(float)
    frame = frame.drop(columns=["wm_yr_wk"])

    if with_target:
        end_pos = origin_pos + horizon
        if end_pos > panel.values.shape[1]:
            raise ValueError("target window runs past the end of the snapshot")
        frame["y"] = panel.values[:, origin_pos:end_pos].reshape(-1)

    for col in CATEGORICAL_COLUMNS + EXTRA_CATEGORICAL_COLUMNS:
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
    for col in CATEGORICAL_COLUMNS + EXTRA_CATEGORICAL_COLUMNS:
        out[col] = out[col].astype("category")
    return out
