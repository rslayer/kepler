"""Recursive 1-step forecaster (ensemble member for the recipe).

The recipe is DIRECT multi-horizon: as-of-origin features held constant across the 28 days.
This is its complement — a single 1-step model applied recursively: predict day h, feed that
prediction into the lags for day h+1, and so on. Its errors are structured differently
(they compound along the horizon rather than being fixed at the origin), which is exactly the
decorrelation an ensemble with the direct recipe needs.

Leak-free: features at target position t read the value array only strictly before t. In
training those are actuals; in the recursive forecast they are actuals before the origin plus
the model's own earlier predictions — never a future actual.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import HORIZON, Panel

LAGS = (1, 7, 14, 28)
ROLLS = (7, 28, 56)
CATS = ("item_id", "store_id")
PARAMS = dict(objective="regression", n_estimators=600, learning_rate=0.05, num_leaves=127,
              min_child_samples=50, subsample=0.7, subsample_freq=1, colsample_bytree=0.7,
              deterministic=True, force_row_wise=True, num_threads=4, verbose=-1)
TRAIN_DAYS = 365  # 1-step training rows span this many days before the origin


def _cal_array(panel: Panel, col: str) -> np.ndarray:
    if col in panel.calendar.columns:
        return panel.calendar[col].to_numpy()
    return np.zeros(len(panel.exog_dates))


def _features_at(vext: np.ndarray, price: np.ndarray, snap: np.ndarray, dow: np.ndarray,
                 month: np.ndarray, event: np.ndarray, xmas: np.ndarray, t: int) -> dict:
    """1-step features for every series at target column t (reads vext[:, <t] only)."""
    n = vext.shape[0]
    f = {}
    for k in LAGS:
        f[f"lag_{k}"] = vext[:, t - k] if t - k >= 0 else np.full(n, np.nan, np.float32)
    for w in ROLLS:
        lo = t - w
        f[f"roll_{w}"] = vext[:, lo:t].mean(axis=1) if lo >= 0 else np.full(n, np.nan, np.float32)
    f["roll_std_28"] = vext[:, max(0, t - 28):t].std(axis=1) if t >= 2 else np.full(n, np.nan, np.float32)
    f["dow"] = np.full(n, dow[t] if t < len(dow) else 0)
    f["month"] = np.full(n, month[t] if t < len(month) else 1)
    f["event_flag"] = np.full(n, event[t] if t < len(event) else 0.0)
    f["christmas"] = np.full(n, xmas[t] if t < len(xmas) else 0.0)
    f["snap"] = snap[:, t] if t < snap.shape[1] else np.zeros(n, np.float32)
    p = price[:, t] if t < price.shape[1] else np.full(n, np.nan, np.float32)
    hist_max = np.nanmax(price[:, max(0, t - 365):t], axis=1) if t >= 1 else np.full(n, np.nan)
    f["price"] = p
    with np.errstate(invalid="ignore", divide="ignore"):
        f["price_rel_max"] = p / hist_max
    return f


PARAMS_TWEEDIE = {**PARAMS, "objective": "tweedie", "tweedie_variance_power": 1.1}


class RecursiveForecaster:
    name = "lgbm_recursive"
    PARAMS = PARAMS
    LOG_TARGET = False        # legacy flag (log1p); TRANSFORM takes precedence when set
    TRANSFORM = None          # None | "log1p" | "sqrt": target transform to curb the recursive over-forecast

    def config(self) -> dict:
        return {"kind": self.name, "lags": list(LAGS), "rolls": list(ROLLS),
                "params": dict(self.PARAMS), "train_days": TRAIN_DAYS}

    def _matrices(self, panel: Panel):
        snap = None
        for c in ("snap_own",):
            if c in panel.sd_matrices:
                snap = np.asarray(panel.sd_matrices[c], dtype=np.float32); break
        if snap is None:
            sc = _cal_array(panel, "snap_CA").astype(np.float32)
            snap = np.tile(sc, (len(panel.ids), 1))
        return (panel.price_matrix, snap, _cal_array(panel, "dow"), _cal_array(panel, "month"),
                _cal_array(panel, "event_flag"), _cal_array(panel, "christmas"))

    def forecast(self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42) -> pd.DataFrame:
        import lightgbm as lgb
        o = panel.pos(origin)
        price, snap, dow, month, event, xmas = self._matrices(panel)
        cats = {c: pd.Categorical(panel.attrs[c]) for c in CATS if c in panel.attrs}

        # --- training: 1-step rows over TRAIN_DAYS before the origin
        feat_names = ([f"lag_{k}" for k in LAGS] + [f"roll_{w}" for w in ROLLS]
                      + ["roll_std_28", "dow", "month", "event_flag", "christmas", "snap",
                         "price", "price_rel_max"] + list(cats))
        start = max(max(LAGS + ROLLS), o - TRAIN_DAYS)
        rows, targets = [], []
        for t in range(start, o):
            fr = _features_at(panel.values, price, snap, dow, month, event, xmas, t)
            for c, v in cats.items():
                fr[c] = v
            rows.append(pd.DataFrame(fr)); targets.append(panel.values[:, t])
        train = pd.concat(rows, ignore_index=True)
        for c in cats:
            train[c] = pd.Categorical(train[c])
        y = np.concatenate(targets).astype(np.float64)
        tf = self.TRANSFORM or ("log1p" if self.LOG_TARGET else None)
        if tf == "log1p":
            y = np.log1p(y)
        elif tf == "sqrt":
            y = np.sqrt(y)
        params = dict(self.PARAMS); params.update(random_state=seed, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
        model = lgb.LGBMRegressor(**params)
        model.fit(train[feat_names], y, categorical_feature=list(cats))

        # --- recursive forecast. The fold window is [origin, origin+27]; the origin day is
        # the first forecast day (column o). vext holds actuals before o; as each day is
        # predicted its column is overwritten so later lags read predictions, never the
        # window's actuals. A horizon buffer covers a post-snapshot origin (o+h-1 >= n_days).
        vext = np.concatenate([panel.values.copy(), np.zeros((len(panel.ids), horizon), np.float32)], axis=1)
        preds = np.empty((len(panel.ids), horizon), dtype=np.float64)
        for h in range(1, horizon + 1):
            t = o + (h - 1)  # target column: origin+ (h-1)
            fr = _features_at(vext, price, snap, dow, month, event, xmas, t)
            for c, v in cats.items():
                fr[c] = v
            x = pd.DataFrame(fr)
            for c in cats:
                x[c] = pd.Categorical(x[c], categories=cats[c].categories)
            yhat = model.predict(x[feat_names])
            if tf == "log1p":
                yhat = np.expm1(yhat)
            elif tf == "sqrt":
                yhat = np.square(np.clip(yhat, 0.0, None))
            yhat = np.clip(yhat, 0.0, None)
            vext[:, t] = yhat  # overwrite so subsequent lags/rolls use the prediction
            preds[:, h - 1] = yhat
        dates = pd.DatetimeIndex([pd.Timestamp(origin) + pd.Timedelta(days=h) for h in range(horizon)])
        return pd.DataFrame({"id": np.repeat(panel.ids, horizon),
                             "date": np.tile(dates.to_numpy(), len(panel.ids)),
                             "forecast": preds.reshape(-1)})


class RecursiveForecasterTweedie(RecursiveForecaster):
    """Recursive 1-step under a Tweedie objective (variance power 1.1). Tweedie models a
    non-negative, zero-inflated target, so its predictions are naturally >= 0 and better
    calibrated for intermittent demand than a regression model whose negative predictions get
    clipped to 0 (that clip inflates the mean, and in a recursive model the inflation compounds
    into the +9.9% bias seen with the regression member)."""

    name = "lgbm_recursive_tw"
    PARAMS = PARAMS_TWEEDIE


class RecursiveForecasterLog(RecursiveForecaster):
    """Recursive 1-step on a log1p target. log1p compresses the right-skew of intermittent
    demand so the model's conditional mean over-predicts less; the recursive drift (the +9.6%
    bias that persisted under both regression and Tweedie) should shrink."""

    name = "lgbm_recursive_log"
    LOG_TARGET = True


class RecursiveForecasterSqrt(RecursiveForecaster):
    """Recursive 1-step on a sqrt target: milder than log1p, it sits between the raw model's
    +9.6% over-forecast and the log model's -21% under-forecast, so the recursive bias should
    land closer to zero."""

    name = "lgbm_recursive_sqrt"
    TRANSFORM = "sqrt"
