"""Hierarchical WRMSSE — the M5 competition's official metric. FROZEN once tagged v4-quality.

For each of the dataset's hierarchy levels (M5: 12 levels, from the grand total down to
item-store), forecasts and actuals are summed to that level and every aggregate series is
scored exactly as src/scorer.py scores an item-store series:

    scale_a  = mean over the training period of (y_t - y_{t-1})^2, from the aggregate's
               first non-zero day onward
    rmsse_a  = sqrt( mean over the horizon of (y - yhat)^2 / scale_a )
    w_a      = the aggregate's dollar sales over the final 28 training days, normalised
               within the level over scoreable aggregates
    level score = sum_a w_a * rmsse_a
    WRMSSE_hier = mean of the level scores (levels weighted equally, the competition rule)

Level 12 (item-store) of this scorer equals src/scorer.py's wrmsse by construction.
Inputs are the same frames the level-12 scorer takes, plus the series attribute table and
the hierarchy (a list of attribute-column lists; [] is the grand total).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .scorer import _wide, series_scale

LEVEL_NAMES = {
    (): "L1 total", ("state_id",): "L2 state", ("store_id",): "L3 store", ("cat_id",): "L4 category",
    ("dept_id",): "L5 department", ("state_id", "cat_id"): "L6 state-category",
    ("state_id", "dept_id"): "L7 state-department", ("store_id", "cat_id"): "L8 store-category",
    ("store_id", "dept_id"): "L9 store-department", ("item_id",): "L10 item",
    ("item_id", "state_id"): "L11 item-state", ("item_id", "store_id"): "L12 item-store",
}


def _dollars_last_28(train_long: pd.DataFrame, prices: pd.DataFrame, calendar: pd.DataFrame) -> pd.Series:
    """Unnormalised dollar sales per series over the final 28 training days (scorer's window)."""
    cutoff = train_long["date"].max() - pd.Timedelta(days=27)
    tail = train_long.loc[train_long["date"] >= cutoff, ["id", "item_id", "store_id", "date", "sales"]]
    tail = tail.merge(calendar[["date", "wm_yr_wk"]], on="date", how="left")
    tail = tail.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")
    tail["dollars"] = tail["sales"] * tail["sell_price"].fillna(0.0)
    return tail.groupby("id", observed=True)["dollars"].sum()


def score_window_hier(
    truth: pd.DataFrame,
    pred: pd.DataFrame,
    train_long: pd.DataFrame,
    prices: pd.DataFrame,
    calendar: pd.DataFrame,
    series: pd.DataFrame,
    hierarchy: list[list[str]],
) -> tuple[dict, pd.DataFrame]:
    truth_wide = _wide(truth, "sales")
    pred_wide = _wide(pred, "forecast").reindex(index=truth_wide.index, columns=truth_wide.columns)
    if pred_wide.isna().any().any():
        raise ValueError("Forecast has missing (id, date) cells for this window.")
    train_wide = _wide(train_long[["id", "date", "sales"]], "sales").reindex(index=truth_wide.index)
    dollars = _dollars_last_28(train_long, prices, calendar).reindex(truth_wide.index).fillna(0.0)
    attrs = series.set_index("series_id").reindex(truth_wide.index)

    rows = []
    level_scores = {}
    for keys in hierarchy:
        keys = list(keys)
        if keys:
            grp = attrs[keys].astype(str).agg("|".join, axis=1).to_numpy()
        else:
            grp = np.array(["total"] * len(truth_wide))
        t = truth_wide.groupby(grp).sum()
        p = pred_wide.groupby(grp).sum()
        h = train_wide.groupby(grp).sum()
        d = dollars.groupby(grp).sum().reindex(t.index)
        scale = series_scale(h).reindex(t.index)
        err = p.to_numpy(dtype=float) - t.to_numpy(dtype=float)
        rmsse = np.sqrt(np.mean(err**2, axis=1) / scale.to_numpy(dtype=float))
        ok = np.isfinite(rmsse)
        w = d.to_numpy(dtype=float) * ok
        if w.sum() <= 0:
            raise ValueError(f"no weight at level {keys}")
        w = w / w.sum()
        score = float(np.nansum(w * np.where(ok, rmsse, 0.0)))
        name = LEVEL_NAMES.get(tuple(keys), "+".join(keys) or "total")
        level_scores[name] = score
        rows.append({"level": name, "keys": "+".join(keys) or "total", "n_series": int(len(t)),
                     "n_scored": int(ok.sum()), "score": score})
    per_level = pd.DataFrame(rows)
    return {"wrmsse_hier": float(np.mean(list(level_scores.values()))), "levels": level_scores}, per_level
