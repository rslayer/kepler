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
    EXTRA_CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    HORIZON,
    Panel,
    build_frame,
    build_training_set,
)

ALL_CATEGORICAL = CATEGORICAL_COLUMNS + EXTRA_CATEGORICAL_COLUMNS


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
    # Subclasses (experiments) override FEATURES / PARAMS / origin settings. The baseline
    # keeps FEATURE_COLUMNS verbatim so its config hash and metrics do not move.
    FEATURES = list(FEATURE_COLUMNS)

    def config(self) -> dict:
        return {
            "kind": "lgbm",
            "params": dict(self.PARAMS),
            "features": list(self.FEATURES),
            "n_train_origins": self.N_TRAIN_ORIGINS,
            "train_origin_spacing": self.TRAIN_ORIGIN_SPACING,
            **({"drop_prelaunch": True} if self.DROP_PRELAUNCH else {}),
            **({"recency_half_life_days": self.RECENCY_HALF_LIFE_DAYS} if self.RECENCY_HALF_LIFE_DAYS else {}),
            **({"metric_weights": True} if self.METRIC_WEIGHTS else {}),
        }

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        import lightgbm as lgb

        params = dict(self.PARAMS)
        params.update(random_state=seed, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
        model = lgb.LGBMRegressor(**params)

        features = list(self.FEATURES)
        categorical = [c for c in features if c in ALL_CATEGORICAL]
        x_train = train[features]
        x_pred = predict[features].copy()
        # Align categorical dictionaries so LightGBM sees identical codes in both frames.
        for col in categorical:
            categories = x_train[col].cat.categories
            x_pred[col] = pd.Categorical(x_pred[col], categories=categories)

        model.fit(
            x_train,
            self.transform_target(train["y"]),
            sample_weight=self.sample_weight(train),
            categorical_feature=categorical,
        )
        return self.inverse_transform(model.predict(x_pred))

    # Training-set hooks (no-ops for the baseline).
    DROP_PRELAUNCH = False   # drop rows of series with no sale before their training origin
    RECENCY_HALF_LIFE_DAYS: float | None = None  # weight = 0.5 ** (origin age / half life)

    def filter_training(self, train: pd.DataFrame, fold_origin: pd.Timestamp) -> pd.DataFrame:
        if self.DROP_PRELAUNCH:
            train = train[train["ever_sold"] == 1].reset_index(drop=True)
        return train

    METRIC_WEIGHTS = False  # weight rows by dollar weight / scale, as WRMSSE does per series

    def sample_weight(self, train: pd.DataFrame):
        w = np.ones(len(train), dtype=float)
        used = False
        if self.RECENCY_HALF_LIFE_DAYS is not None:
            origin = train["date"] - pd.to_timedelta(train["horizon"].astype(int) - 1, unit="D")
            age_days = (self._fold_origin - origin).dt.days.to_numpy(dtype=float)
            w *= np.power(0.5, age_days / self.RECENCY_HALF_LIFE_DAYS)
            used = True
        if self.METRIC_WEIGHTS:
            mw = train["aux_wdollar"].to_numpy(dtype=float) / train["aux_scale"].to_numpy(dtype=float)
            mw = np.nan_to_num(mw, nan=0.0, posinf=0.0)
            w *= mw / max(mw.mean(), 1e-12)
            used = True
        return w if used else None

    # Target transform hooks (identity for the baseline).
    def transform_target(self, y: pd.Series) -> pd.Series:
        return y

    def inverse_transform(self, pred: np.ndarray) -> np.ndarray:
        return pred

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
        self._fold_origin = pd.Timestamp(origin)
        train = self.filter_training(train, self._fold_origin)
        predict = build_frame(panel, origin, horizon, with_target=False)
        preds = self._fit_predict(train, predict, seed)
        out = predict[["id", "date"]].copy()
        out["forecast"] = np.clip(preds, 0.0, None)
        return out


# ----------------------------------------------------------------------- experiments
# One class per experiment; each changes exactly one thing relative to its parent.


class LGBMShortLags(LGBMBaseline):
    """r010 (kept): + lag_1, lag_2, lag_3 at the origin (current state: stockouts, surges)."""

    name = "lgbm_shortlags"
    FEATURES = LGBMBaseline.FEATURES + ["lag_1", "lag_2", "lag_3"]


class LGBMShortLagsOrigins80(LGBMShortLags):
    """r011: r010 with 80 training origins."""

    name = "lgbm_shortlags_o80"
    N_TRAIN_ORIGINS = 80


class LGBMShortLagsTweedie(LGBMShortLags):
    """r017 (discarded alone, ensemble member): r010 with Tweedie objective, power 1.2."""

    name = "lgbm_sl_tweedie"
    PARAMS = {**LGBMShortLags.PARAMS, "objective": "tweedie", "tweedie_variance_power": 1.2}


class LGBMShortLagsMCS200(LGBMShortLags):
    """r018 (investigate, ensemble member): r010 with min_child_samples 200."""

    name = "lgbm_sl_mcs200"
    PARAMS = {**LGBMShortLags.PARAMS, "min_child_samples": 200}


class Ensemble:
    """Equal-weight average of member models' forecasts. Members are full models fit
    independently under the same contract, so the average is leak-free if they are."""

    name = "ensemble"
    MEMBERS: tuple[type, ...] = ()
    WEIGHTS: tuple[float, ...] | None = None  # None = equal weights

    def _weights(self) -> np.ndarray:
        w = np.ones(len(self.MEMBERS)) if self.WEIGHTS is None else np.asarray(self.WEIGHTS, dtype=float)
        return w / w.sum()

    def config(self) -> dict:
        return {
            "kind": "ensemble",
            "members": [m().config() | {"name": m.name} for m in self.MEMBERS],
            "weights": self._weights().round(4).tolist(),
        }

    def forecast(self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42) -> pd.DataFrame:
        outs = [m().forecast(panel, origin, horizon, seed) for m in self.MEMBERS]
        base = outs[0][["id", "date"]].copy()
        stack = np.column_stack([o["forecast"].to_numpy(dtype=float) for o in outs])
        base["forecast"] = stack @ self._weights()
        return base


class EnsembleL2Tweedie(Ensemble):
    """r021: average of r010 (L2) and r017 (Tweedie) forecasts."""

    name = "ens_l2_tweedie"
    MEMBERS = (LGBMShortLags, LGBMShortLagsTweedie)


class EnsembleMCS200Tweedie(Ensemble):
    """r022: r021 with the L2 member swapped for the regularised r018 (min_child_samples 200)."""

    name = "ens_mcs200_tweedie"
    MEMBERS = (LGBMShortLagsMCS200, LGBMShortLagsTweedie)


class EnsembleL2Tweedie73(Ensemble):
    """r023: r021 with weights 0.7 (L2) / 0.3 (Tweedie) instead of equal."""

    name = "ens_l2_tweedie_73"
    MEMBERS = (LGBMShortLags, LGBMShortLagsTweedie)
    WEIGHTS = (0.7, 0.3)


MODELS: dict[str, type] = {
    SeasonalNaive.name: SeasonalNaive,
    LGBMBaseline.name: LGBMBaseline,
    LGBMShortLags.name: LGBMShortLags,
    LGBMShortLagsOrigins80.name: LGBMShortLagsOrigins80,
    LGBMShortLagsTweedie.name: LGBMShortLagsTweedie,
    LGBMShortLagsMCS200.name: LGBMShortLagsMCS200,
    EnsembleL2Tweedie.name: EnsembleL2Tweedie,
    EnsembleMCS200Tweedie.name: EnsembleMCS200Tweedie,
    EnsembleL2Tweedie73.name: EnsembleL2Tweedie73,
}


def get_model(name: str):
    if name not in MODELS:
        raise SystemExit(f"Unknown model '{name}'. Registered: {', '.join(sorted(MODELS))}")
    return MODELS[name]()
