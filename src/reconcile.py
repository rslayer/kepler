"""Middle-out multiplicative reconciliation (SPEC_v7).

The bottom model (recipe) forecasts item-store. This module forecasts one smoother AGGREGATE
level independently and scales the bottom forecasts within each aggregate group so their sum
matches the aggregate forecast. That borrows the aggregate's level (correcting the bottom
model's aggregate bias) without the bottom x bottom inverse full MinT would need.

Leak-free: the aggregate forecaster reads only history strictly before the origin, the same
as-of-origin contract the bottom features obey (asserted below).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import HORIZON, Panel

# aggregate forecaster: a light LGBM on the aggregated series (no price/SNAP; those do not
# aggregate cleanly). Lags/rolls are as-of-origin; the target-day calendar varies over the horizon.
_LAGS = (7, 14, 28, 364)
_ROLLS = (7, 28)
_AGG_PARAMS = dict(objective="regression", n_estimators=300, learning_rate=0.05, num_leaves=63,
                   min_child_samples=20, subsample=1.0, colsample_bytree=0.9,
                   deterministic=True, force_row_wise=True, num_threads=4, verbose=-1)


def group_index(panel: Panel, keys: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """(group_labels unique, index-per-bottom-series into that unique array) for the level `keys`."""
    labels = np.array(["|".join(str(panel.attrs[k][i]) for k in keys) for i in range(len(panel.ids))])
    uniq, inv = np.unique(labels, return_inverse=True)
    return uniq, inv


def aggregate_values(panel: Panel, inv: np.ndarray, n_groups: int) -> np.ndarray:
    """Sum the bottom (series x day) matrix to (group x day) using the group index `inv`."""
    agg = np.zeros((n_groups, panel.values.shape[1]), dtype=np.float64)
    np.add.at(agg, inv, panel.values.astype(np.float64))
    return agg


def _agg_frame(agg: np.ndarray, groups: np.ndarray, panel: Panel, origins: list[int],
               horizon: int, with_target: bool) -> pd.DataFrame:
    """One row per (group, origin, horizon-day). Lags/rolls read strictly before the origin."""
    cal = panel.calendar
    dow = cal["dow"].to_numpy(); month = cal["month"].to_numpy()
    event = (cal["event_flag"].to_numpy() if "event_flag" in cal.columns
             else np.zeros(len(cal), dtype=float))
    n_days = agg.shape[1]
    rows = []
    for o in origins:
        for k in _LAGS:
            assert o - k < o, "lag must precede the origin"
        lagvals = {f"lag_{k}": (agg[:, o - k] if o - k >= 0 else np.full(len(groups), np.nan)) for k in _LAGS}
        rollvals = {}
        for w in _ROLLS:
            lo = max(0, o - w)
            rollvals[f"roll_{w}"] = agg[:, lo:o].mean(axis=1) if o > lo else np.full(len(groups), np.nan)
        for h in range(1, horizon + 1):
            t = o + h
            if with_target and t >= n_days:
                continue
            block = {"group": groups, "horizon": h,
                     "dow": np.full(len(groups), dow[t] if t < n_days else dow[t % 7]),
                     "month": np.full(len(groups), month[t] if t < n_days else 1),
                     "event_flag": np.full(len(groups), event[t] if t < n_days else 0.0)}
            block.update({c: v for c, v in lagvals.items()})
            block.update({c: v for c, v in rollvals.items()})
            if with_target:
                block["y"] = agg[:, t]
            rows.append(pd.DataFrame(block))
    frame = pd.concat(rows, ignore_index=True)
    frame["group"] = frame["group"].astype("category")
    return frame


def _training_origins(origin_pos: int, n: int = 40, spacing: int = 7, horizon: int = HORIZON) -> list[int]:
    """Simulated origins strictly before `origin_pos`; newest ends its horizon before the origin."""
    newest = origin_pos - horizon
    origins = [newest - spacing * i for i in range(n)]
    return [o for o in origins if o - max(_LAGS) >= 0][::-1]


def aggregate_forecast(panel: Panel, keys: list[str], origin: pd.Timestamp, horizon: int,
                       seed: int) -> pd.DataFrame:
    """Independent forecast of the aggregate level `keys`: [group, date, agg_forecast]."""
    import lightgbm as lgb
    groups, inv = group_index(panel, keys)
    agg = aggregate_values(panel, inv, len(groups))
    o = panel.pos(origin)
    origins = _training_origins(o, horizon=horizon)
    train = _agg_frame(agg, groups, panel, origins, horizon, with_target=True)
    pred = _agg_frame(agg, groups, panel, [o], horizon, with_target=False)
    feats = [c for c in train.columns if c not in ("y",)]
    params = dict(_AGG_PARAMS); params.update(random_state=seed, seed=seed)
    model = lgb.LGBMRegressor(**params)
    model.fit(train[feats], train["y"], categorical_feature=["group"])
    yhat = np.clip(model.predict(pred[feats]), 0.0, None)
    dates = [pd.Timestamp(origin) + pd.Timedelta(days=int(h)) for h in pred["horizon"]]
    return pd.DataFrame({"group": pred["group"].astype(str).to_numpy(), "date": dates, "agg_forecast": yhat})


def reconcile(bottom_pred: pd.DataFrame, agg_pred: pd.DataFrame, panel: Panel, keys: list[str],
              clip: tuple[float, float] = (0.5, 2.0)) -> pd.DataFrame:
    """Scale each bottom forecast so its aggregate group sum matches agg_pred (clipped)."""
    id_to_group = {panel.ids[i]: "|".join(str(panel.attrs[k][i]) for k in keys) for i in range(len(panel.ids))}
    out = bottom_pred.copy()
    out["_group"] = out["id"].map(id_to_group)
    bu = out.groupby(["_group", "date"], observed=True)["forecast"].transform("sum")
    a = agg_pred.rename(columns={"group": "_group"}).set_index(["_group", "date"])["agg_forecast"]
    a_aligned = out.set_index(["_group", "date"]).index.map(a).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = np.where((bu.to_numpy() > 1e-9) & np.isfinite(a_aligned), a_aligned / bu.to_numpy(), 1.0)
    factor = np.clip(factor, clip[0], clip[1])
    out["forecast"] = out["forecast"].to_numpy() * factor
    return out[["id", "date", "forecast"]]
