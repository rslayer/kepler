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
    event_window_multipliers,
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
    # Subclasses (experiments) override FEATURES / PARAMS / origin settings / hooks. The
    # baseline keeps FEATURE_COLUMNS verbatim and adds no config keys, so its config hash
    # (900159c6f3dd, run r033) and metrics do not move.
    FEATURES: list[str] | None = None  # None = the bound dataset's FEATURE_COLUMNS

    @property
    def features(self) -> list[str]:
        return list(FEATURE_COLUMNS) if self.FEATURES is None else list(self.FEATURES)

    def config(self) -> dict:
        cfg = {
            "kind": "lgbm",
            "params": dict(self.PARAMS),
            "features": self.features,
            "n_train_origins": self.N_TRAIN_ORIGINS,
            "train_origin_spacing": self.TRAIN_ORIGIN_SPACING,
        }
        cfg.update(self.extra_config())
        return cfg

    def extra_config(self) -> dict:
        """Experiment-specific config keys; empty for the baseline."""
        return {}

    def postprocess(self, predict: pd.DataFrame, preds: np.ndarray) -> np.ndarray:
        """Post-fit hook (identity for the baseline): adjust raw predictions using only
        columns of the predict frame that are known in advance (calendar, price, horizon)."""
        return preds

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        import lightgbm as lgb

        params = dict(self.PARAMS)
        params.update(random_state=seed, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
        model = lgb.LGBMRegressor(**params)

        features = self.features
        categorical = [c for c in features if c in CATEGORICAL_COLUMNS]
        x_train = train[features]
        x_pred = predict[features].copy()
        # Align categorical dictionaries so LightGBM sees identical codes in both frames.
        for col in categorical:
            categories = x_train[col].cat.categories
            x_pred[col] = pd.Categorical(x_pred[col], categories=categories)

        model.fit(x_train, train["y"], categorical_feature=categorical)
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
        preds = self.postprocess(predict, preds)
        out = predict[["id", "date"]].copy()
        out["forecast"] = np.clip(preds, 0.0, None)
        return out


# ----------------------------------------------------------------------- experiments
# One class per experiment; each changes exactly one thing relative to its parent.


class LGBMChristmasZero(LGBMBaseline):
    """H031 (run r037, branch exp/r037; ported to the v3 contract): forecast 0 on Christmas
    Day. The store is closed every 25 December (sales 0 on 2012-2015) but the 40-origin
    training window never contains a Christmas, so the baseline forecasts a normal day
    inside folds 2 and 3. Reads the adapter's `christmas` calendar flag."""

    name = "lgbm_xmas0"

    def extra_config(self) -> dict:
        return {"postprocess": "christmas_zero"}

    def postprocess(self, predict: pd.DataFrame, preds: np.ndarray) -> np.ndarray:
        closed = predict["christmas"].to_numpy() == 1
        return np.where(closed, 0.0, preds)


# ----------------------------------------------------------------------- recipe (SPEC_v4 Part C)
# The published M5 recipe, added one ingredient at a time on top of the champion. Each class
# changes exactly one thing relative to its parent so the ledger records what it was worth.


class LGBMRecipe1Capacity(LGBMChristmasZero):
    """Ingredient 1: capacity with early stopping. Up to 3000 rounds at lr 0.02, deeper
    leaves, feature/bagging subsampling (seeded). The newest simulated training origin is
    held out as the validation set for early stopping (its 28-day target window closes
    before the fold origin, so no fold data is touched); the model is used as-is at its
    best iteration."""

    name = "recipe1_capacity"
    # SPEC_v4 asked for lr 0.02 / 3000 rounds; that exceeded the 60-minute screening budget
    # on this laptop (Tweedie fits ~8 min each). lr 0.05 / 1500 keeps the early-stopped
    # capacity idea at ~2.5x fewer trees; recorded as a deviation in the changelog.
    PARAMS = {
        **LGBMChristmasZero.PARAMS,
        "n_estimators": 1500, "learning_rate": 0.05, "num_leaves": 127,
        "min_child_samples": 100, "colsample_bytree": 0.7, "subsample": 0.7, "subsample_freq": 1,
    }
    EARLY_STOPPING_ROUNDS = 100

    def extra_config(self) -> dict:
        return {**super().extra_config(), "early_stopping": self.EARLY_STOPPING_ROUNDS, "validation": "newest_origin"}

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        import lightgbm as lgb

        params = dict(self.PARAMS)
        params.update(random_state=seed, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
        features = self.features
        categorical = [c for c in features if c in CATEGORICAL_COLUMNS]
        # rows from the newest simulated origin = validation; origin = target date - (h - 1)
        origin_of_row = train["date"] - pd.to_timedelta(train["horizon"].astype(int) - 1, unit="D")
        newest = origin_of_row.max()
        val_mask = (origin_of_row == newest).to_numpy()
        x_all = train[features]
        x_tr, y_tr = x_all[~val_mask], train["y"][~val_mask]
        x_va, y_va = x_all[val_mask], train["y"][val_mask]
        x_pred = predict[features].copy()
        for col in categorical:
            cats = x_tr[col].cat.categories
            x_va = x_va.assign(**{col: pd.Categorical(x_va[col], categories=cats)})
            x_pred[col] = pd.Categorical(x_pred[col], categories=cats)
        model = lgb.LGBMRegressor(**params)
        model.fit(x_tr, y_tr, eval_set=[(x_va, y_va)], categorical_feature=categorical,
                  callbacks=[lgb.early_stopping(self.EARLY_STOPPING_ROUNDS, verbose=False)])
        self.last_best_iteration = int(model.best_iteration_ or params["n_estimators"])
        return model.predict(x_pred, num_iteration=model.best_iteration_)


class LGBMRecipe2Tweedie(LGBMRecipe1Capacity):
    """Ingredient 2: Tweedie objective (variance power 1.1) plus a per-series level-growth
    feature, level_ratio_28_365 (last-28-day mean over last-365-day mean, at the origin).
    The v0 lessons showed Tweedie's under-forecast is level growth between training and
    forecast windows (ledger H027); the feature lets the model see it."""

    name = "recipe2_tweedie"
    PARAMS = {**LGBMRecipe1Capacity.PARAMS, "objective": "tweedie", "tweedie_variance_power": 1.1}

    @property
    def features(self) -> list[str]:
        return super().features + ["level_ratio_28_365"]


class LGBMRecipe3Direct(LGBMRecipe2Tweedie):
    """Ingredient 3: direct multi-horizon. One model per horizon week (h 1-7, 8-14, 15-21,
    22-28), each fit on that week's rows with target-relative lags tlag_7..tlag_35, which
    are defined only where the lagged day is strictly before the origin (k >= h). Week w
    therefore sees lags >= 7w; the rest are all-NaN in its rows and carry nothing."""

    name = "recipe3_direct"
    WEEKS = ((1, 7), (8, 14), (15, 21), (22, 28))

    @property
    def features(self) -> list[str]:
        return super().features + [f"tlag_{k}" for k in (7, 14, 21, 28, 35)]

    def extra_config(self) -> dict:
        return {**super().extra_config(), "direct_weeks": [list(w) for w in self.WEEKS]}

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        out = np.empty(len(predict), dtype=float)
        th = train["horizon"].astype(int).to_numpy()
        ph = predict["horizon"].astype(int).to_numpy()
        for lo, hi in self.WEEKS:
            tm = (th >= lo) & (th <= hi)
            pm = (ph >= lo) & (ph <= hi)
            out[pm] = super()._fit_predict(train[tm], predict[pm], seed)
        return out


class LGBMRecipe4Rolling(LGBMRecipe3Direct):
    """Ingredient 4: rolling mean/std/max over 7/14/28/56/180 days at the origin, zero-run
    length, days since first sale, days since last sale (all strictly before the origin)."""

    name = "recipe4_rolling"
    ROLL_EXTRA = ([f"roll_mean_{w}" for w in (14, 56, 180)]
                  + [f"roll_std_{w}" for w in (7, 14, 28, 56, 180)]
                  + [f"roll_max_{w}" for w in (7, 14, 28, 56, 180)]
                  + ["zero_run_length", "days_since_first_sale", "days_since_last_sale"])

    @property
    def features(self) -> list[str]:
        return super().features + self.ROLL_EXTRA


class LGBMRecipe5Price(LGBMRecipe4Rolling):
    """Ingredient 5: price relative to the item's max to date, week-over-week price
    momentum, an on-promotion flag, price relative to the price group's mean that day, and
    the share of the group on promotion."""

    name = "recipe5_price"
    PRICE_EXTRA = ["price_rel_max", "price_momentum", "on_promo", "price_rel_group", "group_promo_share"]

    @property
    def features(self) -> list[str]:
        return super().features + self.PRICE_EXTRA


class LGBMRecipe6Calendar(LGBMRecipe5Price):
    """Ingredient 6: event lead/lag flags (+/-3 days), SNAP for the series' own state,
    day of month, week of year."""

    name = "recipe6_calendar"
    CAL_EXTRA = ([f"event_lead{k}" for k in (3, 2, 1)] + [f"event_lag{k}" for k in (1, 2, 3)]
                 + ["snap_own", "day_of_month", "week_of_year"])

    @property
    def features(self) -> list[str]:
        return super().features + self.CAL_EXTRA


# L2-objective variants of ingredients 3-6 (fallback chain on the ingredient-1 base): the
# Tweedie base under-forecast by 4-5% on m5_ca1 and every feature ingredient improved WAPE
# but not WRMSSE on top of it. Same features, same early stopping, L2 loss.
_L2 = {**LGBMRecipe1Capacity.PARAMS}


class LGBMRecipe3DirectL2(LGBMRecipe3Direct):
    name = "recipe3_direct_l2"; PARAMS = _L2


class LGBMRecipe4RollingL2(LGBMRecipe4Rolling):
    name = "recipe4_rolling_l2"; PARAMS = _L2


class LGBMRecipe5PriceL2(LGBMRecipe5Price):
    name = "recipe5_price_l2"; PARAMS = _L2


class LGBMRecipe6CalendarL2(LGBMRecipe6Calendar):
    name = "recipe6_calendar_l2"; PARAMS = _L2


class LGBMXmasThanksgivingDept(LGBMChristmasZero):
    """H041 (retest of H039 on the champion): multiply the Christmas-zeroed forecast on
    Thanksgiving Day and the three days after it by the department's mean prior-year ratio of
    that day to its four same-weekday days before (history strictly before the origin). No
    40-origin training window contains a Thanksgiving; no model input changes."""

    name = "lgbm_xmas0_tgd"

    def extra_config(self) -> dict:
        return {"postprocess": "christmas_zero+thanksgiving_dept4"}

    def forecast(
        self, panel: Panel, origin: pd.Timestamp, horizon: int = HORIZON, seed: int = 42
    ) -> pd.DataFrame:
        # predict rows are series-major (id repeated per horizon), matching reshape(-1)
        self._mult = event_window_multipliers(
            panel, panel.pos(origin), horizon, "Thanksgiving", "dept_id"
        ).reshape(-1)
        return super().forecast(panel, origin, horizon, seed)

    def postprocess(self, predict: pd.DataFrame, preds: np.ndarray) -> np.ndarray:
        return super().postprocess(predict, preds) * self._mult


class LGBMRecipeBag3(LGBMRecipe6CalendarL2):
    """Lever 2 (SPEC_v4): seed-averaged forecasts. forecast(seed) is the mean of three fits
    at sub-seeds derived from `seed`, so each logged seed is already a small ensemble. The
    harness's per-seed spread shrinks (~1/sqrt(3)) and the keep-rule bar with it; the
    variance reduction usually also improves the mean. 3x the fit cost."""

    name = "recipe_bag3"
    BAG = 3

    def extra_config(self) -> dict:
        return {**super().extra_config(), "bag": self.BAG}

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        preds = [super(LGBMRecipeBag3, self)._fit_predict(train, predict, seed + 1000 * k) for k in range(self.BAG)]
        return np.mean(preds, axis=0)


class LGBMRecipeScaled(LGBMRecipeBag3):
    """Bias fix 1 (SPEC_v4 lever 1): predict a RATIO, not a level. The training target is
    y / scale where scale = the series' 28-day mean at the origin (the roll_mean_28 feature,
    floored so zero-history series fall back to an unscaled target); predictions are
    multiplied back by the same scale. Trees cannot extrapolate a level they have not seen;
    a level-invariant target lets growth between the training window and the forecast
    window pass straight through. Everything else as recipe_bag3."""

    name = "recipe_scaled"
    SCALE_FEATURE = "roll_mean_28"
    SCALE_FLOOR = 0.1  # below this the series is essentially dormant; use the raw target

    def extra_config(self) -> dict:
        return {**super().extra_config(), "target_scale": self.SCALE_FEATURE, "scale_floor": self.SCALE_FLOOR}

    def _scale(self, frame: pd.DataFrame) -> np.ndarray:
        s = frame[self.SCALE_FEATURE].to_numpy(dtype=float)
        return np.where(s >= self.SCALE_FLOOR, s, 1.0)

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        s_tr = self._scale(train)
        scaled = train.assign(y=train["y"].to_numpy(dtype=float) / s_tr)
        return super()._fit_predict(scaled, predict, seed) * self._scale(predict)


class LGBMRecipeMomentum(LGBMRecipeBag3):
    """Bias fix 2: momentum ratios at the origin (7/28, 28/56, 28/180-day level ratios) on
    the bagged recipe, so the model can lift or lower a forecast for a series whose level
    is moving. (First planned on the ratio target; that base lost, r109.)"""

    name = "recipe_momentum"

    @property
    def features(self) -> list[str]:
        return super().features + ["mom_7_28", "mom_28_56", "mom_28_180"]


class LGBMRecipeScaledW(LGBMRecipeScaled):
    """Bias fix 1b: the ratio target with level-proportional sample weights (weight = the
    scale), so the L2 loss on ratios is a level-weighted loss and high-volume series keep
    their importance — the unweighted ratio target (r109) let low-volume series' noisy
    ratios dominate and over-forecast by +2.7%."""

    name = "recipe_scaled_w"

    def _fit_predict(self, train: pd.DataFrame, predict: pd.DataFrame, seed: int) -> np.ndarray:
        import lightgbm as lgb
        s_tr = self._scale(train)
        scaled = train.assign(y=train["y"].to_numpy(dtype=float) / s_tr)
        self._sample_weight = s_tr
        try:
            return LGBMRecipe1Capacity._fit_predict_weighted(self, scaled, predict, seed, s_tr) * self._scale(predict)
        finally:
            self._sample_weight = None


def _fit_predict_weighted(self, train, predict, seed, weight):
    """LGBMRecipe1Capacity._fit_predict with per-row sample weights (bag-aware via Bag3)."""
    import lightgbm as lgb
    preds = []
    for k in range(getattr(self, "BAG", 1)):
        sd = seed + 1000 * k
        params = dict(self.PARAMS); params.update(random_state=sd, seed=sd, bagging_seed=sd, feature_fraction_seed=sd)
        features = self.features
        categorical = [c for c in features if c in CATEGORICAL_COLUMNS]
        origin_of_row = train["date"] - pd.to_timedelta(train["horizon"].astype(int) - 1, unit="D")
        val_mask = (origin_of_row == origin_of_row.max()).to_numpy()
        x_all = train[features]
        x_tr, y_tr, w_tr = x_all[~val_mask], train["y"][~val_mask], weight[~val_mask]
        x_va, y_va, w_va = x_all[val_mask], train["y"][val_mask], weight[val_mask]
        x_pred = predict[features].copy()
        for col in categorical:
            cats = x_tr[col].cat.categories
            x_va = x_va.assign(**{col: pd.Categorical(x_va[col], categories=cats)})
            x_pred[col] = pd.Categorical(x_pred[col], categories=cats)
        model = lgb.LGBMRegressor(**params)
        model.fit(x_tr, y_tr, sample_weight=w_tr, eval_set=[(x_va, y_va)], eval_sample_weight=[w_va],
                  categorical_feature=categorical, callbacks=[lgb.early_stopping(self.EARLY_STOPPING_ROUNDS, verbose=False)])
        preds.append(model.predict(x_pred, num_iteration=model.best_iteration_))
    return np.mean(preds, axis=0)


LGBMRecipe1Capacity._fit_predict_weighted = _fit_predict_weighted


MODELS: dict[str, type] = {
    SeasonalNaive.name: SeasonalNaive,
    LGBMBaseline.name: LGBMBaseline,
    LGBMChristmasZero.name: LGBMChristmasZero,
    LGBMRecipe1Capacity.name: LGBMRecipe1Capacity,
    LGBMRecipe2Tweedie.name: LGBMRecipe2Tweedie,
    LGBMRecipe3Direct.name: LGBMRecipe3Direct,
    LGBMRecipe4Rolling.name: LGBMRecipe4Rolling,
    LGBMRecipe5Price.name: LGBMRecipe5Price,
    LGBMRecipe6Calendar.name: LGBMRecipe6Calendar,
    LGBMRecipe3DirectL2.name: LGBMRecipe3DirectL2,
    LGBMRecipe4RollingL2.name: LGBMRecipe4RollingL2,
    LGBMRecipe5PriceL2.name: LGBMRecipe5PriceL2,
    LGBMRecipe6CalendarL2.name: LGBMRecipe6CalendarL2,
    LGBMRecipeBag3.name: LGBMRecipeBag3,
    LGBMRecipeScaled.name: LGBMRecipeScaled,
    LGBMRecipeMomentum.name: LGBMRecipeMomentum,
    LGBMRecipeScaledW.name: LGBMRecipeScaledW,


    LGBMXmasThanksgivingDept.name: LGBMXmasThanksgivingDept,
}


def get_model(name: str):
    if name not in MODELS:
        raise SystemExit(f"Unknown model '{name}'. Registered: {', '.join(sorted(MODELS))}")
    return MODELS[name]()
