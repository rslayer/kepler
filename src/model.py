"""Model definitions. The researcher edits this file.

CONTRACT
--------
A model is fit only on data strictly prior to the fold origin and returns a 28-day-ahead
forecast for every series as a long frame [id, date, forecast].

To add a model: write a class with `name`, `config()`, and `forecast()`, then register it
in MODELS at the bottom. Do not touch the fold logic in src/backtest.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    HORIZON,
    Panel,
    build_frame,
    build_training_set,
)


class SeasonalNaive:
    """Repeat the last fully observed week: forecast(d) = sales(d - 7k), k chosen so the
    source date is the most recent same-weekday date strictly before the origin."""

    name = "seasonal_naive"

    def config(self) -> dict:
        return {"kind": "seasonal_naive", "season": 7}

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        origin_pos = panel.pos(origin)
        offsets = [(origin_pos - 7) + ((h - 1) % 7) for h in range(1, horizon + 1)]
        assert all(o < origin_pos for o in offsets), "seasonal naive would read at/after origin"
        preds = panel.values[:, offsets]
        dates = pd.DatetimeIndex(
            [pd.Timestamp(origin) + pd.Timedelta(days=h) for h in range(horizon)]
        )
        return pd.DataFrame(
            {
                "id": np.repeat(panel.ids, horizon),
                "date": np.tile(dates.to_numpy(), panel.values.shape[0]),
                "forecast": preds.reshape(-1).astype(float),
            }
        )


class LGBMBaseline:
    """One LightGBM across all series. Lags 7/14/28, rolling means 7/28, day-of-week,
    month, SNAP flag, event flag, sell price, item and store as categoricals."""

    name = "lgbm_baseline"

    # Determinism: fixed seed, deterministic=True, force_row_wise=True, and a fixed
    # thread count. Thread count matters — LightGBM's histogram sums are order-dependent,
    # so varying threads breaks four-decimal reproducibility.
    PARAMS = {
        "objective": "regression",
        "n_estimators": 300,
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_child_samples": 50,
        "colsample_bytree": 0.9,
        "subsample": 1.0,
        "reg_lambda": 1.0,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 4,
        "verbose": -1,
    }
    N_TRAIN_ORIGINS = 40
    TRAIN_ORIGIN_SPACING = 7
    FEATURES = list(FEATURE_COLUMNS)

    def config(self) -> dict:
        return {
            "kind": "lgbm",
            "params": dict(self.PARAMS),
            "features": list(self.FEATURES),
            "n_train_origins": self.N_TRAIN_ORIGINS,
            "train_origin_spacing": self.TRAIN_ORIGIN_SPACING,
        }

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        import lightgbm as lgb

        params = dict(self.PARAMS)
        params.update(random_state=seed, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
        model = lgb.LGBMRegressor(**params)

        x_train = train[self.FEATURES]
        x_pred = predict[self.FEATURES].copy()
        # Align categorical dictionaries so LightGBM sees identical codes in both frames.
        for col in CATEGORICAL_COLUMNS:
            categories = x_train[col].cat.categories
            x_pred[col] = pd.Categorical(x_pred[col], categories=categories)

        model.fit(x_train, train["y"], categorical_feature=CATEGORICAL_COLUMNS)
        return model.predict(x_pred)

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        train = build_training_set(
            panel,
            origin,
            n_origins=self.N_TRAIN_ORIGINS,
            spacing_days=self.TRAIN_ORIGIN_SPACING,
            horizon=horizon,
        )
        predict = build_frame(panel, origin, horizon, with_target=False)
        preds = self._fit_predict(train, predict, seed)
        out = predict[["id", "date"]].copy()
        out["forecast"] = np.clip(preds, 0.0, None)
        return out


class LGBMLocalSmooth(LGBMBaseline):
    """lgbm_baseline plus a local 7-day smoothed level around the target date."""

    name = "lgbm_local_smooth"
    FEATURES = LGBMBaseline.FEATURES + ["local_smooth_7"]


MODELS: dict[str, type] = {
    SeasonalNaive.name: SeasonalNaive,
    LGBMBaseline.name: LGBMBaseline,
    LGBMLocalSmooth.name: LGBMLocalSmooth,
}


def get_model(name: str):
    if name not in MODELS:
        raise SystemExit(f"Unknown model '{name}'. Registered: {', '.join(sorted(MODELS))}")
    return MODELS[name]()
