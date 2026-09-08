"""Metrics. FROZEN — never edited by any agent.

WRMSSE is the M5 competition metric restricted to the item-store level (level 12) with
the standard competition weights:

    scale_i  = mean over the training period of (y_t - y_{t-1})^2, counted only from the
               first non-zero observation of series i onward
    rmsse_i  = sqrt( mean over the horizon of (y - yhat)^2 / scale_i )
    w_i      = dollar sales of series i over the final 28 days of the training period,
               normalised so the weights sum to 1
    WRMSSE   = sum_i w_i * rmsse_i

Series whose scale is zero (no variation in training) carry zero weight, as in M5.

WAPE = sum |y - yhat| / sum y
bias = sum (yhat - y) / sum y
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON_BUCKETS = {"h1_7": (1, 7), "h8_14": (8, 14), "h15_28": (15, 28)}


def _wide(df: pd.DataFrame, value: str) -> pd.DataFrame:
    """Long [id, date, <value>] -> wide frame indexed by id, columns sorted by date."""
    w = df.pivot(index="id", columns="date", values=value)
    return w.reindex(columns=sorted(w.columns))


def series_scale(train_wide: pd.DataFrame) -> pd.Series:
    """Mean squared first difference per series, from the first non-zero sale onward."""
    values = train_wide.to_numpy(dtype=float)
    scales = np.full(values.shape[0], np.nan)
    for i in range(values.shape[0]):
        row = values[i]
        nonzero = np.flatnonzero(row > 0)
        if nonzero.size == 0:
            continue
        active = row[nonzero[0] :]
        if active.size < 2:
            continue
        diffs = np.diff(active)
        scales[i] = float(np.mean(diffs**2))
    out = pd.Series(scales, index=train_wide.index, name="scale")
    # A flat-but-nonzero series has scale 0 and would divide by zero; M5 drops these.
    return out.replace(0.0, np.nan)


def series_weights(
    train_long: pd.DataFrame,
    prices: pd.DataFrame,
    calendar: pd.DataFrame,
    last_n_days: int = 28,
) -> pd.Series:
    """Normalised dollar-sales weights over the final `last_n_days` of training."""
    cutoff = train_long["date"].max() - pd.Timedelta(days=last_n_days - 1)
    tail = train_long.loc[train_long["date"] >= cutoff, ["id", "item_id", "store_id", "date", "sales"]]
    tail = tail.merge(calendar[["date", "wm_yr_wk"]], on="date", how="left")
    tail = tail.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")
    tail["dollars"] = tail["sales"] * tail["sell_price"].fillna(0.0)
    dollars = tail.groupby("id", observed=True)["dollars"].sum()
    total = dollars.sum()
    if total <= 0:
        raise ValueError("Total dollar sales over the weighting window is zero.")
    return (dollars / total).rename("weight")


def score_window(
    truth: pd.DataFrame,
    pred: pd.DataFrame,
    train_long: pd.DataFrame,
    prices: pd.DataFrame,
    calendar: pd.DataFrame,
) -> tuple[dict, pd.DataFrame]:
    """Score one 28-day window.

    truth: [id, date, sales] over the evaluation window
    pred:  [id, date, forecast] over the same window
    train_long: [id, item_id, store_id, date, sales], strictly before the window
    Returns (aggregate metrics dict, per-series detail frame).
    """
    truth_wide = _wide(truth, "sales")
    pred_wide = _wide(pred, "forecast").reindex(index=truth_wide.index, columns=truth_wide.columns)
    if pred_wide.isna().any().any():
        missing = int(pred_wide.isna().sum().sum())
        raise ValueError(f"Forecast has {missing} missing (id, date) cells for this window.")

    train_wide = _wide(train_long[["id", "date", "sales"]], "sales").reindex(index=truth_wide.index)
    scale = series_scale(train_wide)
    weight = series_weights(train_long, prices, calendar).reindex(truth_wide.index).fillna(0.0)

    err = pred_wide.to_numpy(dtype=float) - truth_wide.to_numpy(dtype=float)
    mse = np.mean(err**2, axis=1)
    rmsse = np.sqrt(mse / scale.to_numpy(dtype=float))

    detail = pd.DataFrame(
        {
            "scale": scale.to_numpy(dtype=float),
            "weight": weight.to_numpy(dtype=float),
            "rmsse": rmsse,
            "abs_err": np.abs(err).sum(axis=1),
            "actual": truth_wide.to_numpy(dtype=float).sum(axis=1),
            "forecast": pred_wide.to_numpy(dtype=float).sum(axis=1),
        },
        index=truth_wide.index,
    )
    scored = detail["rmsse"].notna()
    # Renormalise across scoreable series so dropped ones do not deflate the metric.
    live_weight = detail.loc[scored, "weight"]
    if live_weight.sum() <= 0:
        raise ValueError("No scoreable series carry weight in this window.")
    detail["weight_norm"] = 0.0
    detail.loc[scored, "weight_norm"] = live_weight / live_weight.sum()
    detail["contrib"] = detail["weight_norm"] * detail["rmsse"].fillna(0.0)

    actual_sum = detail["actual"].sum()
    if actual_sum <= 0:
        raise ValueError("Total actual sales in the evaluation window is zero.")

    horizons = np.arange(1, truth_wide.shape[1] + 1)
    metrics = {
        "wrmsse": float(detail["contrib"].sum()),
        "wape": float(detail["abs_err"].sum() / actual_sum),
        "bias": float((detail["forecast"].sum() - actual_sum) / actual_sum),
        "n_series": int(truth_wide.shape[0]),
        "n_scored": int(scored.sum()),
    }
    for name, (lo, hi) in HORIZON_BUCKETS.items():
        sel = (horizons >= lo) & (horizons <= hi)
        a = truth_wide.to_numpy(dtype=float)[:, sel]
        e = err[:, sel]
        metrics[f"wape_{name}"] = float(np.abs(e).sum() / a.sum()) if a.sum() > 0 else float("nan")
    return metrics, detail


def aggregate_folds(fold_metrics: list[dict]) -> dict:
    """Aggregate per-fold metrics into the run-level numbers. Plain mean across folds."""
    keys = ["wrmsse", "wape", "bias", "wape_h1_7", "wape_h8_14", "wape_h15_28"]
    return {k: float(np.mean([m[k] for m in fold_metrics])) for k in keys}
